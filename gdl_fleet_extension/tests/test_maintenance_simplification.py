# Copyright (c) 2026, GDL and contributors
"""The simple service record.

Final document 2.1.1.4 lists what a service record holds. These tests read the
form the way a workshop clerk meets it and check two things: everything that
section names is on it, and nothing else is.
"""

import frappe
from frappe.tests import IntegrationTestCase

from gdl_fleet_extension.setup.maintenance_simplification import (
	ERPNEXT_SCAFFOLDING,
	PURCHASING_CYCLE,
)

DOCTYPE = "Asset Maintenance Log"

# Section 2.1.1.4, field for field.
THE_DOCUMENT_ASKS_FOR = {
	"vehicle": "Vehicle",
	"location": "Location",
	"completion_date": "Service Date",
	"odometer": "Odometer Reading",
	"service_items": "Service Type / Parts used - one row per item",
	"service_provider": "Service Provider",
	"actions_performed": "Service Description",
	"labour_cost": "Labour/Service Cost",
	"parts_cost": "Parts cost, which totals with labour",
	"total_cost": "Total Cost",
	"bill_no": "Invoice/Reference No",
	"next_due_date": "next service date",
	"next_due_odometer": "next service odometer",
	"cost_center": "Cost Center",
	"project": "Project",
}


class TestTheFormMatchesTheDocument(IntegrationTestCase):
	def setUp(self):
		self.meta = frappe.get_meta(DOCTYPE)

	def test_every_field_the_document_names_is_on_the_form(self):
		for fieldname, why in THE_DOCUMENT_ASKS_FOR.items():
			field = self.meta.get_field(fieldname)
			self.assertIsNotNone(field, f"{fieldname} is missing - the document asks for {why}")
			self.assertFalse(field.hidden, f"{fieldname} is hidden - the document asks for {why}")

	def test_the_erpnext_scaffolding_is_off_the_form(self):
		"""Asset Maintenance, Task, Periodicity, Certificate and the rest.

		A maintenance plan fills them. A clerk recording an oil change cannot.
		"""
		for fieldname in ERPNEXT_SCAFFOLDING:
			field = self.meta.get_field(fieldname)
			if field:
				self.assertTrue(field.hidden, f"{fieldname} is still on the form")

	def test_the_purchasing_cycle_is_off_the_form(self):
		"""The document asks for an Invoice/Reference No, not a procurement chain."""
		for fieldname in PURCHASING_CYCLE:
			field = self.meta.get_field(fieldname)
			if field:
				self.assertTrue(field.hidden, f"{fieldname} is still on the form")

	def test_nothing_was_deleted(self):
		"""Hidden, not dropped - ACC-AML records already carry these values, and
		the purchasing code still reads them."""
		for fieldname in ERPNEXT_SCAFFOLDING + PURCHASING_CYCLE:
			if fieldname.startswith(("column_break", "gdl_")):
				continue
			self.assertIsNotNone(self.meta.get_field(fieldname),
			                     f"{fieldname} must be hidden, never deleted")

	def test_no_more_than_the_document_asks_for_is_visible(self):
		"""The one that actually keeps the form simple.

		A field added later shows up here and has to be justified against the
		document or hidden, instead of quietly joining the form.
		"""
		allowed = set(THE_DOCUMENT_ASKS_FOR) | {
			"naming_series", "maintenance_status", "amended_from",
			"bill_date", "bill_attachment",       # the invoice the number refers to
			"driver", "driver_employee",          # who took the vehicle in
		}
		visible = {f.fieldname for f in self.meta.fields
		           if not f.hidden
		           and f.fieldtype not in ("Section Break", "Column Break", "Tab Break")}
		self.assertEqual(visible - allowed, set())

	def test_the_vehicle_is_required(self):
		"""Without one the record joins no service history and no due list."""
		self.assertTrue(self.meta.get_field("vehicle").reqd)

	def test_the_form_uses_the_document_s_words(self):
		for fieldname, label in (("odometer", "Odometer Reading"),
		                         ("actions_performed", "Service Description"),
		                         ("bill_no", "Invoice / Reference No")):
			self.assertEqual(self.meta.get_field(fieldname).label, label)

	def test_the_service_line_names_the_service_type(self):
		meta = frappe.get_meta("Fleet Service Item")
		self.assertEqual(meta.get_field("service_item").label, "Service Type")
		self.assertEqual(meta.get_field("part_brand").label, "Part / Material Used")

	def test_the_invoice_number_is_asked_for_once(self):
		"""It was on the record and on every line. One is the document's answer."""
		self.assertTrue(frappe.get_meta("Fleet Service Item").get_field("invoice_reference").hidden)


class TestPurchasingIsStoodDown(IntegrationTestCase):
	"""Hiding a cycle that still runs would be worse than leaving it visible."""

	def test_the_switch_is_off_on_this_site(self):
		"""Reads what the site holds, not what a fixture sets - the shape of bug
		that let maintenance_bill_requires_attachment sit at 0 unnoticed."""
		self.assertFalse(
			frappe.db.get_single_value("GDL Fleet Settings", "maintenance_po_on_completion"),
			"purchasing on completion is still on - patches/v1_9 did not run",
		)

	def test_no_record_is_left_waiting_on_a_purchase_order(self):
		self.assertEqual(
			frappe.get_all("Asset Maintenance Log",
			               filters={"purchasing_status": "Pending"}, limit=1), [],
			"a completed service is still stuck at Purchasing: Pending",
		)

	def test_the_code_is_still_there_for_the_day_gdl_wants_it(self):
		from gdl_fleet_extension.overrides import asset_maintenance
		self.assertTrue(hasattr(asset_maintenance, "maintenance_log_purchasing"))
