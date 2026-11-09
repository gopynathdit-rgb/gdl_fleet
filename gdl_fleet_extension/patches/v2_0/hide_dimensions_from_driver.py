# Copyright (c) 2026, GDL and contributors
"""Take the accounting dimensions off the driver's Vehicle Log.

GDL, looking at the form as a driver: "in driver login i dont need this field"
- the Site and Accounting Dimensions section. Site, Department, Cost Center,
Project and Task are how FINANCE files a journey, not how a driver records one,
and they sat as five empty boxes between the driver and the odometer reading.

Raising the fields to permlevel 1 is what hides them, and it hides them from
EVERY role without a level-1 row - which is why setup/fleet_permissions.py now
carries a level-1 row for Fleet Administrator, Fleet Manager, Fleet Approver
and Fleet Maintenance User. Those four already reached these fields; they keep
what they had. Fleet Driver is the one left out, which is the whole point.

create_custom_fields() creates what is missing and never touches what exists,
so the permlevel added to the setup dict reaches a fresh install and nothing
else. This applies it to the sites already running.
"""

import frappe

FIELDS = ("gdl_dimension_section", "site", "department", "gdl_dimension_cb",
          "cost_center", "project", "task")


def execute():
	changed, missing = [], []

	for fieldname in FIELDS:
		name = frappe.db.get_value(
			"Custom Field", {"dt": "Vehicle Log", "fieldname": fieldname}, "name")
		if not name:
			missing.append(fieldname)
			continue
		if frappe.db.get_value("Custom Field", name, "permlevel") == 1:
			continue
		frappe.db.set_value("Custom Field", name, "permlevel", 1)
		changed.append(fieldname)

	if changed:
		frappe.clear_cache(doctype="Vehicle Log")
		frappe.db.commit()
		print(f"  Raised {len(changed)} Vehicle Log field(s) above a driver's reach.")
	if missing:
		print(f"  Not on this site, skipped: {missing}")
