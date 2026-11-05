# Copyright (c) 2026, GDL and contributors
"""
Fleet Mgmt.docx 4.1 defines Vehicle Status as Active / Under Maintenance /
Unavailable / Disposed.

Reserved and In Use were part of the earlier design. Section 5 asks for booked
status in the Vehicle Availability report instead, which is derived from
Movement Orders rather than stored on the vehicle.
"""

import frappe

MAPPING = {
	"Available": "Active",
	"Reserved": "Active",
	"In Use": "Active",
	"Sold / Disposed": "Disposed",
}


def execute():
	if not frappe.db.exists("DocType", "Vehicle"):
		return

	for old, new in MAPPING.items():
		frappe.db.sql(
			"update `tabVehicle` set vehicle_status = %(new)s where vehicle_status = %(old)s",
			{"old": old, "new": new},
		)
	frappe.db.commit()
