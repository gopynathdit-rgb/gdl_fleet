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


class TestVehicleConnectsToItsRenewals(IntegrationTestCase):
	"""The Vehicle form must lead to the register, not just mirror it.

	These go through frappe's OWN call path - Meta.get_dashboard_data() - and
	not through the hook function directly. Calling the function directly is
	what let a broken signature ship: frappe calls the hook as get_data(data=...)
	and the first version took no arguments, so every Vehicle list and form
	died with "TypeError: get_data() got an unexpected keyword argument 'data'"
	while the tests stayed green.
	"""

	def dashboard(self):
		return frappe.get_meta("Vehicle").get_dashboard_data()

	def linked_doctypes(self):
		data = self.dashboard()
		return [item for group in data["transactions"] for item in (group.get("items") or [])]

	def test_the_vehicle_dashboard_builds_at_all(self):
		"""The regression itself: this is the call that was failing."""
		self.assertTrue(self.dashboard(), "the Vehicle dashboard could not be built")

	def test_renewal_register_is_on_the_vehicle_dashboard(self):
		self.assertIn("Renewal Register", self.linked_doctypes())

	def test_it_links_on_the_vehicle_field(self):
		"""Renewal Register points at a vehicle with `vehicle`, not ERPNext's
		`license_plate`, so it needs a non-standard fieldname or the strip
		would come back empty."""
		self.assertEqual(
			self.dashboard()["non_standard_fieldnames"]["Renewal Register"], "vehicle")

	def test_erpnexts_own_links_are_kept(self):
		"""The dashboard is extended, not replaced."""
		self.assertIn("Vehicle Log", self.linked_doctypes())

	def test_it_is_not_added_twice(self):
		"""get_dashboard_data() is called on every form load."""
		self.assertEqual(self.linked_doctypes().count("Renewal Register"), 1)

	def test_the_hook_accepts_the_keyword_frappe_passes(self):
		"""frappe calls it as get_data(data=...). Nothing else is supported."""
		import inspect

		from gdl_fleet_extension.overrides.vehicle_dashboard import get_data
		self.assertIn("data", inspect.signature(get_data).parameters)

	def test_the_hook_points_at_it(self):
		from gdl_fleet_extension import hooks
		self.assertEqual(
			hooks.override_doctype_dashboards["Vehicle"],
			"gdl_fleet_extension.overrides.vehicle_dashboard.get_data",
		)
