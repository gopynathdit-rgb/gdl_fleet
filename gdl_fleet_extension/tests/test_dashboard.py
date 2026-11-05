# Copyright (c) 2026, GDL and contributors
"""
The fleet dashboard - Business Blueprint item 10, "Reports & Dashboard", and
GAP item 4, "Mileage Report/Dashboard".

A chart that points at a renamed field fails on every desk load, and a card
with a filter on an option that no longer exists silently reads zero - which
is worse, because zero looks like good news. These tests execute every card
and chart rather than just checking they exist.
"""

import json

import frappe
from frappe.tests import IntegrationTestCase

from gdl_fleet_extension.setup.dashboard import (
	DASHBOARD_CHARTS,
	NUMBER_CARDS,
	setup_dashboard,
)

WORKSPACE = "GDL Fleet"


class TestDashboardDefinitions(IntegrationTestCase):
	def test_every_card_exists(self):
		for spec in NUMBER_CARDS:
			self.assertTrue(
				frappe.db.exists("Number Card", spec["label"]),
				f"missing number card {spec['label']}",
			)

	def test_every_chart_exists(self):
		for spec in DASHBOARD_CHARTS:
			self.assertTrue(
				frappe.db.exists("Dashboard Chart", spec["chart_name"]),
				f"missing chart {spec['chart_name']}",
			)

	def test_a_card_is_named_by_its_title(self):
		"""Both doctypes autoname from their own label, so the title IS the
		record name. Assuming otherwise creates a duplicate on every migrate."""
		for spec in NUMBER_CARDS:
			self.assertEqual(
				frappe.db.get_value("Number Card", spec["label"], "label"), spec["label"]
			)
		for spec in DASHBOARD_CHARTS:
			self.assertEqual(
				frappe.db.get_value("Dashboard Chart", spec["chart_name"], "chart_name"),
				spec["chart_name"],
			)

	def test_every_card_field_still_exists(self):
		"""A filter on a renamed field reads zero, and zero looks like good news."""
		for spec in NUMBER_CARDS:
			meta = frappe.get_meta(spec["document_type"])
			for condition in json.loads(spec.get("filters_json") or "[]"):
				fieldname = condition[1]
				if fieldname in ("docstatus", "name", "owner"):
					continue
				self.assertIsNotNone(
					meta.get_field(fieldname),
					f"{spec['label']} filters on {spec['document_type']}.{fieldname}, "
					f"which no longer exists",
				)

	def test_every_card_filter_value_is_a_real_option(self):
		"""A Select option that was renamed would make the card read zero."""
		for spec in NUMBER_CARDS:
			meta = frappe.get_meta(spec["document_type"])
			for condition in json.loads(spec.get("filters_json") or "[]"):
				fieldname, operator, value = condition[1], condition[2], condition[3]
				field = meta.get_field(fieldname)
				if not field or field.fieldtype != "Select":
					continue
				options = set((field.options or "").split("\n"))
				for wanted in (value if isinstance(value, list) else [value]):
					self.assertIn(
						wanted, options,
						f"{spec['label']}: '{wanted}' is not an option of "
						f"{spec['document_type']}.{fieldname}",
					)

	def test_every_chart_field_still_exists(self):
		for spec in DASHBOARD_CHARTS:
			meta = frappe.get_meta(spec["document_type"])
			for key in ("based_on", "value_based_on", "group_by_based_on"):
				fieldname = spec.get(key)
				if not fieldname:
					continue
				self.assertIsNotNone(
					meta.get_field(fieldname),
					f"{spec['chart_name']}.{key} points at "
					f"{spec['document_type']}.{fieldname}, which no longer exists",
				)

	def test_creation_is_idempotent(self):
		result = setup_dashboard()
		self.assertEqual(result["number_cards"]["created"], [])
		self.assertEqual(result["charts"]["created"], [])


class TestDashboardRenders(IntegrationTestCase):
	def test_every_card_returns_a_number(self):
		from frappe.desk.doctype.number_card.number_card import get_result

		for spec in NUMBER_CARDS:
			card = frappe.get_doc("Number Card", spec["label"])
			value = get_result(doc=card, filters=json.loads(card.filters_json or "[]"))
			self.assertIsNotNone(value, f"{spec['label']} returned nothing")
			self.assertGreaterEqual(float(value), 0)

	def test_every_chart_returns_data(self):
		from frappe.desk.doctype.dashboard_chart.dashboard_chart import get as chart_get

		for spec in DASHBOARD_CHARTS:
			result = chart_get(chart_name=spec["chart_name"])
			self.assertIn("datasets", result, f"{spec['chart_name']} produced no datasets")

	def test_the_active_vehicle_card_agrees_with_the_table(self):
		"""The card must not drift from the records it counts."""
		from frappe.desk.doctype.number_card.number_card import get_result

		card = frappe.get_doc("Number Card", "Vehicles Active")
		counted = get_result(doc=card, filters=json.loads(card.filters_json))
		self.assertEqual(
			int(counted), frappe.db.count("Vehicle", {"vehicle_status": "Active"})
		)


class TestWorkspaceShowsTheDashboard(IntegrationTestCase):
	def layout(self):
		content = frappe.db.get_value("Workspace", WORKSPACE, "content")
		return json.loads(content or "[]")

	def test_the_workspace_lays_out_the_cards_and_charts(self):
		"""Attaching a card to the workspace is not enough - it only appears
		if the layout references it too."""
		blocks = self.layout()
		laid_out = {b.get("type") for b in blocks}
		self.assertIn("number_card", laid_out, "no number cards in the layout")
		self.assertIn("chart", laid_out, "no charts in the layout")

	def test_every_laid_out_card_is_attached_to_the_workspace(self):
		workspace = frappe.get_doc("Workspace", WORKSPACE)
		attached = {c.number_card_name for c in workspace.number_cards}
		for block in self.layout():
			if block.get("type") != "number_card":
				continue
			name = block["data"]["number_card_name"]
			self.assertIn(name, attached, f"{name} is laid out but not attached")

	def test_every_laid_out_chart_is_attached_to_the_workspace(self):
		workspace = frappe.get_doc("Workspace", WORKSPACE)
		attached = {c.chart_name for c in workspace.charts}
		for block in self.layout():
			if block.get("type") != "chart":
				continue
			name = block["data"]["chart_name"]
			self.assertIn(name, attached, f"{name} is laid out but not attached")

	def test_the_dashboard_comes_before_the_link_cards(self):
		"""A manager opens this to see whether anything is wrong, so the
		figures go above the directory of links."""
		types = [b.get("type") for b in self.layout()]
		self.assertLess(
			types.index("number_card"), types.index("card"),
			"the link cards appear above the dashboard",
		)
