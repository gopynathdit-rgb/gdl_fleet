# Copyright (c) 2026, GDL and contributors
"""
The GDL Fleet tile on the Desk home page.

The Desk home grid is built from three records that have to line up, which is
where the old Fleet Management tile came apart:

  Desktop Icon  ->  Workspace Sidebar  ->  Workspace

  * `Desktop Icon` is the tile. Its `link_to` is a Dynamic Link resolved
    through `link_type`, which for a desk tile is "Workspace Sidebar" - NOT
    "Workspace". Pointing it straight at a Workspace fails validation.

  * `Workspace Sidebar` is the navigation group behind the tile. Its first
    item, of link_type "Workspace", is what gives the tile its route. With no
    resolvable route the tile shows "Icon is not correctly configured please
    check the workspace sidebar to it" when clicked.

  * `icon` must name an SVG shipped at
    `<app>/public/desktop_icons/<name>.svg`. The old tile asked for "truck",
    which no installed app provides, so the page fell back to a grey letter.
    This app ships `gdl_fleet.svg` on the same 54x54 artboard ERPNext uses.

The uninstall of gdl_fleet_management left its Desktop Icon and Workspace
Sidebar behind, because both were created at runtime rather than shipped by the
app (`standard = 0`), so nothing claimed them.
"""

import frappe

NAME = "GDL Fleet"
WORKSPACE = "GDL Fleet"
ICON_SVG = "gdl_fleet"
APP = "gdl_fleet_extension"
ORPHANED = "Fleet Management"

# Mirrors the cards on the workspace so the sidebar and the page agree.
SIDEBAR_ITEMS = [
	("Link", "Home", "Workspace", WORKSPACE, "home"),
	("Section Break", "Vehicle Master", "DocType", None, "list"),
	("Link", "Vehicle", "DocType", "Vehicle", None),
	("Link", "Driver", "DocType", "Driver", None),
	("Link", "Fleet Vehicle Type", "DocType", "Fleet Vehicle Type", None),
	("Link", "Driver Assignment", "DocType", "Driver Assignment", None),
	("Link", "Renewal Register", "DocType", "Renewal Register", None),
	("Section Break", "Movement", "DocType", None, "share"),
	("Link", "Movement Order Request", "DocType", "Movement Order Request", None),
	("Link", "Movement Order", "DocType", "Movement Order", None),
	("Section Break", "Operations", "DocType", None, "tool"),
	("Link", "Daily KM / Vehicle Log", "DocType", "Vehicle Log", None),
	("Link", "POL Abstract", "DocType", "POL Abstract", None),
	("Section Break", "Service & Maintenance", "DocType", None, "settings"),
	("Link", "Asset Maintenance Log", "DocType", "Asset Maintenance Log", None),
	("Link", "Asset Repair", "DocType", "Asset Repair", None),
	("Section Break", "Parts & Tyres", "DocType", None, "database"),
	("Link", "Fleet Part Issue", "DocType", "Fleet Part Issue", None),
	("Link", "Vehicle Tyre", "DocType", "Vehicle Tyre", None),
	("Section Break", "Setup", "DocType", None, "settings"),
	("Link", "GDL Fleet Settings", "DocType", "GDL Fleet Settings", None),
	("Section Break", "Reports", "DocType", None, "sheet"),
	("Link", "Fleet Register", "Report", "Fleet Register", None),
	("Link", "Vehicle Utilization", "Report", "Vehicle Utilization", None),
	("Link", "Service Due", "Report", "Service Due", None),
	("Link", "Insurance / Renewal Due", "Report", "Insurance and Renewal Due", None),
	("Link", "POL Summary Register", "Report", "POL Summary Register", None),
	("Link", "Mileage Deviation Dashboard", "Report", "Mileage Deviation Dashboard", None),
	("Link", "Tyre Mileage Report", "Report", "Tyre Mileage Report", None),
]


def _target_exists(link_type, link_to):
	if not link_to:
		return True
	return bool(frappe.db.exists(link_type, link_to))


def remove_orphans():
	"""Drop the tile and sidebar left behind by the uninstalled app.

	Only when their targets really are gone - if the old app is ever
	reinstalled these come back and should be left alone.
	"""
	removed = []

	# Innermost first: the sidebar is only dead once its workspace has gone,
	# and the tile is only dead once its sidebar has gone. Checking the tile
	# first would read a sidebar that is about to be deleted and spare the tile.
	if frappe.db.exists("Workspace Sidebar", ORPHANED):
		if not frappe.db.exists("Workspace", ORPHANED):
			frappe.delete_doc("Workspace Sidebar", ORPHANED, force=True, ignore_permissions=True)
			removed.append("Workspace Sidebar")

	if frappe.db.exists("Desktop Icon", ORPHANED):
		link_to = frappe.db.get_value("Desktop Icon", ORPHANED, "link_to")
		if not link_to or not frappe.db.exists("Workspace Sidebar", link_to):
			frappe.delete_doc("Desktop Icon", ORPHANED, force=True, ignore_permissions=True)
			removed.append("Desktop Icon")

	return removed


def build_sidebar():
	"""The navigation group the tile opens into."""
	if not frappe.db.exists("Workspace", WORKSPACE):
		return False

	if frappe.db.exists("Workspace Sidebar", NAME):
		doc = frappe.get_doc("Workspace Sidebar", NAME)
	else:
		doc = frappe.new_doc("Workspace Sidebar")
		doc.name = NAME

	doc.title = NAME
	doc.header_icon = ICON_SVG
	doc.app = APP
	doc.standard = 0
	if doc.meta.get_field("module") and frappe.db.exists("Module Def", "GDL Fleet"):
		doc.module = "GDL Fleet"

	doc.set("items", [])
	for item_type, label, link_type, link_to, icon in SIDEBAR_ITEMS:
		# Never ship a dead link - a missing target is what breaks the tile.
		if not _target_exists(link_type, link_to):
			continue
		doc.append("items", {
			"type": item_type, "label": label, "link_type": link_type,
			"link_to": link_to, "icon": icon,
		})

	doc.flags.ignore_permissions = True
	doc.save()
	return True


def build_tile():
	"""The tile itself on the Desk home grid."""
	if not frappe.db.exists("Workspace Sidebar", NAME):
		return False

	values = {
		"label": NAME,
		"icon_type": "Link",
		"link_type": "Workspace Sidebar",
		"link_to": NAME,
		"app": APP,
		"icon": ICON_SVG,
		"hidden": 0,
		"standard": 0,
	}

	if frappe.db.exists("Desktop Icon", NAME):
		changed = False
		for field, value in values.items():
			if frappe.db.get_value("Desktop Icon", NAME, field) != value:
				frappe.db.set_value("Desktop Icon", NAME, field, value, update_modified=False)
				changed = True
		return changed

	doc = frappe.get_doc({"doctype": "Desktop Icon", **values})
	doc.flags.ignore_permissions = True
	doc.insert()
	return True


def setup_desktop_icon():
	removed = remove_orphans()
	sidebar = build_sidebar()
	tile = build_tile()
	if removed or sidebar or tile:
		frappe.clear_cache()
	return {"removed_orphans": removed, "sidebar": sidebar, "tile": tile}
