# Copyright (c) 2026, GDL and contributors
"""Take Asset Repair off the fleet menu, properly this time.

The first attempt set `hidden` on the Workspace Link and reported success from
the database flag. It did nothing. frappe's desk/desktop.py builds a
workspace's links like this:

    # Check if user is allowed to view
    if self.is_item_allowed(item.link_to, item.link_type):

and never looks at `hidden` at all - the links widget renders every link it is
handed. Permission is the only filter there is, which is why GDL still saw both
entries as Administrator.

So the grant goes. Fleet Driver, Fleet Maintenance User and Fleet Administrator
lose their rows on Asset Repair, at GDL's instruction. The form cannot be saved
by any of them anyway: `asset` is mandatory and no GDL vehicle is linked to an
Asset, so opening it only ever ended in "Asset None not found". There are no
records to lose.

NOT touched: Manufacturing Manager, Quality Manager and Fleet Manager. Those
rows are ERPNext's own, for repairs on non-vehicle assets - GDL has three, a
building and some furniture - and taking the DocType away from them was never
asked for.

Administrator will still see the link. Nothing can change that short of
disabling the DocType for the whole site, which would reach Accounts too.
"""

import frappe

DOCTYPE = "Asset Repair"
ROLES = ("Fleet Driver", "Fleet Maintenance User", "Fleet Administrator")


def execute():
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	removed = []
	for role in ROLES:
		for name in frappe.get_all("Custom DocPerm",
		                           filters={"parent": DOCTYPE, "role": role},
		                           pluck="name"):
			frappe.delete_doc("Custom DocPerm", name, ignore_permissions=True, force=True)
			removed.append(role)

	if removed:
		frappe.clear_cache()
		frappe.db.commit()
		print(f"  {DOCTYPE} is no longer reachable by: {', '.join(sorted(set(removed)))}.")
