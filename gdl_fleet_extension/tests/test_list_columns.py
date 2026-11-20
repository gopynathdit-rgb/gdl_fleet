# Copyright (c) 2026, GDL and contributors
"""What each fleet list shows without anyone configuring it.

GDL: "add ... site and Default vehicle field need to be add then In Driver
Assignment, Can u add Site, and To Date also. Can u add Location to Renewal
Register also, and Movement Order request, Movement Order".
"""

import frappe
from frappe.tests import IntegrationTestCase

# doctype -> the fields GDL asked to see in the list
ASKED_FOR = {
	"Driver": ["site", "default_vehicle"],
	"Driver Assignment": ["location", "to_date"],
	"Renewal Register": ["location"],
	"Movement Order Request": ["site"],
	"Movement Order": ["site"],
}

# frappe shows this many columns before the rest need the list's own
# settings menu - 4 under 1366px, 6 to 1920px, 10 above (list_view.js).
COLUMNS_ON_A_MEDIUM_SCREEN = 6


class TestFleetListColumns(IntegrationTestCase):
	def columns(self, doctype):
		return [f.fieldname for f in frappe.get_meta(doctype).fields if f.in_list_view]

	def test_every_asked_for_field_is_in_the_list(self):
		for doctype, fieldnames in ASKED_FOR.items():
			shown = self.columns(doctype)
			for fieldname in fieldnames:
				with self.subTest(doctype=doctype, field=fieldname):
					self.assertIn(fieldname, shown)

	def test_the_fields_exist_on_the_doctype(self):
		"""An in_list_view flag on a field that is not there shows nothing."""
		for doctype, fieldnames in ASKED_FOR.items():
			meta = frappe.get_meta(doctype)
			for fieldname in fieldnames:
				with self.subTest(doctype=doctype, field=fieldname):
					self.assertIsNotNone(meta.get_field(fieldname))

	def test_what_asked_for_lands_inside_the_visible_six(self):
		"""Columns past the limit are dropped silently, so a field asked for
		must be early enough to survive on an ordinary screen."""
		for doctype, fieldnames in ASKED_FOR.items():
			visible = self.columns(doctype)[:COLUMNS_ON_A_MEDIUM_SCREEN]
			for fieldname in fieldnames:
				with self.subTest(doctype=doctype, field=fieldname):
					self.assertIn(
						fieldname, visible,
						f"{doctype}.{fieldname} is column "
						f"{self.columns(doctype).index(fieldname) + 1} and "
						f"would be cut off below a 1920px screen")
