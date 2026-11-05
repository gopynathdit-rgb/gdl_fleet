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
		missing = gdl_doctypes - linked
		self.assertEqual(missing, set(), f"not reachable from the workspace: {missing}")

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
