# Copyright (c) 2026, GDL and contributors
"""Where the fields sit on the service record.

GDL walked through this on a call: "same line also" (Vehicle and Location),
"that field need under service item table in right", "need same line" and
"form will more long need short".

The result: Location beside Vehicle, and the three costs on ONE line under the
Service Items table they are totalled from - which also takes three rows off
the height of the form.

This is asserted because the order was being fought over by two modules.
maintenance_simplification used to pin `location` after `vehicle` and
`labour_cost` after `gdl_service_cb`, and it runs AFTER maintenance_fields, so
it silently undid both changes on every migrate. There is one owner now -
maintenance_fields.enforce_field_order() - and this test fails if a second one
appears.
"""

import frappe
from frappe.tests import IntegrationTestCase

DOCTYPE = "Asset Maintenance Log"


def rows():
	"""The form as frappe lays it out: a list of rows, each a list of labels."""
	out, row = [], []
	for field in frappe.get_meta(DOCTYPE).fields:
		if field.hidden or field.fieldname == "amended_from":
			continue
		if field.fieldtype == "Section Break":
			if row:
				out.append(row)
			out.append([f"SECTION:{field.label or ''}"])
			row = []
			continue
		if field.fieldtype == "Column Break":
			continue
		row.append(field.label)
	if row:
		out.append(row)
	return out


def row_containing(label):
	for row in rows():
		if label in row:
			return row
	return []


class TestServiceRecordLayout(IntegrationTestCase):
	def test_location_is_on_the_same_line_as_vehicle(self):
		row = row_containing("Vehicle")
		self.assertIn("Location", row,
		              "Location is not on the same line as Vehicle")

	def test_the_three_costs_are_on_one_line(self):
		row = row_containing("Labour Cost")
		for label in ("Parts Cost", "Total Cost"):
			self.assertIn(label, row, f"{label} is not on the same line as Labour Cost")

	def test_the_costs_come_after_the_service_items_table(self):
		flat = [cell for row in rows() for cell in row]
		self.assertLess(flat.index("Service Items"), flat.index("Labour Cost"),
		                "the costs are above the table they are totalled from")

	def test_the_costs_are_not_in_the_service_details_section(self):
		"""They were. Moving them out is what took three rows off the form."""
		seen_section = None
		for row in rows():
			if row and str(row[0]).startswith("SECTION:"):
				seen_section = row[0]
			if "Labour Cost" in row:
				self.assertNotEqual(seen_section, "SECTION:Service Details")
				return
		self.fail("Labour Cost is not on the form at all")

	def test_only_one_module_decides_the_order(self):
		"""maintenance_simplification used to rewrite insert_after for
		`location` and `labour_cost` after maintenance_fields had set it,
		undoing both layout changes on every migrate."""
		import inspect

		from gdl_fleet_extension.setup import maintenance_simplification
		source = inspect.getsource(maintenance_simplification)
		for fieldname in ('"fieldname": "location"', '"fieldname": "labour_cost"'):
			self.assertNotIn(
				f'frappe.db.set_value("Custom Field", {{"dt": DOCTYPE, {fieldname}}},\n'
				f'\t                    "insert_after"', source,
				"maintenance_simplification is pinning field order again")

	def test_the_order_is_enforced_after_every_field_exists(self):
		"""create_custom_fields saves fields in list order, so one pointing at
		a break defined further down does not stick. The chain is re-applied
		afterwards."""
		from gdl_fleet_extension.setup.maintenance_fields import (
			FIELD_ORDER,
			enforce_field_order,
		)
		chain = FIELD_ORDER[DOCTYPE]
		for fieldname, after in chain.items():
			name = frappe.db.get_value(
				"Custom Field", {"dt": DOCTYPE, "fieldname": fieldname}, "name")
			if not name:
				continue
			with self.subTest(field=fieldname):
				self.assertEqual(
					frappe.db.get_value("Custom Field", name, "insert_after"), after)
		enforce_field_order()		# idempotent
