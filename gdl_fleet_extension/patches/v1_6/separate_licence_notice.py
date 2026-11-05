# Copyright (c) 2026, GDL and contributors
"""
OBS-002: give the driving-licence alert its own notice period.

It used to read `renewal_notice_days`, the first rung of the insurance ladder.
That coupled two unrelated things: changing the insurance reminder silently
changed the licence one, and a licence takes longer to replace than a policy
takes to renew - 14 days is not enough notice to get a driver re-licensed.

A default on an Int field in a Single's JSON only applies when that Single is
first created, so an existing site needs the value written once, here. The
existing Notification is then re-pointed at the new setting; `days_in_advance`
is the only thing touched, so any wording GDL has tuned on it survives.
"""

import frappe

FIELD = "licence_expiry_notice_days"
DEFAULT = 30
ALERT = "GDL Fleet: Driving Licence Expiry"


def execute():
	if not frappe.db.exists("DocType", "GDL Fleet Settings"):
		return

	settings = frappe.get_single("GDL Fleet Settings")
	if not settings.meta.get_field(FIELD):
		return

	# Only write it when it is genuinely unset. A site where someone has already
	# chosen a value keeps their choice - a patch that overwrites a deliberate
	# setting is a bug, not a migration.
	if settings.get(FIELD) in (None, ""):
		settings.set(FIELD, DEFAULT)
		settings.flags.ignore_permissions = True
		settings.flags.ignore_validate = True
		settings.save()
		frappe.db.commit()
		print(f"  Driving licence notice set to {DEFAULT} days, independent of the renewal ladder.")

	wanted = frappe.utils.cint(settings.get(FIELD))
	if not frappe.db.exists("Notification", ALERT):
		return

	current = frappe.utils.cint(frappe.db.get_value("Notification", ALERT, "days_in_advance"))
	if wanted and current != wanted:
		frappe.db.set_value("Notification", ALERT, "days_in_advance", wanted,
		                    update_modified=False)
		frappe.db.commit()
		print(f"  Driving licence alert re-pointed: {current} -> {wanted} days.")
	elif not wanted:
		frappe.db.set_value("Notification", ALERT, "enabled", 0, update_modified=False)
		frappe.db.commit()
		print("  Driving licence notice is 0, so the alert was switched off.")
