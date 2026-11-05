# Copyright (c) 2026, GDL and contributors
"""
Client decisions of 3 November 2026:

  - "User will apply, manager will approve, and create Movement order."
    -> the Movement Order approval chain becomes Simple.
  - "create a user and a manager (MTO location wise) ... final MTO will be at
    head office." -> approval is restricted to the location's own MTO.
  - "their requirement is in 14 day ... Or 14 and 3 days."
    -> renewal reminders at 14 days, 3 days and on the expiry day.

A default on a Check or Select field in a Single's JSON only applies when that
Single is FIRST created. Every site that already had GDL Fleet Settings keeps
the old value, so the defaults have to be written once, here.

Only values the site still holds at the OLD default are changed. A site where
someone has already chosen something different keeps their choice - a patch
that overwrites a deliberate setting is a bug, not a migration.
"""

import frappe

# fieldname: (value to write, the old default it is allowed to replace)
SETTINGS = {
	"movement_approval_chain": ("Simple", (None, "", "Full (Five Stage)")),
	"enforce_location_mto": (1, (None, "", 0, "0")),
	"renewal_notice_days": (14, (None, "", 30, "30")),
	"renewal_second_reminder_days": (3, (None, "", 15, "15")),
	"renewal_third_reminder_days": (0, (None, "", 7, "7")),
	"renewal_final_reminder_days": (0, (None, "", 3, "3")),
}


def execute():
	if not frappe.db.exists("DocType", "GDL Fleet Settings"):
		return

	settings = frappe.get_single("GDL Fleet Settings")
	changed = []

	for fieldname, (value, replaceable) in SETTINGS.items():
		if not settings.meta.get_field(fieldname):
			continue
		current = settings.get(fieldname)
		if current not in replaceable:
			print(f"  keeping {fieldname} = {current!r} (set deliberately)")
			continue
		settings.set(fieldname, value)
		changed.append(f"{fieldname}={value!r}")

	if not changed:
		return

	settings.flags.ignore_permissions = True
	settings.flags.ignore_validate = True
	settings.save()
	frappe.db.commit()
	print("  GDL Fleet Settings: " + ", ".join(changed))

	# The workflow is built from this setting, so it has to be rebuilt now
	# rather than waiting for the next migrate.
	from gdl_fleet_extension.setup.workflows import create_movement_order_workflow

	create_movement_order_workflow()
	frappe.db.commit()
	print("  Movement Order workflow rebuilt on the Simple chain.")
