# Copyright (c) 2026, GDL and contributors
"""The Renewal Register and the Vehicle's own display fields.

GDL: "in vehicle master insurance details there then what is Renewal Register?
need link with that."
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from gdl_fleet_extension.gdl_fleet.doctype.renewal_register.renewal_register import (
	VEHICLE_FIELDS_BY_TYPE,
)
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle


class TestRenewalSyncsToVehicle(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle()
		self.vehicle.insert()

	def renew(self, renewal_type, expiry=None, submit=True, **kwargs):
		values = {
			"doctype": "Renewal Register",
			"vehicle": self.vehicle.name,
			"renewal_type": renewal_type,
			"effective_from": nowdate(),
			"expiry_date": expiry or add_days(nowdate(), 365),
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def vehicle_value(self, fieldname):
		return frappe.db.get_value("Vehicle", self.vehicle.name, fieldname)

	# --- the three types that have a Vehicle field ----------------------
	def test_insurance_reaches_the_vehicle(self):
		expiry = add_days(nowdate(), 200)
		self.renew("Insurance", expiry=expiry, provider="Bhutan Insurance",
		           certificate_no="POL-123")
		self.assertEqual(self.vehicle_value("insurance_company"), "Bhutan Insurance")
		self.assertEqual(self.vehicle_value("policy_no"), "POL-123")
		self.assertEqual(str(self.vehicle_value("end_date")), expiry)

	def test_registration_reaches_the_vehicle(self):
		"""Before this, a Registration renewal left Registration Expiry blank
		for ever - a field on screen that nothing ever filled."""
		expiry = add_days(nowdate(), 300)
		self.renew("Registration", expiry=expiry)
		self.assertEqual(str(self.vehicle_value("registration_expiry")), expiry)

	def test_fitness_reaches_inspection_expiry(self):
		expiry = add_days(nowdate(), 120)
		self.renew("Fitness", expiry=expiry)
		self.assertEqual(str(self.vehicle_value("inspection_expiry")), expiry)

	# --- the ones that deliberately do not ------------------------------
	def test_a_type_with_no_vehicle_field_is_register_only(self):
		"""Road Tax has no field on the Vehicle form. It must not fail, and it
		must not quietly land in somebody else's field."""
		before = self.vehicle_value("registration_expiry")
		self.renew("Road Tax", expiry=add_days(nowdate(), 90))
		self.assertEqual(self.vehicle_value("registration_expiry"), before)

	def test_the_renewal_date_fields_hold_the_renew_by_date(self):
		"""Asked whether these meant "renewed on" or "renew by", GDL answered
		"renew by date" - which is the day the certificate expires."""
		insurance_expiry = add_days(nowdate(), 180)
		registration_expiry = add_days(nowdate(), 240)
		self.renew("Insurance", expiry=insurance_expiry, provider="X", certificate_no="Y")
		self.renew("Registration", expiry=registration_expiry)
		self.assertEqual(str(self.vehicle_value("insurance_renewal_date")), insurance_expiry)
		self.assertEqual(str(self.vehicle_value("registration_renewal_date")),
		                 registration_expiry)

	def test_renew_by_matches_the_expiry_it_came_from(self):
		"""They are the same date by GDL's definition - so they must not drift
		apart, and a Registration expiry must not land in the insurance one."""
		self.renew("Insurance", expiry=add_days(nowdate(), 180),
		           provider="X", certificate_no="Y")
		self.renew("Registration", expiry=add_days(nowdate(), 240))
		self.assertEqual(self.vehicle_value("insurance_renewal_date"),
		                 self.vehicle_value("end_date"))
		self.assertEqual(self.vehicle_value("registration_renewal_date"),
		                 self.vehicle_value("registration_expiry"))
		self.assertNotEqual(self.vehicle_value("insurance_renewal_date"),
		                    self.vehicle_value("registration_renewal_date"))

	def test_fitness_does_not_touch_either_renewal_date(self):
		"""There is no Inspection Renewal Date field, and Fitness must not
		borrow one belonging to another certificate."""
		self.renew("Fitness", expiry=add_days(nowdate(), 60))
		self.assertIsNone(self.vehicle_value("insurance_renewal_date"))
		self.assertIsNone(self.vehicle_value("registration_renewal_date"))

	# --- history is what the register is for ----------------------------
	def test_an_older_renewal_cannot_overwrite_the_live_one(self):
		"""Submitting a lapsed policy late must not drag the Vehicle back."""
		current = add_days(nowdate(), 300)
		self.renew("Insurance", expiry=current, provider="Current", certificate_no="NEW")
		self.renew("Insurance", expiry=add_days(nowdate(), -30),
		           effective_from=add_days(nowdate(), -395),
		           provider="Lapsed", certificate_no="OLD")
		self.assertEqual(self.vehicle_value("insurance_company"), "Current",
		                 "a lapsed policy overwrote the live one")
		self.assertEqual(str(self.vehicle_value("end_date")), current)

	def test_both_records_survive(self):
		"""Section 4.5: history is retained, not replaced."""
		self.renew("Insurance", expiry=add_days(nowdate(), 100),
		           provider="First", certificate_no="A")
		self.renew("Insurance", expiry=add_days(nowdate(), 465),
		           effective_from=add_days(nowdate(), 100),
		           provider="Second", certificate_no="B")
		held = frappe.get_all("Renewal Register",
		                      filters={"vehicle": self.vehicle.name, "renewal_type": "Insurance"},
		                      pluck="name")
		self.assertEqual(len(held), 2, "a renewal replaced its predecessor")


class TestTheRenewalsConnectionIsGone(IntegrationTestCase):
	"""GDL asked for the Connections strip entry back off the Vehicle form:
	"remove Renewals".

	It was added so a vehicle led to its renewals. GDL have since linked the
	two in the other direction - saving a Vehicle writes the register - and
	did not want the strip. The LINK between the records is untouched; only
	the box at the top of the form is gone.
	"""

	def test_the_dashboard_override_is_not_registered(self):
		from gdl_fleet_extension import hooks

		self.assertFalse(getattr(hooks, "override_doctype_dashboards", None),
		                 "the Vehicle dashboard is being overridden again")

	def test_the_vehicle_form_still_builds(self):
		"""Removing a hook must not take the form with it."""
		self.assertTrue(frappe.get_meta("Vehicle").get_dashboard_data())

	def test_the_records_are_still_linked(self):
		"""Only the strip went. A renewal still points at its vehicle, and
		saving a vehicle still writes the register."""
		self.assertTrue(frappe.get_meta("Renewal Register").get_field("vehicle"))
		from gdl_fleet_extension.overrides.vehicle_renewals import RENEWAL_SOURCES

		self.assertIn("Insurance", RENEWAL_SOURCES)
