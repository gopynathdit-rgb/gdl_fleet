# Copyright (c) 2026, GDL and contributors
"""
Seeds GDL Fleet Settings with the customer's starting configuration.

These values are DATA, written once into the Single on first install. The engine
in utils.maintenance reads them back from the database at runtime, so GDL can
change an interval, add a service item or retire a rule entirely from the desk
without a code change or a deployment.
"""

import frappe

# (service item, interval km, interval months) - the customer's opening set.
# Fleet Mgmt.docx section 4.4 names these twelve maintenance items. The
# intervals remain configuration; only the item list comes from the document.
DEFAULT_MAINTENANCE_RULES = [
	("Engine Oil", 7500, 6),
	("Engine Oil Filter", 7500, 6),
	("Fuel Filter", 10000, 12),
	("Air Filter", 10000, 12),
	("Brake Fluid", 40000, 24),
	("Brake Pads", 30000, 24),
	("Coolant", 40000, 24),
	("Gear Oil", 40000, 24),
	("Tyre Replacement / Rotation", 20000, 24),
	("Battery Replacement", 0, 36),
	("General Inspection", 0, 6),
	("Other Repair or Maintenance", 0, 0),
]


def create_service_items():
	"""Vehicle Service Item is the STANDARD hrms master - reused, not duplicated."""
	for service_item, _km, _months in DEFAULT_MAINTENANCE_RULES:
		if frappe.db.exists("Vehicle Service Item", service_item):
			continue
		frappe.get_doc(
			{"doctype": "Vehicle Service Item", "service_item": service_item}
		).insert(ignore_permissions=True)


def seed_fleet_settings():
	"""Idempotent: seeds only what is still empty, never overwrites GDL's edits."""
	create_service_items()

	settings = frappe.get_single("GDL Fleet Settings")
	changed = False

	# Additive: a rule GDL has already tuned is never overwritten, but an item
	# named in section 4.4 that is missing gets added.
	configured = {row.service_item for row in settings.get("maintenance_rules") or []}
	for service_item, interval_km, interval_months in DEFAULT_MAINTENANCE_RULES:
		if service_item in configured:
			continue
		settings.append(
			"maintenance_rules",
			{
				"service_item": service_item,
				"interval_km": interval_km,
				"interval_months": interval_months,
				"maintenance_type": "Preventive Maintenance",
				"is_active": 1,
			},
		)
		changed = True

	for fieldname, value in (
		# Client answer, 3 Nov 2026: "their requirement is in 14 day ... Or 14
		# and 3 days." So the ladder is 14 days, 3 days and the expiry day, and
		# the two spare rungs ship switched off.
		("renewal_notice_days", 14),
		("renewal_second_reminder_days", 3),
		("renewal_third_reminder_days", 0),
		("renewal_final_reminder_days", 0),
		("abnormal_daily_km", 500),
		("maintenance_due_notice_days", 14),
		("maintenance_due_notice_km", 500),
	):
		# `not settings.get(...)` would be wrong here: 0 is a deliberate value
		# meaning "switch this reminder off", and treating it as unset puts the
		# reminder back on every single migrate.
		if settings.get(fieldname) in (None, ""):
			settings.set(fieldname, value)
			changed = True

	if changed:
		settings.flags.ignore_permissions = True
		settings.save()

	return changed
