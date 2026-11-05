# Copyright (c) 2026, GDL and contributors
"""Fleet Mgmt.docx 4.5 and 4.6 - Renewal Register and its alerts."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, cint, flt, nowdate

from gdl_fleet_extension.gdl_fleet.doctype.renewal_register.renewal_register import (
	get_current_renewal,
	get_primary_notice_days,
	get_renewal_history,
	make_renewal,
	refresh_statuses,
)
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle


class TestRenewalRegister(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle()
		self.vehicle.insert()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def renew(self, kind="Insurance", expiry=None, previous=None, submit=True, **kwargs):
		values = {
			"doctype": "Renewal Register", "renewal_type": kind,
			"vehicle": self.vehicle.name,
			"certificate_no": f"POL-{frappe.generate_hash(length=5).upper()}",
			"provider": "Royal Insurance Corporation of Bhutan",
			"effective_from": add_months(expiry or nowdate(), -12),
			"expiry_date": expiry or add_months(nowdate(), 6),
			"premium": 18500,
			"previous_renewal": previous,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert()
		if submit:
			doc.submit()
		return doc

	# --- the rule the document is most explicit about -------------------------
	def test_renewal_history_is_preserved(self):
		first = self.renew(expiry=add_days(nowdate(), -200))
		second = self.renew(expiry=add_months(nowdate(), 6), previous=first.name)

		first.reload()
		self.assertTrue(frappe.db.exists("Renewal Register", first.name))
		self.assertEqual(first.renewal_status, "Renewed")
		self.assertEqual(second.previous_renewal, first.name)

		history = get_renewal_history(self.vehicle.name)
		self.assertEqual(len(history), 2)

	def test_superseded_record_keeps_its_own_particulars(self):
		first = self.renew(expiry=add_days(nowdate(), -200), premium=12000)
		original_cert = first.certificate_no
		self.renew(expiry=add_months(nowdate(), 6), previous=first.name, premium=18500)

		first.reload()
		self.assertEqual(first.certificate_no, original_cert)
		self.assertEqual(flt(first.premium), 12000.0)

	def test_chain_across_three_renewals(self):
		a = self.renew(expiry=add_days(nowdate(), -400))
		b = self.renew(expiry=add_days(nowdate(), -40), previous=a.name)
		c = self.renew(expiry=add_months(nowdate(), 6), previous=b.name)

		a.reload(); b.reload()
		self.assertEqual(a.renewal_status, "Renewed")
		self.assertEqual(b.renewal_status, "Renewed")
		self.assertEqual(c.renewal_status, "Valid")
		self.assertEqual(len(get_renewal_history(self.vehicle.name)), 3)

	# --- all seven renewal types ---------------------------------------------
	def test_all_document_renewal_types(self):
		options = frappe.get_meta("Renewal Register").get_field("renewal_type").options.split("\n")
		for kind in ("Insurance", "Registration", "Fitness", "Emission", "Permit",
		             "Road Tax", "Other"):
			self.assertIn(kind, options)

	def test_multiple_types_coexist_for_one_vehicle(self):
		self.renew("Insurance", expiry=add_months(nowdate(), 6))
		self.renew("Registration", expiry=add_months(nowdate(), 9))
		self.renew("Fitness", expiry=add_months(nowdate(), 3))
		self.assertEqual(len(get_renewal_history(self.vehicle.name)), 3)
		self.assertEqual(
			len(get_renewal_history(self.vehicle.name, renewal_type="Insurance")), 1
		)

	# --- status ---------------------------------------------------------------
	def test_valid_status(self):
		doc = self.renew(expiry=add_months(nowdate(), 6))
		self.assertEqual(doc.renewal_status, "Valid")

	def test_due_soon_status(self):
		doc = self.renew(expiry=add_days(nowdate(), 10))
		self.assertEqual(doc.renewal_status, "Due Soon")

	def test_expired_status(self):
		doc = self.renew(expiry=add_days(nowdate(), -5))
		self.assertEqual(doc.renewal_status, "Expired")

	def test_days_to_expiry(self):
		doc = self.renew(expiry=add_days(nowdate(), 20))
		self.assertEqual(cint(doc.days_to_expiry), 20)

	def test_notice_window_is_configuration(self):
		"""Nothing is hard-coded: the window is whatever GDL sets.

		GDL answered 14 days on 3 Nov 2026, so that is the live value - but
		the point of this test is that CHANGING it changes behaviour, not that
		it happens to be 14 today.
		"""
		self.assertEqual(cint(get_primary_notice_days()), 14)

		settings = frappe.get_single("GDL Fleet Settings")
		original = settings.renewal_notice_days
		settings.renewal_notice_days = 30
		settings.flags.ignore_permissions = True
		settings.save()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
		try:
			self.assertEqual(cint(get_primary_notice_days()), 30)
			# 20 days out is Valid at a 14-day window but Due Soon at 30
			doc = self.renew(expiry=add_days(nowdate(), 20))
			self.assertEqual(doc.renewal_status, "Due Soon")
		finally:
			settings = frappe.get_single("GDL Fleet Settings")
			settings.renewal_notice_days = original
			settings.flags.ignore_permissions = True
			settings.save()
			frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def test_escalation_ladder_is_configurable(self):
		settings = frappe.get_single("GDL Fleet Settings")
		for fieldname in ("renewal_notice_days", "renewal_second_reminder_days",
		                  "renewal_third_reminder_days", "renewal_final_reminder_days"):
			self.assertTrue(
				frappe.get_meta("GDL Fleet Settings").get_field(fieldname),
				f"{fieldname} must be configurable",
			)

	def test_refresh_statuses(self):
		doc = self.renew(expiry=add_months(nowdate(), 6))
		self.assertEqual(doc.renewal_status, "Valid")
		frappe.db.set_value("Renewal Register", doc.name, "expiry_date",
		                    add_days(nowdate(), -3), update_modified=False)
		refresh_statuses()
		self.assertEqual(
			frappe.db.get_value("Renewal Register", doc.name, "renewal_status"), "Expired"
		)

	def test_refresh_leaves_renewed_records_alone(self):
		first = self.renew(expiry=add_days(nowdate(), -200))
		self.renew(expiry=add_months(nowdate(), 6), previous=first.name)
		refresh_statuses()
		first.reload()
		self.assertEqual(first.renewal_status, "Renewed")

	# --- validation -----------------------------------------------------------
	def test_expiry_before_effective_rejected(self):
		doc = frappe.get_doc({
			"doctype": "Renewal Register", "renewal_type": "Insurance",
			"vehicle": self.vehicle.name, "effective_from": nowdate(),
			"expiry_date": add_days(nowdate(), -10),
		})
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_previous_renewal_must_match_vehicle(self):
		other = new_vehicle()
		other.insert()
		first = self.renew(expiry=add_days(nowdate(), -100))

		doc = frappe.get_doc({
			"doctype": "Renewal Register", "renewal_type": "Insurance",
			"vehicle": other.name, "expiry_date": add_months(nowdate(), 6),
			"previous_renewal": first.name,
		})
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_previous_renewal_must_match_type(self):
		first = self.renew("Insurance", expiry=add_days(nowdate(), -100))
		doc = frappe.get_doc({
			"doctype": "Renewal Register", "renewal_type": "Fitness",
			"vehicle": self.vehicle.name, "expiry_date": add_months(nowdate(), 6),
			"previous_renewal": first.name,
		})
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_expiry_date_is_mandatory(self):
		self.assertTrue(frappe.get_meta("Renewal Register").get_field("expiry_date").reqd)

	# --- helpers --------------------------------------------------------------
	def test_current_renewal_is_the_live_one(self):
		first = self.renew(expiry=add_days(nowdate(), -200))
		second = self.renew(expiry=add_months(nowdate(), 6), previous=first.name)
		current = get_current_renewal(self.vehicle.name, "Insurance")
		self.assertEqual(current["name"], second.name)

	def test_make_renewal_carries_forward_and_chains(self):
		first = self.renew(expiry=add_days(nowdate(), 5))
		nxt = make_renewal(first.name)
		self.assertEqual(nxt["previous_renewal"], first.name)
		self.assertEqual(nxt["vehicle"], self.vehicle.name)
		self.assertEqual(nxt["renewal_type"], "Insurance")

	def test_insurance_renewal_updates_the_vehicle_display(self):
		doc = self.renew("Insurance", expiry=add_months(nowdate(), 8),
		                 provider="Bhutan Insurance Ltd")
		self.assertEqual(
			frappe.db.get_value("Vehicle", self.vehicle.name, "insurance_company"),
			"Bhutan Insurance Ltd",
		)
		self.assertEqual(
			str(frappe.db.get_value("Vehicle", self.vehicle.name, "end_date")),
			str(doc.expiry_date),
		)

	def test_attachment_field_available(self):
		self.assertEqual(
			frappe.get_meta("Renewal Register").get_field("attachment").fieldtype, "Attach"
		)

	def test_permissions(self):
		roles = {p.role for p in frappe.get_meta("Renewal Register").permissions}
		self.assertIn("Fleet Administrator", roles)
		read_only = {p.role for p in frappe.get_meta("Renewal Register").permissions
		             if not p.write}
		self.assertIn("Fleet User", read_only)
