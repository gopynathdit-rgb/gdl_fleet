# Copyright (c) 2026, GDL and contributors
"""
Read-only pre-flight checks for the two site-wide changes this app deliberately
does NOT make on its own.

Nothing in this module writes. Each function reports what a change would affect
so the decision is made on evidence rather than on trust.
"""

import frappe
from frappe.utils import cint

SPARE_WORKFLOW = "GDL Spare Part Approval"


# ----------------------------------------------------------------------
# 1. Activating the spare-part workflow
# ----------------------------------------------------------------------
@frappe.whitelist()
def check_spare_workflow_activation() -> dict:
	"""What activating the Material Request workflow would affect.

	A frappe Workflow is bound to a DocType, not to a filter - `get_workflow_name`
	looks up only (document_type, is_active). So activation is unavoidably
	site-wide, and the desk hides Submit for every Material Request. The bypass
	transitions are what keep ordinary requests working.
	"""
	workflow_exists = frappe.db.exists("Workflow", SPARE_WORKFLOW)
	is_active = (
		cint(frappe.db.get_value("Workflow", SPARE_WORKFLOW, "is_active"))
		if workflow_exists
		else 0
	)

	total = frappe.db.count("Material Request")
	fleet = frappe.db.count("Material Request", {"fleet_request_type": ("is", "set")})
	drafts = frappe.db.count("Material Request", {"docstatus": 0})
	non_fleet_drafts = frappe.db.count(
		"Material Request", {"docstatus": 0, "fleet_request_type": ("in", ("", None))}
	)

	bypass_roles = []
	fleet_roles = []
	if workflow_exists:
		workflow = frappe.get_doc("Workflow", SPARE_WORKFLOW)
		for row in workflow.transitions:
			if row.condition == "not doc.fleet_request_type":
				bypass_roles.append(row.allowed)
			else:
				fleet_roles.append(row.allowed)

	# Roles that can submit a Material Request today but have no bypass path.
	submitters = {
		p.role
		for p in frappe.get_meta("Material Request").permissions
		if p.submit and p.permlevel == 0
	}
	unprotected = sorted(submitters - set(bypass_roles))

	return {
		"workflow_exists": bool(workflow_exists),
		"is_active": bool(is_active),
		"material_requests_total": total,
		"material_requests_fleet": fleet,
		"material_requests_non_fleet": total - fleet,
		"open_drafts_total": drafts,
		"open_drafts_non_fleet": non_fleet_drafts,
		"bypass_roles": sorted(set(bypass_roles)),
		"fleet_roles": sorted(set(fleet_roles)),
		"roles_that_submit_today_without_bypass": unprotected,
		"safe_to_activate": not unprotected,
		"note": (
			"A frappe Workflow cannot be limited to a subset of documents. Once "
			"active it governs every Material Request and the desk replaces the "
			"Submit button with workflow actions. Server-side doc.submit() calls "
			"still work. Ordinary requests keep a one-click path only through the "
			"bypass transitions listed above."
		),
	}


# ----------------------------------------------------------------------
# 2. Enabling serial / batch tracking
# ----------------------------------------------------------------------
@frappe.whitelist()
def check_serial_batch_activation() -> dict:
	"""Exactly what enabling `enable_serial_and_batch_no_for_item` would touch."""
	enabled = cint(
		frappe.db.get_single_value("Stock Settings", "enable_serial_and_batch_no_for_item")
	)
	user_default = frappe.db.get_value(
		"DefaultValue",
		{"defkey": "enable_serial_and_batch_no_for_item", "parent": "__default"},
		"defvalue",
	)

	serial_items = frappe.get_all(
		"Item", filters={"has_serial_no": 1}, fields=["name", "disabled"]
	)
	batch_items = frappe.get_all(
		"Item", filters={"has_batch_no": 1}, fields=["name", "disabled"]
	)

	tracked = {i.name for i in serial_items} | {i.name for i in batch_items}
	affected_sle = 0
	if tracked:
		affected_sle = frappe.db.count(
			"Stock Ledger Entry", {"item_code": ("in", list(tracked)), "is_cancelled": 0}
		)

	submitted_bundles = frappe.db.count("Serial and Batch Bundle", {"docstatus": 1})

	return {
		"currently_enabled": bool(enabled),
		"user_default": user_default,
		"serial_tracked_items": [i.name for i in serial_items],
		"batch_tracked_items": [i.name for i in batch_items],
		"serial_no_records": frappe.db.count("Serial No"),
		"batch_records": frappe.db.count("Batch"),
		"serial_batch_bundles": frappe.db.count("Serial and Batch Bundle"),
		"submitted_bundles": submitted_bundles,
		"stock_ledger_entries_total": frappe.db.count("Stock Ledger Entry", {"is_cancelled": 0}),
		"stock_ledger_entries_on_tracked_items": affected_sle,
		"reversible": submitted_bundles == 0,
		"note": (
			"The flag only affects items already marked has_serial_no or "
			"has_batch_no. Items without those flags are untouched. No existing "
			"ledger entry, valuation or GL entry is rewritten. Once a submitted "
			"Serial and Batch Bundle exists the flag can no longer be switched "
			"off (erpnext stock_settings.validate_serial_and_batch_no_settings)."
		),
	}
