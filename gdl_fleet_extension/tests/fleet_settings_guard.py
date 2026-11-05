# Copyright (c) 2026, GDL and contributors
"""
Keep tests from leaving their settings behind.

Several suites flip switches in GDL Fleet Settings to exercise a rule. Writing
those with `frappe.db.set_single_value` reaches straight past the test
transaction, so a value changed in a test stayed changed on the site - which is
how `maintenance_bill_requires_attachment` ended up switched off in real use
and let a bill through with no attachment.

Mix this in and every field the test touches is put back as it was, whether the
test passes, fails or raises.
"""

import frappe


class FleetSettingsGuard:
	"""Snapshot the settings on setUp, restore them on tearDown."""

	#: fields a suite intends to change; empty means "whatever it touches"
	guarded_settings: tuple[str, ...] = ()

	def setUp(self):
		super().setUp()
		self._settings_snapshot = self._read_settings()

	def tearDown(self):
		self._restore_settings()
		super().tearDown()

	# ------------------------------------------------------------------
	def _settings_fields(self):
		if self.guarded_settings:
			return self.guarded_settings
		meta = frappe.get_meta("GDL Fleet Settings")
		return tuple(
			f.fieldname for f in meta.fields
			if f.fieldtype not in ("Section Break", "Column Break", "Table", "HTML")
		)

	def _read_settings(self):
		doc = frappe.get_single("GDL Fleet Settings")
		return {field: doc.get(field) for field in self._settings_fields()}

	def _restore_settings(self):
		changed = False
		for field, original in (getattr(self, "_settings_snapshot", None) or {}).items():
			if frappe.db.get_single_value("GDL Fleet Settings", field) != original:
				frappe.db.set_single_value("GDL Fleet Settings", field, original)
				changed = True
		if changed:
			frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def set_fleet_setting(self, field, value):
		"""Change a setting for the duration of this test."""
		frappe.db.set_single_value("GDL Fleet Settings", field, value)
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
