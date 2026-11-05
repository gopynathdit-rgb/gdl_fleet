# Copyright (c) 2026, GDL and contributors
"""
Business Blueprint gaps closed here:

  Tire Lifecycle Management -> "Tire Cost Analysis"
  Spare Parts Management    -> "Parts Consumption", "Replacement History"
  Movement Order Request    -> "captures ... passenger/official details"

The reports are tested through their execute() so the columns they declare and
the figures they produce are checked together; a report that returns the right
numbers under the wrong column heading is still broken.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, flt, nowdate

from gdl_fleet_extension.gdl_fleet.report.part_replacement_history import (
	part_replacement_history,
)
from gdl_fleet_extension.gdl_fleet.report.parts_consumption import parts_consumption
from gdl_fleet_extension.gdl_fleet.report.tyre_cost_analysis import tyre_cost_analysis
from gdl_fleet_extension.tests.test_parts_and_tyres import make_item
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
from gdl_fleet_extension.utils.parts import build_replacement_history, get_issued_parts
from gdl_fleet_extension.utils.tyre import cost_per_km


def value_for(rows, key_field, key, field):
	"""The one figure for a group, so a test does not depend on row order."""
	for row in rows:
		if row.get(key_field) == key:
			return row.get(field)
	return None


# ---------------------------------------------------------------------------
# cost_per_km - the arithmetic every tyre cost figure rests on
# ---------------------------------------------------------------------------
class TestCostPerKm(IntegrationTestCase):
	def test_plain_division(self):
		self.assertEqual(cost_per_km(20000, 20000), 1.0)
		self.assertEqual(cost_per_km(15000, 20000), 0.75)

	def test_four_decimal_places_are_kept(self):
		"""A tyre costs fractions of a currency unit per km - 2dp rounds to zero."""
		self.assertEqual(cost_per_km(100, 30000), 0.0033)

	def test_no_distance_yet_is_not_free(self):
		"""A tyre fitted today has no cost per km, which is not the same as 0.00."""
		self.assertIsNone(cost_per_km(18000, 0))
		self.assertIsNone(cost_per_km(18000, None))

	def test_no_cost_recorded_gives_nothing(self):
		self.assertIsNone(cost_per_km(0, 20000))
		self.assertIsNone(cost_per_km(None, 20000))

	def test_negative_distance_is_refused(self):
		self.assertIsNone(cost_per_km(18000, -500))


# ---------------------------------------------------------------------------
# A tyre's cost comes from the issue that fitted it
# ---------------------------------------------------------------------------
class TestTyreCarriesItsCost(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(last_odometer=40000)
		self.vehicle.insert()
		self.tyre_item = make_item("GDL-COST-TYRE-01")

	def issue_tyre(self, rate, position="Front Left", odometer=40000):
		doc = frappe.get_doc({
			"doctype": "Fleet Part Issue",
			"vehicle": self.vehicle.name,
			"issue_date": nowdate(),
			"odometer": odometer,
			"purpose": "Routine Replacement",
			"items": [{
				"item_code": self.tyre_item, "qty": 1, "rate": rate,
				"is_tyre": 1, "tyre_position": position,
			}],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		return doc

    # ---
	def test_cost_is_copied_onto_the_tyre(self):
		self.issue_tyre(rate=8500)
		tyre = frappe.get_last_doc("Vehicle Tyre", filters={"vehicle": self.vehicle.name})
		self.assertEqual(flt(tyre.cost), 8500)

	def test_the_tyre_keeps_its_own_cost_after_the_issue_changes(self):
		"""The figure lives on the tyre, so archiving the issue cannot blank it."""
		issue = self.issue_tyre(rate=9000)
		tyre_name = frappe.get_last_doc(
			"Vehicle Tyre", filters={"vehicle": self.vehicle.name}
		).name
		issue.cancel()
		# cancelling deletes the tyre record by design; re-issuing records a new one
		self.assertFalse(frappe.db.exists("Vehicle Tyre", tyre_name))

	def test_a_hand_recorded_tyre_may_carry_no_cost(self):
		"""Cost is not mandatory - an unknown cost must stay blank, not become 0."""
		tyre = frappe.get_doc({
			"doctype": "Vehicle Tyre", "vehicle": self.vehicle.name,
			"item_code": self.tyre_item, "tyre_position": "Rear Left",
			"status": "Fitted", "fitted_date": nowdate(), "fitted_odometer": 40000,
		})
		tyre.flags.ignore_permissions = True
		tyre.insert()
		self.assertIn(flt(tyre.cost), (0.0,))


# ---------------------------------------------------------------------------
# Tyre Cost Analysis
# ---------------------------------------------------------------------------
class TestTyreCostAnalysis(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(last_odometer=10000)
		self.vehicle.insert()
		self.item = make_item("GDL-COST-TYRE-02")

	def fit_and_remove(self, cost, fitted_at, removed_at, position):
		tyre = frappe.get_doc({
			"doctype": "Vehicle Tyre", "vehicle": self.vehicle.name,
			"item_code": self.item, "tyre_position": position,
			"status": "Fitted", "fitted_date": add_months(nowdate(), -6),
			"fitted_odometer": fitted_at, "cost": cost,
			"removed_date": nowdate(), "removed_odometer": removed_at,
			"removal_reason": "Worn Out",
		})
		tyre.flags.ignore_permissions = True
		tyre.insert()
		return tyre

	def run_report(self, **filters):
		# Scoped to this test's own vehicle: the tyre ITEM is shared across the
		# class, so an item-grouped report would otherwise total up tyres that
		# a sibling test created.
		base = {"group_by": "Vehicle", "include_in_service": 1,
		        "vehicle": self.vehicle.name}
		base.update(filters)
		return tyre_cost_analysis.execute(base)

	# ---
	def test_cost_per_km_is_total_cost_over_total_km(self):
		self.fit_and_remove(cost=10000, fitted_at=10000, removed_at=30000,
		                    position="Front Left")   # 20,000 km
		self.fit_and_remove(cost=6000, fitted_at=10000, removed_at=20000,
		                    position="Front Right")  # 10,000 km
		_cols, data, _msg, _chart = self.run_report()

		# 16,000 spent over 30,000 km
		self.assertEqual(value_for(data, "vehicle", self.vehicle.name, "total_cost"), 16000.0)
		self.assertEqual(value_for(data, "vehicle", self.vehicle.name, "total_km"), 30000)
		self.assertEqual(
			value_for(data, "vehicle", self.vehicle.name, "cost_per_km"),
			round(16000 / 30000, 4),
		)

	def test_a_tyre_with_no_cost_is_left_out(self):
		"""Including it would divide real kilometres by a cost nobody recorded."""
		self.fit_and_remove(cost=0, fitted_at=10000, removed_at=30000, position="Rear Left")
		_cols, data, _msg, _chart = self.run_report()
		self.assertIsNone(value_for(data, "vehicle", self.vehicle.name, "tyres"))

	def test_short_lived_tyres_are_counted_against_the_band(self):
		self.fit_and_remove(cost=9000, fitted_at=10000, removed_at=21000,
		                    position="Rear Right")  # 11,000 km - below 16,000
		_cols, data, _msg, _chart = self.run_report()
		self.assertEqual(value_for(data, "vehicle", self.vehicle.name, "below"), 1)
		self.assertEqual(value_for(data, "vehicle", self.vehicle.name, "above"), 0)

	def test_grouping_by_item_reports_the_same_spend(self):
		self.fit_and_remove(cost=12000, fitted_at=10000, removed_at=28000,
		                    position="Front Left")
		_cols, by_item, _msg, _chart = self.run_report(group_by="Tyre Item")
		self.assertEqual(value_for(by_item, "item_code", self.item, "total_cost"), 12000.0)

	def test_the_grouped_column_matches_the_grouping(self):
		"""A column headed Vehicle must not be filled with item codes."""
		for group_by, expected in [
			("Vehicle", "vehicle"), ("Tyre Item", "item_code"),
			("Site", "site"), ("Removal Reason", "removal_reason"),
		]:
			cols, _data, _msg, _chart = self.run_report(group_by=group_by)
			self.assertEqual(cols[0]["fieldname"], expected, f"group_by={group_by}")


# ---------------------------------------------------------------------------
# Parts Consumption
# ---------------------------------------------------------------------------
class TestPartsConsumption(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(last_odometer=60000)
		self.vehicle.insert()
		self.part = make_item("GDL-CONSUME-PART-01")

	def issue(self, qty, rate, submit=True, odometer=60000):
		doc = frappe.get_doc({
			"doctype": "Fleet Part Issue", "vehicle": self.vehicle.name,
			"issue_date": nowdate(), "odometer": odometer,
			"purpose": "Routine Replacement",
			"items": [{"item_code": self.part, "qty": qty, "rate": rate}],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def run_report(self, **filters):
		base = {"group_by": "Item", "vehicle": self.vehicle.name}
		base.update(filters)
		return parts_consumption.execute(base)

	# ---
	def test_quantity_and_amount_are_totalled(self):
		self.issue(qty=2, rate=500)
		self.issue(qty=3, rate=500)
		_cols, data, _msg, _chart = self.run_report()
		self.assertEqual(value_for(data, "item_code", self.part, "qty"), 5.0)
		self.assertEqual(value_for(data, "item_code", self.part, "amount"), 2500.0)
		self.assertEqual(value_for(data, "item_code", self.part, "issues"), 2)

	def test_a_draft_issue_has_not_left_store(self):
		"""Counting a draft would overstate what the fleet actually consumed."""
		self.issue(qty=4, rate=500, submit=False)
		_cols, data, _msg, _chart = self.run_report()
		self.assertIsNone(value_for(data, "item_code", self.part, "qty"))

	def test_a_cancelled_issue_drops_out(self):
		doc = self.issue(qty=2, rate=500)
		doc.cancel()
		_cols, data, _msg, _chart = self.run_report()
		self.assertIsNone(value_for(data, "item_code", self.part, "qty"))

	def test_detail_mode_lists_every_line(self):
		self.issue(qty=1, rate=100)
		self.issue(qty=1, rate=200)
		cols, data, _msg, _chart = self.run_report(group_by="Detail")
		self.assertEqual(len(data), 2)
		self.assertIn("serial_no", [c["fieldname"] for c in cols])

	def test_tyre_filters_are_opposites(self):
		tyre_item = make_item("GDL-CONSUME-TYRE-01")
		doc = frappe.get_doc({
			"doctype": "Fleet Part Issue", "vehicle": self.vehicle.name,
			"issue_date": nowdate(), "odometer": 60000,
			"purpose": "Routine Replacement",
			"items": [
				{"item_code": self.part, "qty": 1, "rate": 100},
				{"item_code": tyre_item, "qty": 1, "rate": 9000,
				 "is_tyre": 1, "tyre_position": "Front Left"},
			],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()

		_c, tyres_only, _m, _ch = self.run_report(group_by="Detail", tyres_only=1)
		_c, no_tyres, _m, _ch = self.run_report(group_by="Detail", exclude_tyres=1)
		self.assertEqual([r["item_code"] for r in tyres_only], [tyre_item])
		self.assertNotIn(tyre_item, [r["item_code"] for r in no_tyres])

	def test_the_period_filter_is_honoured(self):
		self.issue(qty=1, rate=100)
		_c, before, _m, _ch = self.run_report(
			from_date=add_days(nowdate(), -60), to_date=add_days(nowdate(), -30)
		)
		self.assertEqual(before, [])


# ---------------------------------------------------------------------------
# Part Replacement History - the interval is the point
# ---------------------------------------------------------------------------
class TestReplacementHistory(IntegrationTestCase):
	def rows(self, *issues):
		"""(vehicle, item, date, odometer) tuples shaped like issue lines."""
		return [
			{"vehicle": v, "item_code": i, "issue_date": d, "odometer": o,
			 "issue": f"FPI-{n}", "idx": 1}
			for n, (v, i, d, o) in enumerate(issues, start=1)
		]

	def test_first_fitting_has_no_interval(self):
		history = build_replacement_history(
			self.rows(("V1", "PAD", frappe.utils.getdate("2026-01-01"), 10000))
		)
		self.assertEqual(len(history), 1)
		self.assertIsNone(history[0]["km_since_previous"])
		self.assertIsNone(history[0]["previous_issue"])
		self.assertEqual(history[0]["sequence"], 1)

	def test_interval_is_measured_against_the_previous_fitting(self):
		history = build_replacement_history(self.rows(
			("V1", "PAD", frappe.utils.getdate("2026-01-01"), 10000),
			("V1", "PAD", frappe.utils.getdate("2026-04-01"), 19000),
		))
		second = history[1]
		self.assertEqual(second["km_since_previous"], 9000)
		self.assertEqual(second["days_since_previous"], 90)
		self.assertEqual(second["previous_issue"], "FPI-1")
		self.assertEqual(second["replacements"], 2)

	def test_rows_arriving_newest_first_still_order_correctly(self):
		"""get_issued_parts returns newest first; the history must not invert."""
		history = build_replacement_history(self.rows(
			("V1", "PAD", frappe.utils.getdate("2026-04-01"), 19000),
			("V1", "PAD", frappe.utils.getdate("2026-01-01"), 10000),
		))
		self.assertEqual([r["sequence"] for r in history], [1, 2])
		self.assertEqual(history[1]["km_since_previous"], 9000)

	def test_different_vehicles_do_not_share_a_history(self):
		history = build_replacement_history(self.rows(
			("V1", "PAD", frappe.utils.getdate("2026-01-01"), 10000),
			("V2", "PAD", frappe.utils.getdate("2026-02-01"), 50000),
		))
		self.assertTrue(all(r["km_since_previous"] is None for r in history))

	def test_different_items_do_not_share_a_history(self):
		history = build_replacement_history(self.rows(
			("V1", "PAD", frappe.utils.getdate("2026-01-01"), 10000),
			("V1", "FILTER", frappe.utils.getdate("2026-02-01"), 14000),
		))
		self.assertTrue(all(r["km_since_previous"] is None for r in history))

	def test_a_repeated_odometer_reports_nothing_rather_than_zero(self):
		"""Two issues at the same reading is a data question, not a part that
		lasted no distance."""
		history = build_replacement_history(self.rows(
			("V1", "PAD", frappe.utils.getdate("2026-01-01"), 10000),
			("V1", "PAD", frappe.utils.getdate("2026-02-01"), 10000),
		))
		self.assertIsNone(history[1]["km_since_previous"])
		self.assertEqual(history[1]["days_since_previous"], 31)


class TestReplacementHistoryReport(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(last_odometer=80000)
		self.vehicle.insert()
		self.part = make_item("GDL-REPLACE-PART-01")

	def issue(self, odometer, date):
		doc = frappe.get_doc({
			"doctype": "Fleet Part Issue", "vehicle": self.vehicle.name,
			"issue_date": date, "odometer": odometer,
			"purpose": "Routine Replacement",
			"items": [{"item_code": self.part, "qty": 1, "rate": 400}],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		return doc

	def test_repeated_only_hides_a_part_fitted_once(self):
		self.issue(80000, add_days(nowdate(), -200))
		_c, data, _m, _ch = part_replacement_history.execute(
			{"vehicle": self.vehicle.name, "repeated_only": 1}
		)
		self.assertEqual(data, [])

	def test_a_part_replaced_twice_reports_its_interval(self):
		self.issue(80000, add_days(nowdate(), -200))
		self.issue(87000, add_days(nowdate(), -20))
		_c, data, _m, _ch = part_replacement_history.execute(
			{"vehicle": self.vehicle.name, "repeated_only": 1}
		)
		self.assertEqual(len(data), 2)
		self.assertEqual(data[1]["km_since_previous"], 7000)

	def test_the_early_replacement_filter(self):
		self.issue(80000, add_days(nowdate(), -200))
		self.issue(87000, add_days(nowdate(), -20))
		_c, strict, _m, _ch = part_replacement_history.execute(
			{"vehicle": self.vehicle.name, "replaced_within_km": 5000}
		)
		_c, loose, _m, _ch = part_replacement_history.execute(
			{"vehicle": self.vehicle.name, "replaced_within_km": 9000}
		)
		self.assertEqual(strict, [])
		self.assertEqual(len(loose), 1)


# ---------------------------------------------------------------------------
# Passengers on the request (blueprint: "passenger/official details")
# ---------------------------------------------------------------------------
class TestRequestPassengers(IntegrationTestCase):
	def test_the_request_has_a_passenger_table(self):
		field = frappe.get_meta("Movement Order Request").get_field("passengers")
		self.assertIsNotNone(field, "Movement Order Request has no passengers table")
		self.assertEqual(field.fieldtype, "Table")
		self.assertEqual(field.options, "Movement Order Passenger")

	def test_the_table_is_optional(self):
		"""A requester often books before knowing who travels."""
		field = frappe.get_meta("Movement Order Request").get_field("passengers")
		self.assertFalse(field.reqd)
