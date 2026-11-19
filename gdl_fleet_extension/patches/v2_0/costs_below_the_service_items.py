# Copyright (c) 2026, GDL and contributors
"""Move Labour / Parts / Total Cost below the Service Items table.

GDL, with an arrow drawn from the three cost fields down to the table:
"need update below this fields".

Parts Cost is totalled FROM those rows, so reading the rows first and their
totals underneath is the order the form is actually filled in.

create_custom_fields() updates a field it already finds, so a fresh install
gets this from setup/maintenance_fields.py. This moves the sites already
running.
"""

import frappe

DOCTYPE = "Asset Maintenance Log"
# fieldname -> what it must now sit after
CHAIN = {
	"cost_center": "gdl_service_cb",
	"gdl_cost_section": "service_items",
	"gdl_cost_cb": "gdl_cost_section",
	"labour_cost": "gdl_cost_cb",
	"parts_cost": "labour_cost",
	"total_cost": "parts_cost",
	"gdl_vehicle_cb": "vehicle",
	"location": "gdl_vehicle_cb",
}


def execute():
	moved = []
	for fieldname, after in CHAIN.items():
		name = frappe.db.get_value(
			"Custom Field", {"dt": DOCTYPE, "fieldname": fieldname}, "name")
		if not name:
			continue
		if frappe.db.get_value("Custom Field", name, "insert_after") == after:
			continue
		frappe.db.set_value("Custom Field", name, "insert_after", after)
		moved.append(fieldname)

	if moved:
		frappe.clear_cache(doctype=DOCTYPE)
		frappe.db.commit()
		print(f"  Moved {', '.join(moved)} below the Service Items table.")
