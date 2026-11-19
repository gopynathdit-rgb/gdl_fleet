# Copyright (c) 2026, GDL and contributors
"""The left sidebar, built from the GDL Fleet workspace.

GDL rearranged the workspace cards and then said "left also need change" -
the sidebar still listed every DocType and Report in the module, including the
ones taken off the menu.

The sidebar is a separate record: a Workspace Sidebar, which frappe otherwise
auto-generates from every non-child DocType, Report, Page and Dashboard that
declares the module (auto_generate_sidebar_from_module). That is why Asset
Repair and Vehicle Tyre were still in it after both came off the workspace.

This builds it FROM the workspace's own cards, so the two cannot drift: change
a card, and the sidebar follows on the next migrate. A card becomes a Section
Break; its links become sidebar links.
"""

import frappe

WORKSPACE = "GDL Fleet"
SIDEBAR = "GDL Fleet"


def setup_fleet_sidebar():
	"""Idempotent. Safe on install and on every migrate."""
	if not frappe.db.exists("Workspace", WORKSPACE):
		return

	wanted = sidebar_items_from_workspace()
	if not wanted:
		return

	if frappe.db.exists("Workspace Sidebar", SIDEBAR):
		doc = frappe.get_doc("Workspace Sidebar", SIDEBAR)
	else:
		doc = frappe.new_doc("Workspace Sidebar")
		doc.title = SIDEBAR

	if same(doc.items, wanted):
		return

	doc.module = "GDL Fleet"
	doc.items = []
	for row in wanted:
		doc.append("items", row)
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.clear_cache()
	return len(wanted)


def sidebar_items_from_workspace():
	workspace = frappe.get_doc("Workspace", WORKSPACE)
	items = []
	for link in workspace.links:
		if link.type == "Card Break":
			items.append({"label": link.label, "type": "Section Break",
			              "collapsible": 1})
		elif link.type == "Link":
			items.append({
				"label": link.label,
				"type": "Link",
				"link_type": link.link_type,
				"link_to": link.link_to,
				"child": 1,
			})
	return items


def same(existing, wanted):
	def shape(rows, get):
		return [(get(r, "label"), get(r, "type"), get(r, "link_to")) for r in rows]

	return (shape(existing, lambda r, f: r.get(f))
	        == shape(wanted, lambda r, f: r.get(f)))
