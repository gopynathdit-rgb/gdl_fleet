"""Seed the POL defaults once on sites that already have GDL Fleet Settings.

The Check defaults in the DocType JSON only apply when a record is created, and
the Settings single already exists here, so the new POL fields came through as
0. They are set once by this patch rather than by the idempotent seeder: the
seeder runs on every migrate and could not tell "never configured" from
"GDL deliberately switched this off".
"""

import frappe

DEFAULTS = {
	"pol_performance_precision": 2,
	"pol_enforce_unique_supply_memo": 1,
	"pol_carry_forward_opening_km": 1,
	"pol_carry_forward_tank_balance": 1,
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
