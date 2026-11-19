# Copyright (c) 2026, GDL and contributors
"""
The GDL Fleet module page.

These tests exist because of a real failure: frappe skips importing a
non-DocType file whose `modified` stamp is not newer than the stored record, so
five phases of workspace edits sat in the repository without ever reaching the
site. Nothing warned about it. These tests do.
"""

import json
import pathlib

import frappe
from frappe.tests import IntegrationTestCase

WORKSPACE = "GDL Fleet"
WORKSPACE_FILE = (
	pathlib.Path(frappe.get_app_path("gdl_fleet_extension"))
	/ "gdl_fleet"
	/ "workspace"
	/ "gdl_fleet"
	/ "gdl_fleet.json"
)


def load_file():
	return json.loads(WORKSPACE_FILE.read_text())


# DocTypes deliberately left off the menu, and how each is still reached.
#
#   Vehicle Tyre - GDL circled it and asked for it to be hidden. A tyre record
#   is created BY a Fleet Part Issue, and read by Tyre Mileage Report and Tyre
#   Cost Analysis, all three of which keep their own menu entries. Its own
#   entry was a fourth way into the same data.
REACHED_ANOTHER_WAY = {"Vehicle Tyre"}


class TestGDLFleetWorkspace(IntegrationTestCase):
	def setUp(self):
		self.file = load_file()
		self.doc = frappe.get_doc("Workspace", WORKSPACE)

	# --- the sync trap --------------------------------------------------------
	def test_database_matches_the_file(self):
		"""Catches an edit that was never synced because `modified` was not bumped."""
		file_links = [
			(link["type"], link.get("link_to"))
			for link in self.file["links"]
		]
		db_links = [(row.type, row.link_to) for row in self.doc.links]
		self.assertEqual(
			db_links,
			file_links,
			"the workspace on the site differs from the file - bump `modified` in "
			f"{WORKSPACE_FILE.name} to a time NEWER than the stored record "
			"(the database stores site-timezone time) and run bench migrate",
		)

	def test_shortcuts_match_the_file(self):
		file_shortcuts = [s["link_to"] for s in self.file["shortcuts"]]
		db_shortcuts = [s.link_to for s in self.doc.shortcuts]
		self.assertEqual(db_shortcuts, file_shortcuts)

	# --- content integrity ----------------------------------------------------
	def test_no_duplicate_links(self):
		targets = [l["link_to"] for l in self.file["links"] if l["type"] == "Link"]
		duplicates = {t for t in targets if targets.count(t) > 1}
		self.assertEqual(duplicates, set(), f"duplicated in the workspace: {duplicates}")

	def test_card_link_counts_are_correct(self):
		links = self.file["links"]
		for index, link in enumerate(links):
			if link["type"] != "Card Break":
				continue
			counted = 0
			for following in links[index + 1 :]:
				if following["type"] == "Card Break":
					break
				counted += 1
			self.assertEqual(
				link["link_count"], counted,
				f"card '{link['label']}' declares {link['link_count']} links but has {counted}",
			)

	def test_every_card_is_rendered(self):
		"""A card with no block in `content` never appears on the page."""
		cards = {l["label"] for l in self.file["links"] if l["type"] == "Card Break"}
		rendered = {
			block["data"]["card_name"]
			for block in json.loads(self.file["content"])
			if block.get("type") == "card"
		}
		self.assertEqual(cards, rendered, "some cards are defined but never rendered")

	# --- reachability ---------------------------------------------------------
	def test_every_gdl_doctype_is_reachable(self):
		"""A DocType nobody can navigate to may as well not exist."""
		gdl_doctypes = set(
			frappe.get_all(
				"DocType",
				filters={"module": "GDL Fleet", "istable": 0},
				pluck="name",
			)
		)
		linked = {l.get("link_to") for l in self.file["links"] if l["type"] == "Link"}
		missing = gdl_doctypes - linked - REACHED_ANOTHER_WAY
		self.assertEqual(missing, set(), f"not reachable from the workspace: {missing}")

	def test_the_exceptions_are_genuinely_reachable(self):
		"""A doctype left off the menu has to be reachable some other way, or
		the exception list is just a way of silencing this test."""
		labels = {l.get("label") for l in self.file["links"]}
		self.assertIn("Tyre Mileage Report", labels)
		self.assertIn("Tyre Cost Analysis", labels)
		self.assertIn("Fleet Part Issue", {l.get("link_to") for l in self.file["links"]})

	def test_all_targets_exist(self):
		for link in self.file["links"]:
			if link["type"] != "Link":
				continue
			doctype = "Report" if link["link_type"] == "Report" else "DocType"
			self.assertTrue(
				frappe.db.exists(doctype, link["link_to"]),
				f"{link['link_type']} {link['link_to']} does not exist",
			)

	def test_shortcut_targets_exist(self):
		for shortcut in self.file["shortcuts"]:
			self.assertTrue(frappe.db.exists("DocType", shortcut["link_to"]))

	# --- the standard fleet page is left alone -------------------------------
	def test_standard_hrms_fleet_card_untouched(self):
		"""ERPNext's own fleet links live on the HR Expenses page and must stay."""
		expenses = frappe.get_doc("Workspace", "Expenses")
		labels = [row.label for row in expenses.links]
		self.assertIn("Fleet Management", labels)
		for target in ("Vehicle", "Driver", "Vehicle Log", "Vehicle Service Item"):
			self.assertIn(target, [row.link_to for row in expenses.links])


class TestDeskVisibility(IntegrationTestCase):
	"""Two fleet apps are installed; the desk must offer only one fleet entry."""

	def desk_pages(self):
		from frappe.desk.desktop import get_workspaces
		frappe.clear_cache()
		result = get_workspaces()
		return ([p["label"] for p in result["pages"]]
		        + [p["label"] for p in result.get("private_pages", [])])

	def test_superseded_fleet_workspace_is_gone(self):
		self.assertNotIn("Fleet Management", self.desk_pages())
		self.assertFalse(frappe.db.exists("Workspace", "Fleet Management"))

	def test_gdl_fleet_is_on_the_desk(self):
		self.assertIn("GDL Fleet", self.desk_pages())

	def test_gdl_fleet_leads_the_fleet_area(self):
		pages = self.desk_pages()
		self.assertLess(pages.index("GDL Fleet"), 8,
		                "GDL Fleet should sit near the front, not sort last")

	def test_the_superseded_app_is_uninstalled(self):
		"""gdl_fleet_management was removed; its DocTypes should be gone with it."""
		for doctype in ("Vehicle Request", "Trip Sheet", "Vehicle Master",
		                "Driver Authorization", "Fleet Settings"):
			self.assertFalse(frappe.db.exists("DocType", doctype),
			                 f"{doctype} belonged to the uninstalled app")
		self.assertNotIn("gdl_fleet_management", frappe.get_installed_apps())

	def test_no_dead_tile_is_left_on_the_desk(self):
		"""A tile whose target is missing has no route.

		Clicking it raises "Icon is not correctly configured please check the
		workspace sidebar to it". `link_to` is a Dynamic Link, so it has to be
		resolved through `link_type` - a desk tile points at a Workspace
		Sidebar, not at a Workspace directly.
		"""
		for icon in frappe.get_all("Desktop Icon",
		                           fields=["name", "link_to", "link_type", "icon_type"]):
			if icon.icon_type != "Link" or not icon.link_to or not icon.link_type:
				continue
			self.assertTrue(
				frappe.db.exists(icon.link_type, icon.link_to),
				f"Desktop Icon {icon.name} points at missing "
				f"{icon.link_type} {icon.link_to}")

	def test_gdl_fleet_has_a_desk_tile(self):
		self.assertTrue(frappe.db.exists("Desktop Icon", "GDL Fleet"))
		row = frappe.db.get_value("Desktop Icon", "GDL Fleet",
		                          ["icon_type", "link_type", "link_to", "icon", "hidden"],
		                          as_dict=True)
		self.assertEqual(row.icon_type, "Link")
		self.assertEqual(row.link_type, "Workspace Sidebar")
		self.assertEqual(row.link_to, "GDL Fleet")
		self.assertEqual(row.hidden, 0)

	def test_the_tile_icon_file_actually_exists(self):
		"""The grey-letter fallback happens when the named SVG is not shipped."""
		import os

		import frappe.utils

		icon = frappe.db.get_value("Desktop Icon", "GDL Fleet", "icon")
		path = frappe.get_app_path("gdl_fleet_extension", "public", "desktop_icons",
		                           f"{icon}.svg")
		self.assertTrue(os.path.exists(path),
		                f"{icon}.svg is not shipped, so the tile would fall back to a letter")

	def test_gdl_fleet_is_on_the_apps_screen(self):
		from frappe.apps import get_apps
		tiles = {a["name"]: a for a in get_apps()}
		self.assertIn("gdl_fleet_extension", tiles)
		self.assertEqual(tiles["gdl_fleet_extension"]["route"], "/desk/gdl-fleet")

	def test_the_old_app_is_not_on_the_apps_screen(self):
		from frappe.apps import get_apps
		self.assertNotIn("gdl_fleet_management", {a["name"] for a in get_apps()})


class TestTheSidebarFollowsTheWorkspace(IntegrationTestCase):
	"""GDL: "left also need change".

	The left sidebar is a Workspace Sidebar record, NOT the workspace. Frappe
	otherwise auto-generates one from every non-child DocType, Report, Page and
	Dashboard that declares the module - which is why Asset Repair and Vehicle
	Tyre were still listed after both came off the workspace cards.

	It is built FROM the cards so the two cannot drift.
	"""

	SIDEBAR = "GDL Fleet"

	def sidebar(self):
		"""Whichever doctype this frappe uses.

		frappe renamed it mid-v16: `Workspace Sidebar` up to ~16.32, `Sidebar`
		by 16.56. GDL's server runs the newer one and this machine the older,
		which is how a sidebar that looked right here changed nothing there.
		"""
		from gdl_fleet_extension.setup.fleet_sidebar import sidebar_doctype

		doctype = sidebar_doctype()
		if not doctype or not frappe.db.exists(doctype, self.SIDEBAR):
			self.skipTest("no sidebar doctype on this site")
		return frappe.get_doc(doctype, self.SIDEBAR)

	def test_the_builder_targets_a_doctype_this_frappe_has(self):
		"""The whole failure was writing to a table the running frappe no
		longer reads."""
		from gdl_fleet_extension.setup.fleet_sidebar import (
			SIDEBAR_DOCTYPES,
			sidebar_doctype,
		)
		chosen = sidebar_doctype()
		self.assertIsNotNone(chosen, "no sidebar doctype found at all")
		self.assertIn(chosen, SIDEBAR_DOCTYPES)
		self.assertTrue(frappe.db.exists("DocType", chosen))

	def test_the_newer_doctype_wins_when_both_exist(self):
		"""A site mid-upgrade can carry both. The desk reads the new one."""
		from gdl_fleet_extension.setup.fleet_sidebar import SIDEBAR_DOCTYPES

		self.assertEqual(SIDEBAR_DOCTYPES[0], "Sidebar")

	def workspace_shape(self):
		workspace = frappe.get_doc("Workspace", "GDL Fleet")
		return [(l.label, "Section Break" if l.type == "Card Break" else "Link")
		        for l in workspace.links if l.type in ("Card Break", "Link")]

	def test_it_matches_the_workspace_card_for_card(self):
		shape = [(i.label, i.type) for i in self.sidebar().items]
		self.assertEqual(shape, self.workspace_shape(),
		                 "the sidebar and the workspace have drifted apart")

	def test_what_came_off_the_menu_is_off_the_sidebar_too(self):
		labels = {i.label for i in self.sidebar().items}
		for gone in ("Asset Repair", "Asset Maintenance", "Vehicle Tyre",
		             "General Ledger", "Budget Variance Report"):
			self.assertNotIn(gone, labels, f"{gone} is still in the sidebar")

	def test_rebuilding_it_twice_changes_nothing(self):
		"""It runs on every migrate."""
		from gdl_fleet_extension.setup.fleet_sidebar import setup_fleet_sidebar
		setup_fleet_sidebar()
		before = [(i.label, i.type) for i in self.sidebar().items]
		self.assertIsNone(setup_fleet_sidebar(), "a second run rewrote the sidebar")
		self.assertEqual([(i.label, i.type) for i in self.sidebar().items], before)
