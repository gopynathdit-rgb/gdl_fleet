"""Seed the thresholds the 25-Sept final document introduces.

Set once, not by the idempotent seeder: the seeder runs on every migrate and
could not tell "never configured" from "GDL deliberately set it to this".
"""

import frappe

DEFAULTS = {
	# Optimal Fleet Utilization - GDL confirmed +/-10% applies in BOTH directions
	"mileage_deviation_tolerance": 10,
	"mileage_requires_hr_approval": 1,
	# Tire Mileage - 20,000 km +/-20%
	"tyre_target_km": 20000,
	"tyre_tolerance": 20,
	# OFMS booking rules
	"booking_lead_time_hours": 24,
	"booking_lead_time_action": "Require Reason",
	"emergency_bypasses_lead_time": 1,
}


def execute():
	settings = frappe.get_single("GDL Fleet Settings")
	changed = False
	for fieldname, value in DEFAULTS.items():
		if settings.meta.get_field(fieldname) and not settings.get(fieldname):
			settings.set(fieldname, value)
			changed = True
	if changed:
		settings.flags.ignore_permissions = True
		settings.save()
		frappe.db.commit()
