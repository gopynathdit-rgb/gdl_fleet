# Copyright (c) 2026, GDL and contributors
"""The supply memo is attached to each POL line, not to the abstract.

GDL, circling the Supplier Bill Attachment at the top: "remove this here" -
and beside the entries table: "Add Attachment in every line item and also need
preview option in the attachment field".

One abstract covers several memos from more than one provider, so a single
file at the top could only ever evidence one of them.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle


class TestTheBillBelongsToTheLine(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(last_odometer=1000)
		self.vehicle.insert()

	def abstract(self, line_attachments, abstract_attachment=None, status="Draft"):
		doc = frappe.get_doc({
			"doctype": "POL Abstract",
			"vehicle": self.vehicle.name,
			"abstract_date": nowdate(),
			"period_from": nowdate(), "period_to": nowdate(),
			"opening_km": 1000, "closing_km": 1100,
			"deviation_reason": "test",
			"supplier_bill_attachment": abstract_attachment,
			"status": status,
			"entries": [
				{"supply_memo_no": f"M{i}", "date": nowdate(), "supplier": "BOD",
				 "litres": 10, "rate": 100, "odometer": 1000 + i,
				 "bill_attachment": attachment}
				for i, attachment in enumerate(line_attachments, start=1)
			],
		})
		doc.flags.ignore_permissions = True
		return doc

	# --- the field is there, and on the grid -----------------------------
	def test_every_line_can_carry_a_bill(self):
		field = frappe.get_meta("POL Entry").get_field("bill_attachment")
		self.assertIsNotNone(field, "POL Entry has no attachment field")
		self.assertEqual(field.fieldtype, "Attach")

	def test_it_shows_in_the_grid_so_it_can_be_opened(self):
		"""In the row itself, not buried behind the edit pencil - that is the
		"preview option" GDL asked for."""
		self.assertTrue(frappe.get_meta("POL Entry").get_field("bill_attachment").in_list_view)

	def test_the_abstract_level_field_is_off_the_form(self):
		field = frappe.get_meta("POL Abstract").get_field("supplier_bill_attachment")
		self.assertIsNotNone(field, "the old field was deleted rather than hidden")
		self.assertTrue(field.hidden)

	# --- the rule now reads the lines ------------------------------------
	def test_a_draft_is_never_blocked(self):
		"""You collect the memos as you go."""
		self.abstract([None, None]).insert()

	def test_sending_for_approval_without_the_memos_is_refused(self):
		doc = self.abstract([None, None], status="Submitted")
		with self.assertRaises(frappe.ValidationError) as cm:
			doc.insert()
		self.assertIn("each POL entry", str(cm.exception))

	def test_the_refusal_names_the_rows_still_missing(self):
		"""Two rows, one attached - the message must point at the other."""
		doc = self.abstract(["/files/memo-1.pdf", None], status="Submitted")
		with self.assertRaises(frappe.ValidationError) as cm:
			doc.insert()
		message = str(cm.exception)
		self.assertIn("row 2", message.lower())
		self.assertNotIn("row 1", message.lower())

	def test_every_line_attached_goes_through(self):
		doc = self.abstract(["/files/memo-1.pdf", "/files/memo-2.pdf"],
		                    status="Submitted")
		doc.insert()
		self.assertEqual(doc.status, "Submitted")

	def test_an_abstract_attached_the_old_way_is_not_reopened(self):
		"""Records evidenced before the field moved must not be sent back to
		be re-attached line by line."""
		doc = self.abstract([None, None], abstract_attachment="/files/old-bill.pdf",
		                    status="Submitted")
		doc.insert()
		self.assertEqual(doc.status, "Submitted")

	def test_the_rule_can_still_be_switched_off(self):
		"""It is configuration, not a hard-coded policy."""
		from gdl_fleet_extension.gdl_fleet.doctype.pol_abstract.pol_abstract import (
			get_pol_setting,
		)
		settings = frappe.get_single("GDL Fleet Settings")
		original = settings.get("pol_abstract_requires_attachment")
		try:
			settings.pol_abstract_requires_attachment = 0
			settings.flags.ignore_permissions = True
			settings.save()
			frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
			self.abstract([None, None], status="Submitted").insert()
		finally:
			settings.pol_abstract_requires_attachment = original
			settings.flags.ignore_permissions = True
			settings.save()
			frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
