# Copyright (c) 2026, GDL and contributors
"""The new Vehicle Log form.

GDL: "From drivers page- New vehicle log. Driver is not showing and in
Employee, it should show all employee."
"""

import os
import re

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

import gdl_fleet_extension
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle

SCRIPT = os.path.join(os.path.dirname(gdl_fleet_extension.__file__),
                      "public", "js", "vehicle_log.js")


def script():
	with open(SCRIPT, encoding="utf-8") as f:
		return re.sub(r"//.*", "", f.read())


class TestTheEmployeeListIsNotFiltered(IntegrationTestCase):
	"""HRMS sets `filters: { status: "Active" }` on this link in its own
	vehicle_log.js. A journey can belong to somebody who has since left, and
	the log is a record of what happened, so GDL want all of them.
	"""

	def test_our_script_is_registered_for_vehicle_log(self):
		"""It only wins because it loads after HRMS's."""
		from gdl_fleet_extension import hooks

		self.assertEqual(hooks.doctype_js.get("Vehicle Log"),
		                 "public/js/vehicle_log.js")

	def test_it_clears_the_employee_query(self):
		self.assertRegex(script(), r'set_query\(\s*"employee"',
		                 "nothing replaces the HRMS filter")

	def test_it_does_not_re_impose_a_status_filter(self):
		body = script()
		employee_part = body[body.index('set_query("employee"'):][:200]
		self.assertNotIn("Active", employee_part,
		                 "the employee list is filtered to Active again")

	def test_the_field_itself_carries_no_filter(self):
		"""Nothing on the doctype narrows it either."""
		field = frappe.get_meta("Vehicle Log").get_field("employee")
		self.assertFalse(field.get("link_filters"))


class TestTheDriverIsFilledIn(IntegrationTestCase):
	"""The server already fills the driver on save. The form has to show it
	as soon as the vehicle is chosen, or the field looks broken."""

	def test_the_script_asks_for_the_active_driver(self):
		self.assertIn("get_active_driver", script(),
		              "the form never looks the driver up")

	def test_it_does_not_overwrite_a_driver_already_chosen(self):
		body = script()
		self.assertIn("frm.doc.driver", body,
		              "the form would overwrite a driver somebody picked")

	def test_the_server_still_fills_it_on_save(self):
		"""The browser is a convenience; this is the rule."""
		vehicle = new_vehicle(last_odometer=100)
		vehicle.insert()
		driver = frappe.db.get_value(
			"Driver", {"license_number": ("is", "set")}, "name")
		if not driver:
			self.skipTest("no Driver with a licence number on this site")

		assignment = frappe.get_doc({
			"doctype": "Driver Assignment", "vehicle": vehicle.name,
			"driver": driver, "assignment_type": "Primary",
			"from_date": add_days(nowdate(), -1),
		})
		assignment.flags.ignore_permissions = True
		assignment.insert()
		assignment.submit()

		log = frappe.get_doc({
			"doctype": "Vehicle Log", "license_plate": vehicle.name,
			"vehicle": vehicle.name,
			"employee": frappe.db.get_value("Employee", {"status": "Active"}, "name"),
			"date": nowdate(), "odometer": 150,
			"place_to_travel": "Paro",
		})
		log.flags.ignore_permissions = True
		log.insert()
		self.assertEqual(log.driver, driver,
		                 "the driver was not taken from the live assignment")
