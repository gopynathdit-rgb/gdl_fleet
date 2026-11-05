# Copyright (c) 2026, GDL and contributors
"""
Vehicle Type configuration, ready for GDL's real list.

Nothing is seeded automatically: the list is GDL's to supply, and guessing it
would put wrong master data in front of users. Call `seed_vehicle_types()` with
the real rows when they arrive.
"""

import frappe

# Shape: (vehicle_type_name, default_seating_capacity, default_fuel_type, requires_driver)
# Left empty deliberately - fill from the customer's list.
GDL_VEHICLE_TYPES: list[tuple] = []


@frappe.whitelist()
def seed_vehicle_types(rows=None) -> dict:
	"""Create any missing Fleet Vehicle Type. Never edits an existing one.

	`rows` accepts the tuple shape above, or a list of dicts, or defaults to
	GDL_VEHICLE_TYPES.
	"""
	frappe.has_permission("Fleet Vehicle Type", "create", throw=True)

	rows = rows or GDL_VEHICLE_TYPES
	if isinstance(rows, str):
		import json

		rows = json.loads(rows)

	created, skipped = [], []

	for row in rows:
		if isinstance(row, dict):
			values = dict(row)
		else:
			name, seats, fuel, requires_driver = (list(row) + [None, None, 1])[:4]
			values = {
				"vehicle_type_name": name,
				"default_seating_capacity": seats,
				"default_fuel_type": fuel,
				"requires_driver": requires_driver,
			}

		name = values.get("vehicle_type_name")
		if not name:
			continue

		if frappe.db.exists("Fleet Vehicle Type", name):
			skipped.append(name)
			continue

		doc = frappe.get_doc({"doctype": "Fleet Vehicle Type", **values})
		doc.flags.ignore_permissions = True
		doc.insert()
		created.append(name)

	return {"created": created, "skipped_existing": skipped}


@frappe.whitelist()
def vehicle_type_readiness() -> dict:
	"""Is the fleet ready to accept vehicles? Vehicle Type is mandatory."""
	types = frappe.get_all(
		"Fleet Vehicle Type", fields=["name", "disabled"], order_by="name"
	)
	unassigned = frappe.get_all(
		"Vehicle",
		filters={"vehicle_type": ("in", ("", None))},
		fields=["name", "gdl_vehicle_id", "make", "model"],
	)

	return {
		"configured_types": [t.name for t in types if not t.disabled],
		"disabled_types": [t.name for t in types if t.disabled],
		"vehicles_without_a_type": unassigned,
		"ready": bool(types) and not unassigned,
	}
