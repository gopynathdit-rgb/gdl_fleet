"""Drop maintenance rules that the final scope document does not list.

Fleet Mgmt.docx section 4.4 names twelve maintenance items. An earlier seed
also created a bare "Tyre" rule, which the document covers as "Tyre
replacement / rotation". The duplicate is removed only when the replacement
rule is actually present, so a site that has renamed or re-tuned its rules
keeps whatever it configured.

The "Tyre" Vehicle Service Item master is left alone - it ships with HRMS and
is not ours to delete.
"""

import frappe

# retired rule -> the rule in section 4.4 that supersedes it
SUPERSEDED = {"Tyre": "Tyre Replacement / Rotation"}


def execute():
	settings = frappe.get_single("GDL Fleet Settings")
	rows = settings.get("maintenance_rules") or []
	present = {row.service_item for row in rows}

	drop = {
		retired
		for retired, replacement in SUPERSEDED.items()
		if retired in present and replacement in present
	}
	if not drop:
		return

	kept = [row for row in rows if row.service_item not in drop]
	settings.set("maintenance_rules", [])
	for row in kept:
		settings.append(
			"maintenance_rules",
			{
				"service_item": row.service_item,
				"vehicle_type": row.vehicle_type,
				"interval_km": row.interval_km,
				"interval_months": row.interval_months,
				"maintenance_type": row.maintenance_type,
				"is_active": row.is_active,
				"description": row.description,
			},
		)
	settings.flags.ignore_permissions = True
	settings.save()
	frappe.db.commit()
