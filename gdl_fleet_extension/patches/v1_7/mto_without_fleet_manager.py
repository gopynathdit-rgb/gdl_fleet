# Copyright (c) 2026, GDL and contributors
"""
OBS-005: a location MTO should not see what every vehicle cost.

The seven MTO accounts were created holding Fleet Approver, Fleet User AND
Fleet Manager. Fleet Manager is a STANDARD ERPNext role with broad access, so
every MTO could read vehicle values, service costs and the whole purchasing
trail - which is not what approving a vehicle request requires.

Removing it alone would have gone too far the other way: Fleet Approver was on
none of the eighteen fleet reports and could not manage renewals, so an MTO
would have lost Movement Request Status and Vehicle Availability - the two
screens the handbook tells them to start from. Those rights are granted to
Fleet Approver in its own right (report JSONs, Renewal Register, and
setup/fleet_permissions.py), and this patch then takes Fleet Manager away.

Only accounts that hold BOTH Fleet Approver and Fleet Manager are touched, and
only the Fleet Manager row is removed. A person who holds Fleet Manager for
some other reason is left alone.
"""

import frappe


def execute():
	if not frappe.db.exists("Role", "Fleet Manager"):
		return

	# An MTO is identified by what it holds, never by its email address.
	candidates = set(frappe.get_all(
		"Has Role", filters={"role": "Fleet Approver", "parenttype": "User"}, pluck="parent"
	)) & set(frappe.get_all(
		"Has Role", filters={"role": "Fleet Manager", "parenttype": "User"}, pluck="parent"
	))

	removed = []
	for user in sorted(candidates):
		if not frappe.db.exists("User", user):
			continue

		doc = frappe.get_doc("User", user)
		keep = [r for r in doc.get("roles") or [] if r.role != "Fleet Manager"]
		if len(keep) == len(doc.get("roles") or []):
			continue

		doc.set("roles", [])
		for row in keep:
			doc.append("roles", {"role": row.role})
		doc.flags.ignore_permissions = True
		doc.save()
		removed.append(user)

	if removed:
		frappe.db.commit()
		frappe.clear_cache()
		print(f"  Fleet Manager removed from {len(removed)} MTO account(s).")
		print("  They keep Fleet Approver and Fleet User, which now carry the")
		print("  report and renewal rights they need.")
