# Copyright (c) 2026, GDL and contributors
"""Take Vehicle Tyre off the GDL Fleet menu.

GDL circled it in the breadcrumb: "hide this".

The LINK ROW is removed, not a permission and not the `hidden` tick. That tick
does nothing - desk/desktop.py get_links() filters workspace entries on
is_item_allowed() alone and never reads it, which is what wasted a round on
Asset Repair. And permission is the wrong lever here: Fleet Part Issue creates
these records, and Tyre Mileage Report and Tyre Cost Analysis read them, so
taking the right away would break the tyre tracking the document asks for.

Nothing is lost. Every tyre record stays, reachable from its Fleet Part Issue
and from both tyre reports, which keep their own menu entries. Putting the row
back restores the entry.
"""

import frappe

WORKSPACE = "GDL Fleet"
LINK_TO = "Vehicle Tyre"
CARD = "Parts & Tyres"


def execute():
	if not frappe.db.exists("Workspace", WORKSPACE):
		return

	workspace = frappe.get_doc("Workspace", WORKSPACE)
	keep = [l for l in workspace.links
	        if not (l.type == "Link" and l.link_to == LINK_TO)]
	if len(keep) == len(workspace.links):
		return

	# The card header declares how many links follow it; leaving it at 2 with
	# one link left makes the card render wrong.
	for link in keep:
		if link.type == "Card Break" and link.label == CARD:
			link.link_count = max(0, (link.link_count or 0) - 1)

	workspace.links = keep
	workspace.flags.ignore_permissions = True
	workspace.save()
	frappe.clear_cache()
	frappe.db.commit()
	print(f"  {LINK_TO} is off the {WORKSPACE} menu. Its records are untouched.")
