# Copyright (c) 2026, GDL and contributors
"""The left sidebar, built from the GDL Fleet workspace.

GDL rearranged the workspace cards and then said "left also need change" -
the sidebar still listed every DocType and Report in the module, including the
ones taken off the menu.

The sidebar is a separate record from the workspace, and frappe otherwise
generates it from every non-child DocType, Report, Page and Dashboard that
declares the module. That is why Asset Repair and Vehicle Tyre stayed in it
after both came off the cards. This builds it FROM the cards instead, so the
two cannot drift: change a card and the sidebar follows on the next migrate.

TWO FRAPPE VERSIONS
-------------------
frappe renamed this doctype mid-v16. Up to ~16.32 it is `Workspace Sidebar`
with `Workspace Sidebar Item`; by 16.56 that is replaced by `Sidebar` with
`Sidebar Item` (frappe/desk/doctype/sidebar/sidebar.py, and the note in
boot.py: "This replaced three overlapping payloads: workspace_sidebar_item
...").

GDL's server runs the newer one and this machine the older, which is why a
sidebar written here looked correct in the database and changed nothing on
the server - the running frappe was reading a different table.

Both carry the same fields for what this needs (type, label, link_type,
link_to, child, collapsible), so one builder serves both. Whichever doctype
the site has is the one written.
"""

import frappe

WORKSPACE = "GDL Fleet"
SIDEBAR = "GDL Fleet"
MODULE = "GDL Fleet"

# newest first - a site with both gets the one its desk actually reads
SIDEBAR_DOCTYPES = ("Sidebar", "Workspace Sidebar")


def sidebar_doctype():
	for doctype in SIDEBAR_DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			return doctype
	return None


def setup_fleet_sidebar():
	"""Idempotent. Safe on install and on every migrate."""
	doctype = sidebar_doctype()
	if not doctype or not frappe.db.exists("Workspace", WORKSPACE):
		return

	wanted = sidebar_items_from_workspace()
	if not wanted:
		return

	if frappe.db.exists(doctype, SIDEBAR):
		doc = frappe.get_doc(doctype, SIDEBAR)
	else:
		doc = frappe.new_doc(doctype)
		doc.title = SIDEBAR

	if same(doc.items, wanted):
		return

	doc.module = MODULE
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
	def shape(rows):
		return [(r.get("label"), r.get("type"), r.get("link_to")) for r in rows]

	return shape(existing) == shape(wanted)
