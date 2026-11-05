# Copyright (c) 2026, GDL and contributors
"""A person's name, not their record id.

An Employee is named by its naming series, so every Link to one read "E260001".
GDL asked for the name "in all place". The flag that does that lives on the
TARGET doctype, which is why one row covers every form at once.
"""

import frappe
from frappe.tests import IntegrationTestCase

from gdl_fleet_extension.setup.people_display import SHOW_NAME_IN_LINKS


class TestLinksShowThePersonsName(IntegrationTestCase):
	def test_the_flag_is_set_on_this_site(self):
		"""Reads what the site holds. A default in a JSON applies at creation
		only, which is how two settings in this app were found sitting at 0."""
		for doctype in SHOW_NAME_IN_LINKS:
			self.assertTrue(
				frappe.get_meta(doctype).show_title_field_in_link,
				f"{doctype} links still show the id - setup_people_display did not run",
			)

	def test_the_title_field_is_the_name_field(self):
		"""The flag shows the title_field. If that is not the name field, the
		flag changes which id is displayed and nothing else."""
		for doctype, fieldname in SHOW_NAME_IN_LINKS.items():
			self.assertEqual(frappe.get_meta(doctype).title_field, fieldname)

	def test_the_name_field_actually_exists(self):
		for doctype, fieldname in SHOW_NAME_IN_LINKS.items():
			self.assertIsNotNone(frappe.get_meta(doctype).get_field(fieldname))

	def test_every_employee_link_in_the_fleet_benefits(self):
		"""The point of fixing the target rather than each field: prove the
		fleet's own Employee links are covered, without naming them one by one."""
		covered = []
		for doctype in ("POL Abstract", "Asset Maintenance Log", "Movement Order",
		                "Movement Order Request", "Vehicle Log", "Driver"):
			if not frappe.db.exists("DocType", doctype):
				continue
			for field in frappe.get_meta(doctype).fields:
				if field.fieldtype == "Link" and field.options == "Employee":
					covered.append(f"{doctype}.{field.fieldname}")
		self.assertTrue(covered, "no Employee link found - this test has stopped testing anything")
		self.assertTrue(frappe.get_meta("Employee").show_title_field_in_link)

	def test_the_id_is_still_what_is_stored(self):
		"""Display only. The stored value must stay the primary key, or every
		report, filter and link in the system breaks."""
		employee = frappe.get_all("Employee", fields=["name", "employee_name"], limit=1)
		if not employee:
			self.skipTest("no Employee on this site")
		self.assertNotEqual(employee[0].name, employee[0].employee_name)
