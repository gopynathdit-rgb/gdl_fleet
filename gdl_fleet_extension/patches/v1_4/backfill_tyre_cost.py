# Copyright (c) 2026, GDL and contributors
"""
Vehicle Tyre gained a Cost field so the Tyre Cost Analysis report has something
to divide by kilometres. Tyres fitted before the field existed already have
their cost recorded - on the Fleet Part Issue line that fitted them - so this
copies it across rather than leaving the report half empty on day one.

A tyre recorded by hand, with no part issue behind it, is left alone. Its cost
is not known to the system and guessing one would be worse than a blank.
"""

import frappe


def execute():
	if not frappe.db.has_column("Vehicle Tyre", "cost"):
		return

	tyres = frappe.get_all(
		"Vehicle Tyre",
		filters={"part_issue": ("is", "set"), "cost": ("in", (0, None))},
		fields=["name", "part_issue", "item_code", "tyre_position"],
	)
	if not tyres:
		return

	updated = 0
	for tyre in tyres:
		amount = frappe.db.get_value(
			"Fleet Part Issue Item",
			{
				"parent": tyre.part_issue,
				"item_code": tyre.item_code,
				"tyre_position": tyre.tyre_position,
			},
			"amount",
		)
		if not amount:
			continue
		frappe.db.set_value("Vehicle Tyre", tyre.name, "cost", amount, update_modified=False)
		updated += 1

	frappe.db.commit()
	print(f"Backfilled cost onto {updated} of {len(tyres)} tyre(s) from their part issue.")
