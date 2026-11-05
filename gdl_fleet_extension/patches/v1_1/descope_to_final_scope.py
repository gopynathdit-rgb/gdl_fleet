# Copyright (c) 2026, GDL and contributors
"""
Remove the features that are not requirements of Fleet Mgmt.docx.

The document's scope is vehicle master, driver assignment, daily KM, service,
renewals and alerts, movement request and order, POL, and the section 5 reports.
Tyre management, spare-part approval, the fleet expense module, mileage
deviation, accident/incident and site requirements are not in it.

Standard ERPNext is left completely alone: Item, Warehouse, Stock Entry,
Serial No, Asset, Cost Center, Project, the Vehicle accounting dimension,
Location, Employee and Driver all remain. Only fields and documents this app
added are removed.
"""

import frappe

DOCTYPES = [
	# child tables first
	"GDL Fleet Tyre Position",
	"GDL Fleet Mileage Norm",
	"GDL Fleet Site Requirement",
	# then the documents
	"Fleet Tyre Installation",
	"Fleet Mileage Deviation",
	"Fleet Accident Report",
]

WORKFLOWS = [
	"GDL Spare Part Approval",
	"GDL Mileage Deviation Review",
	"GDL Accident Handling",
	"GDL Vehicle Booking Approval",
]

REPORTS = [
	"Tyre Performance",
	"Accident and Incident",
	"Mileage Deviation",
	"Site Vehicle Requirement",
	"Vehicle Expense",
]

NOTIFICATIONS = [
	"GDL Fleet: Mileage Deviation Raised",
	"GDL Fleet: Spare Part Approval Pending",
	"GDL Fleet: Accident Reported",
	"GDL Fleet: Accident Pending Action",
]

# Custom fields this app added to STANDARD DocTypes for de-scoped features.
# `vehicle` is NOT listed anywhere: it belongs to the Accounting Dimension and
# is what makes section 5's "Cost by Vehicle" possible.
CUSTOM_FIELDS = {
	"Material Request": [
		"gdl_fleet_section", "fleet_request_type", "vehicle", "driver", "gdl_fleet_cb",
		"asset_repair", "asset_maintenance_log", "site", "department",
		"purpose_remarks", "workflow_state",
	],
	"Stock Entry": [
		"gdl_fleet_section", "asset_repair_reference", "asset_maintenance_log",
		"gdl_fleet_cb", "material_request_reference",
	],
	"Expense Claim": [
		"gdl_fleet_section", "driver", "site", "gdl_fleet_cb", "supplier",
		"purpose", "receipt",
	],
	"Expense Claim Detail": ["odometer"],
	"Serial No": ["is_tyre", "tyre_size", "current_vehicle"],
}


def execute():
	_delete_records_and_doctypes()
	_delete_singles(["Workflow"], WORKFLOWS)
	_delete_singles(["Report"], REPORTS)
	_delete_singles(["Notification"], NOTIFICATIONS)
	_delete_custom_fields()
	frappe.db.commit()


def _delete_records_and_doctypes():
	# developer_mode is required to delete an app-owned DocType
	frappe.conf.developer_mode = 1
	try:
		for doctype in DOCTYPES:
			if not frappe.db.exists("DocType", doctype):
				continue

			if not frappe.db.get_value("DocType", doctype, "istable"):
				for name in frappe.get_all(doctype, pluck="name"):
					try:
						doc = frappe.get_doc(doctype, name)
						if doc.docstatus == 1:
							doc.flags.ignore_permissions = True
							doc.cancel()
						frappe.delete_doc(doctype, name, force=1, ignore_permissions=True,
						                  delete_permanently=True)
					except Exception:
						frappe.db.sql(
							f"delete from `tab{doctype}` where name = %s", name
						)

			try:
				frappe.delete_doc("DocType", doctype, force=1, ignore_permissions=True)
			except Exception:
				# fall back to removing the metadata directly
				frappe.db.sql("delete from `tabDocField` where parent = %s", doctype)
				frappe.db.sql("delete from `tabDocPerm` where parent = %s", doctype)
				frappe.db.sql("delete from `tabDocType` where name = %s", doctype)
				frappe.db.sql_ddl(f"drop table if exists `tab{doctype}`")
	finally:
		frappe.conf.developer_mode = 0


def _delete_singles(doctypes, names):
	for doctype in doctypes:
		for name in names:
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)


def _delete_custom_fields():
	for doctype, fieldnames in CUSTOM_FIELDS.items():
		for fieldname in fieldnames:
			name = frappe.db.get_value(
				"Custom Field",
				{"dt": doctype, "fieldname": fieldname, "module": "GDL Fleet"},
				"name",
			)
			if name:
				frappe.delete_doc("Custom Field", name, force=1, ignore_permissions=True)
		frappe.clear_cache(doctype=doctype)
