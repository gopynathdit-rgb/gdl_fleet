# Copyright (c) 2026, GDL and contributors
"""Undo two defaults that reached further than they were meant to.

Defaulting maintenance_status to Completed, and making completion_date
mandatory, were both right for a driver filling the form in and both wrong for
ERPNext's own machinery. Asset Maintenance.sync_maintenance_tasks() creates an
Asset Maintenance Log for every SCHEDULED task - work that has not happened yet
and therefore has no completion date - and a DocType-level default and reqd
flag apply to those just as much as to the driver's form. Fourteen tests failed
on it; a maintenance plan could not be saved at all.

The status default now lives in the client script, where only a person opening
the form sees it. The date requirement is conditional on the status.
"""

import frappe

DOCTYPE = "Asset Maintenance Log"


def execute():
	for fieldname, prop in (("maintenance_status", "default"),
	                        ("completion_date", "reqd")):
		name = frappe.db.get_value("Property Setter", {
			"doc_type": DOCTYPE, "field_name": fieldname, "property": prop})
		if name:
			frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
			print(f"  dropped {DOCTYPE}.{fieldname} {prop} - it reached the maintenance plan too")

	frappe.clear_cache(doctype=DOCTYPE)
	frappe.db.commit()
