# Copyright (c) 2026, GDL and contributors
"""Fill in the next service due on services already recorded.

Next due was only ever computed for a service raised from an ERPNext Asset
Maintenance PLAN. GDL has none and cannot have any - a plan needs an Asset and
no vehicle is linked to one - so every service recorded so far carries a blank
next due, and Service Due has never had anything to list.

Recomputes them from the Maintenance Rules. Only records with no next due are
touched, so anything already scheduled is left exactly as it is.
"""

import frappe

DOCTYPE = "Asset Maintenance Log"


def execute():
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	from gdl_fleet_extension.overrides.asset_maintenance import set_next_due_from_rules

	names = frappe.get_all(
		DOCTYPE,
		filters={"docstatus": ("<", 2), "maintenance_status": "Completed"},
		pluck="name")

	filled = 0
	for name in names:
		doc = frappe.get_doc(DOCTYPE, name)
		if doc.get("next_due_date") or doc.get("next_due_odometer"):
			continue

		set_next_due_from_rules(doc)
		if not (doc.next_due_date or doc.next_due_odometer):
			continue		# no rule matched the service types on this visit

		doc.db_set("next_due_date", doc.next_due_date, update_modified=False)
		doc.db_set("next_due_odometer", doc.next_due_odometer, update_modified=False)
		filled += 1

	if filled:
		frappe.db.commit()
		print(f"  Scheduled the next service on {filled} existing record(s).")
