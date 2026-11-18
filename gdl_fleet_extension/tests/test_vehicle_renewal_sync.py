# Copyright (c) 2026, GDL and contributors
"""Vehicle insurance / registration details -> the Renewal Register.

GDL's client, on the Vehicle master: "once these details were updated, it
should show in the Renewal Register for both Registration and Insurance
Renewal. Its not updating. Please link these 2."

The link ran one way before this - register to vehicle. Typing the dates onto
the Vehicle did nothing, so a vehicle could show an insurance expiry the
register had never heard of, while the reminders, the Insurance / Renewal Due
report and the §4.5 history all run off the register.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle


class TestVehicleFeedsTheRenewalRegister(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle()
		self.vehicle.insert()

	def renewals(self, renewal_type=None):
		filters = {"vehicle": self.vehicle.name}
		if renewal_type:
			filters["renewal_type"] = renewal_type
		return frappe.get_all(
			"Renewal Register", filters=filters,
			fields=["name", "renewal_type", "provider", "certificate_no",
			        "effective_from", "expiry_date", "renewal_status",
			        "previous_renewal", "docstatus"],
			order_by="creation")

	def save_vehicle(self, **values):
		doc = frappe.get_doc("Vehicle", self.vehicle.name)
		for field, value in values.items():
			doc.set(field, value)
		doc.flags.ignore_permissions = True
		doc.save()
		return doc

	# --- the thing that was missing --------------------------------------
	def test_insurance_typed_on_the_vehicle_reaches_the_register(self):
		expiry = add_days(nowdate(), 365)
		self.save_vehicle(insurance_company="RICB", policy_no="POL-1",
		                  start_date=nowdate(), end_date=expiry)
		rows = self.renewals("Insurance")
		self.assertEqual(len(rows), 1, "no Insurance record appeared in the register")
		self.assertEqual(rows[0].provider, "RICB")
		self.assertEqual(rows[0].certificate_no, "POL-1")
		self.assertEqual(str(rows[0].expiry_date), expiry)
		self.assertEqual(rows[0].docstatus, 1, "the record was left as a draft")

	def test_registration_typed_on_the_vehicle_reaches_the_register(self):
		expiry = add_days(nowdate(), 200)
		self.save_vehicle(registration_expiry=expiry)
		rows = self.renewals("Registration")
		self.assertEqual(len(rows), 1)
		self.assertEqual(str(rows[0].expiry_date), expiry)

	def test_both_at_once(self):
		self.save_vehicle(insurance_company="RICB", policy_no="POL-1",
		                  end_date=add_days(nowdate(), 365),
		                  registration_expiry=add_days(nowdate(), 200))
		self.assertEqual({r.renewal_type for r in self.renewals()},
		                 {"Insurance", "Registration"})

	# --- and the things that must NOT happen ------------------------------
	def test_a_vehicle_with_no_dates_creates_nothing(self):
		self.save_vehicle(color="Blue")
		self.assertEqual(self.renewals(), [])

	def test_saving_again_does_not_duplicate(self):
		"""A vehicle is saved whenever anything on it changes. Every save must
		not stack up another identical renewal."""
		self.save_vehicle(insurance_company="RICB", policy_no="POL-1",
		                  end_date=add_days(nowdate(), 365))
		for _ in range(3):
			self.save_vehicle(color="Blue")
		self.assertEqual(len(self.renewals("Insurance")), 1,
		                 "re-saving the vehicle stacked up duplicate renewals")

	def test_the_register_writing_back_does_not_re_enter(self):
		"""Submitting a renewal writes its dates onto the Vehicle. If that
		write triggered this sync, the two would create records off each other
		without end."""
		self.save_vehicle(insurance_company="RICB", policy_no="POL-1",
		                  end_date=add_days(nowdate(), 365))
		self.assertEqual(len(self.renewals()), 1)

	# --- correction vs renewal -------------------------------------------
	def test_the_same_expiry_with_new_particulars_is_a_correction(self):
		"""A mistyped policy number is not a new policy."""
		expiry = add_days(nowdate(), 365)
		self.save_vehicle(insurance_company="RICB", policy_no="TYPO", end_date=expiry)
		first = self.renewals("Insurance")[0].name

		self.save_vehicle(policy_no="POL-CORRECT")
		rows = self.renewals("Insurance")
		self.assertEqual(len(rows), 1, "a correction created a second renewal")
		self.assertEqual(rows[0].name, first, "the original record was replaced")
		self.assertEqual(rows[0].certificate_no, "POL-CORRECT")

	def test_a_new_expiry_is_a_renewal_and_keeps_the_old_record(self):
		"""Section 4.5: the history is retained, not overwritten."""
		self.save_vehicle(insurance_company="RICB", policy_no="POL-1",
		                  end_date=add_days(nowdate(), 100))
		old = self.renewals("Insurance")[0].name

		self.save_vehicle(policy_no="POL-2", end_date=add_days(nowdate(), 465))
		rows = self.renewals("Insurance")
		self.assertEqual(len(rows), 2, "the renewal did not create a second record")

		previous = next(r for r in rows if r.name == old)
		current = next(r for r in rows if r.name != old)
		self.assertEqual(previous.renewal_status, "Renewed")
		self.assertEqual(previous.certificate_no, "POL-1", "the old policy was edited away")
		self.assertEqual(current.previous_renewal, old, "the chain was not recorded")
		self.assertEqual(current.certificate_no, "POL-2")

	def test_registration_and_insurance_do_not_cross(self):
		"""Each type chains only to its own."""
		self.save_vehicle(end_date=add_days(nowdate(), 365),
		                  registration_expiry=add_days(nowdate(), 200))
		self.save_vehicle(registration_expiry=add_days(nowdate(), 565))
		self.assertEqual(len(self.renewals("Insurance")), 1,
		                 "renewing the registration touched the insurance")
		self.assertEqual(len(self.renewals("Registration")), 2)

	# --- the master must still save --------------------------------------
	def test_a_failing_sync_does_not_block_saving_the_vehicle(self):
		"""The register is built on top of the master. A fault there is worth
		logging, not worth stopping somebody editing a vehicle."""
		from unittest.mock import patch

		with patch("gdl_fleet_extension.overrides.vehicle_renewals.sync_one",
		           side_effect=Exception("boom")):
			self.save_vehicle(insurance_company="RICB",
			                  end_date=add_days(nowdate(), 365))
		self.assertEqual(
			frappe.db.get_value("Vehicle", self.vehicle.name, "insurance_company"),
			"RICB", "the vehicle did not save when the register sync failed")


class TestTheDuplicateInsuranceDateIsGone(IntegrationTestCase):
	"""GDL's client: "There are 2 Insurance Renewals. u can remove one."

	Insurance Expiry and Insurance Renewal Date held the same fact - GDL had
	already defined a renewal date as the "renew by" date, and a policy must be
	renewed by the day it expires.
	"""

	def test_insurance_renewal_date_is_off_the_form(self):
		field = frappe.get_meta("Vehicle").get_field("insurance_renewal_date")
		self.assertIsNotNone(field, "the field was deleted rather than hidden")
		self.assertTrue(field.hidden, "Insurance Renewal Date is still on the form")

	def test_insurance_expiry_is_the_one_kept(self):
		"""It belongs with the company and the policy number, which is where
		somebody looks for it."""
		field = frappe.get_meta("Vehicle").get_field("end_date")
		self.assertIsNotNone(field)
		self.assertFalse(field.hidden, "Insurance Expiry was hidden by mistake")

	def test_nothing_was_deleted(self):
		"""Standing constraint on this project: hidden, never dropped."""
		self.assertTrue(
			frappe.db.has_column("Vehicle", "insurance_renewal_date"),
			"the column holding existing data was dropped")
