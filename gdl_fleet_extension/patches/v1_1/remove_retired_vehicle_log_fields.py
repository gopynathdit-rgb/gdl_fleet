# Copyright (c) 2026, GDL and contributors
"""
Fields on Vehicle Log that the final scope replaced.

`booking` pointed at the old request document; Fleet Mgmt.docx section 4.3 links
the daily record to a Movement Order instead. Changing the field definition does
not remove the Custom Field already created on the site, so it is dropped here.
"""

import frappe

RETIRED = {
	"Vehicle Log": ["booking"],
}


def execute():
	for doctype, fieldnames in RETIRED.items():
		for fieldname in fieldnames:
			name = frappe.db.get_value(
				"Custom Field",
				{"dt": doctype, "fieldname": fieldname, "module": "GDL Fleet"},
				"name",
			)
			if name:
				frappe.delete_doc("Custom Field", name, force=1, ignore_permissions=True)
		frappe.clear_cache(doctype=doctype)
	frappe.db.commit()
