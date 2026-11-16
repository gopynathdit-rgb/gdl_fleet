# Copyright (c) 2026, GDL and contributors
"""Take Asset Maintenance off the fleet menu too.

The companion to hide_asset_repair_from_the_desk, and unusable for the same
reason. Asset Maintenance is ERPNext's maintenance PLAN, and for a vehicle it
cannot be saved:

    asset_name        Link -> Asset                 mandatory
    maintenance_team  Link -> Asset Maintenance Team  mandatory

No GDL vehicle is linked to an Asset (0 of 14) and Default Maintenance Team has
never been set. There are no records, and there could not have been.

Nothing is lost by hiding it, because nothing depended on it. GDL's periodic
maintenance runs on its own data and was checked before this was written:

    Asset Maintenance records : 0
    GDL Fleet Maintenance Rule: 12
    Service Due               : runs, with its own columns
    Notifications             : Maintenance Due, Maintenance Overdue

Next due date and KM are worked out from those rules by the service record
itself, not by a plan. The final document asks for maintenance scheduling,
service due monitoring and overdue tracking; all three are answered by the
rules, the report and the notifications.

Hidden on the workspace, not deleted - DocType, code and any future records all
stay. One link to un-hide if GDL ever puts its vehicles on the asset register.
"""

import frappe

WORKSPACE = "GDL Fleet"
# Asset Repair is listed again deliberately: this patch is idempotent and the
# earlier one found nothing to do, because the workspace JSON re-imported with
# hidden already set before it ran.
LINKS = ("Asset Maintenance", "Asset Repair")


def execute():
	if not frappe.db.exists("Workspace", WORKSPACE):
		return

	hidden = []
	for link_to in LINKS:
		rows = frappe.get_all("Workspace Link", filters={
			"parent": WORKSPACE, "link_to": link_to, "type": "Link", "hidden": 0},
			pluck="name")
		for name in rows:
			frappe.db.set_value("Workspace Link", name, "hidden", 1, update_modified=False)
		if rows:
			hidden.append(link_to)

	if hidden:
		frappe.clear_cache()
		frappe.db.commit()
		print(f"  Off the {WORKSPACE} menu: {', '.join(hidden)} - neither can be saved "
		      f"without an Asset, and nothing depends on them.")
