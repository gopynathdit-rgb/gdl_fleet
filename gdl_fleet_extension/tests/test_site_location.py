# Copyright (c) 2026, GDL and contributors
"""
Phase 12 - the GDL site master is the STANDARD ERPNext Location.

No Site DocType exists. These tests assert the approved tree and that every
fleet document can reference a site.
"""

import frappe
from frappe.tests import IntegrationTestCase

APPROVED_TREE = {
	"GDL": {"parent": None, "is_group": 1},
	"Head Office": {"parent": "GDL", "is_group": 0},
	"Farms": {"parent": "GDL", "is_group": 1},
	"Jamjee Farm": {"parent": "Farms", "is_group": 0},
	"Dochula Farm": {"parent": "Farms", "is_group": 0},
	"Dagapela Farm": {"parent": "Farms", "is_group": 0},
	"Gedu": {"parent": "Farms", "is_group": 0},
	"Samcholing": {"parent": "Farms", "is_group": 0},
	"Jigmeling": {"parent": "Farms", "is_group": 0},
}

# DocType -> the field that carries the site
SITE_FIELDS = {
	"Vehicle": "site",
	"Movement Order Request": "site",
	"Vehicle Log": "site",
	"Driver": "site",
}


class TestSiteLocation(IntegrationTestCase):
	# --- no duplicate master --------------------------------------------------
	def test_no_site_doctype_was_created(self):
		for name in ("Site", "Fleet Site", "GDL Site", "Vehicle Site", "Farm"):
			self.assertFalse(frappe.db.exists("DocType", name), f"{name} should not exist")

	def test_location_remains_standard(self):
		self.assertEqual(frappe.db.get_value("DocType", "Location", "module"), "Assets")
		self.assertEqual(
			frappe.get_all("Custom Field", filters={"dt": "Location", "module": "GDL Fleet"}),
			[],
			"Location must not be customised by this app",
		)

	# --- the approved tree ----------------------------------------------------
	def test_tree_exists_exactly_as_approved(self):
		for name, spec in APPROVED_TREE.items():
			self.assertTrue(frappe.db.exists("Location", name), f"missing Location {name}")
			row = frappe.db.get_value(
				"Location", name, ["parent_location", "is_group"], as_dict=True
			)
			self.assertEqual(row.parent_location, spec["parent"], f"{name} parent")
			self.assertEqual(int(row.is_group), spec["is_group"], f"{name} is_group")

	def test_nested_set_is_valid(self):
		"""lft/rgt must nest, otherwise roll-up reporting silently breaks."""
		gdl = frappe.db.get_value("Location", "GDL", ["lft", "rgt"], as_dict=True)
		farms = frappe.db.get_value("Location", "Farms", ["lft", "rgt"], as_dict=True)
		self.assertLess(gdl.lft, farms.lft)
		self.assertGreater(gdl.rgt, farms.rgt)

		for farm in ("Jamjee Farm", "Dochula Farm", "Dagapela Farm", "Gedu",
		             "Samcholing", "Jigmeling"):
			row = frappe.db.get_value("Location", farm, ["lft", "rgt"], as_dict=True)
			self.assertLess(farms.lft, row.lft, f"{farm} outside Farms")
			self.assertGreater(farms.rgt, row.rgt, f"{farm} outside Farms")

	def test_descendant_lookup_returns_all_farms(self):
		"""This is what makes 'all farms' a single report filter."""
		from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
			get_dimension_with_children,
		)

		children = get_dimension_with_children("Location", "Farms")
		for farm in ("Jamjee Farm", "Gedu", "Jigmeling"):
			self.assertIn(farm, children)
		self.assertNotIn("Head Office", children)

	def test_no_stray_locations(self):
		"""Test-runner fixtures must not pollute the site dropdown."""
		everything = set(frappe.get_all("Location", pluck="name"))
		self.assertEqual(
			everything - set(APPROVED_TREE),
			set(),
			"unexpected Location records - run the cleanup in the test guide",
		)

	# --- reachability from fleet documents -----------------------------------
	def test_every_fleet_doctype_can_reference_a_site(self):
		for doctype, fieldname in SITE_FIELDS.items():
			if not fieldname:
				continue
			field = frappe.get_meta(doctype).get_field(fieldname)
			self.assertTrue(field, f"{doctype} has no `{fieldname}` field")
			self.assertEqual(
				field.options, "Location", f"{doctype}.{fieldname} does not point at Location"
			)

	def test_maintenance_reaches_its_site_through_the_vehicle(self):
		for doctype in ("Asset Repair", "Asset Maintenance Log"):
			self.assertEqual(
				frappe.get_meta(doctype).get_field("vehicle").options, "Vehicle"
			)

	# --- validation -----------------------------------------------------------
	def test_group_location_rejected_as_a_site(self):
		from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle

		vehicle = new_vehicle(site="Farms")
		self.assertRaises(frappe.ValidationError, vehicle.insert)

	def test_leaf_location_accepted(self):
		from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle

		vehicle = new_vehicle(site="Samcholing")
		vehicle.insert()
		self.assertEqual(vehicle.site, "Samcholing")
