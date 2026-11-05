# Copyright (c) 2026, GDL and contributors
"""
DEF-001: move the money and the approval trail above a Fleet Driver's reach.

`create_custom_fields()` creates fields that are missing and leaves fields that
already exist exactly as they are. Every field below already exists on every
installed site, so the permlevel added to the setup dicts reaches a fresh
install and nothing else. This applies it once to what is already there.

Level 1 is money - the supplier, the costs, the bill and where it is charged.
Level 2 is the decision trail - who submitted, who approved, and what it became
in the purchase ledger. Almost all of level 2 is already read-only and written
by code through frappe.db.set_value, which bypasses field permissions, so level
2 is defence in depth rather than the primary control.

Asset Repair is deliberately absent: it carries `service_provider` and
`labour_cost` too, but the approved permission matrix grants no level-1 row on
that DocType, so raising those fields would hide them from everyone.
"""

import frappe

PERMLEVELS = {
	"Asset Maintenance Log": {
		1: [
			"service_provider", "labour_cost", "parts_cost", "total_cost",
			"bill_no", "bill_date", "bill_attachment", "cost_center", "project",
		],
		2: [
			"bill_status", "submitted_by", "submission_date", "approved_by",
			"rejection_reason", "purchase_order", "purchase_invoice",
			"purchasing_status", "purchasing_message", "payment_status",
		],
	},
	"Vehicle": {
		1: ["asset", "lessor"],
	},
}


def execute():
	changed, missing = [], []

	for doctype, levels in PERMLEVELS.items():
		if not frappe.db.exists("DocType", doctype):
			continue

		for permlevel, fieldnames in levels.items():
			for fieldname in fieldnames:
				name = frappe.db.get_value(
					"Custom Field", {"dt": doctype, "fieldname": fieldname}, "name"
				)
				if not name:
					missing.append(f"{doctype}.{fieldname}")
					continue

				if frappe.db.get_value("Custom Field", name, "permlevel") == permlevel:
					continue

				frappe.db.set_value("Custom Field", name, "permlevel", permlevel)
				changed.append(f"{doctype}.{fieldname} -> {permlevel}")

	if changed:
		frappe.clear_cache()
		frappe.db.commit()
		print(f"  Raised the permission level of {len(changed)} field(s).")
	if missing:
		print(f"  Not present on this site, skipped: {missing}")
