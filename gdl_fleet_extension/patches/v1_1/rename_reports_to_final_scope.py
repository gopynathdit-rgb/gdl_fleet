"""Rename the reports to the names used in Fleet Mgmt.docx section 5.

A Script Report resolves its Python module from `scrub(report_name)`, so the
record has to be renamed rather than recreated - otherwise the old record
would keep pointing at a folder that no longer exists.

"Vehicle Cost Per KM" is dropped: section 5 does not list it, and "Cost by
Vehicle" already reports cost per km.
"""

import frappe

RENAMES = {
	"Maintenance Due": "Service Due",
	"Maintenance Cost": "Service History",
	"Vehicle Cost Analysis": "Cost by Vehicle",
	"Fuel Consumption and Efficiency": "Fuel Consumption and Performance",
}

DROPPED = ("Vehicle Cost Per KM",)


def execute():
	for old, new in RENAMES.items():
		if not frappe.db.exists("Report", old):
			continue
		if frappe.db.exists("Report", new):
			# migrate already re-imported the renamed file; retire the old record
			frappe.delete_doc("Report", old, force=True, ignore_permissions=True)
			continue
		frappe.rename_doc("Report", old, new, force=True)

	for name in DROPPED:
		if frappe.db.exists("Report", name):
			frappe.delete_doc("Report", name, force=True, ignore_permissions=True)

	frappe.db.commit()
