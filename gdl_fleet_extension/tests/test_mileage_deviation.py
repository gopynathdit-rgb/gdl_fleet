# Copyright (c) 2026, GDL and contributors
"""
Optimal Fleet Utilization - minimum mileage per vehicle and +/-10% deviation.

GDL confirmed the tolerance applies in BOTH directions, so a vehicle running
well above its target is flagged as well as one running below it.
"""

from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase

from gdl_fleet_extension.tests.fleet_settings_guard import FleetSettingsGuard
from frappe.utils import add_days, flt, nowdate

from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
from gdl_fleet_extension.tests.test_pol import fuel_supplier
from gdl_fleet_extension.utils.mileage_deviation import (
	ABOVE,
	BELOW,
	NOT_APPLICABLE,
	WITHIN,
	classify,
	deviation_percent,
	get_tolerance,
	get_vehicle_mileage,
	needs_hr_approval,
)

TOL = Decimal("10")


class TestMileageDeviationCalculation(FleetSettingsGuard, IntegrationTestCase):
	def test_deviation_is_signed(self):
		self.assertEqual(deviation_percent("7.2", "8"), Decimal("-10"))
		self.assertEqual(deviation_percent("8.8", "8"), Decimal("10"))

	def test_on_target_is_within(self):
		self.assertEqual(classify(8.0, 8.0, TOL)[0], WITHIN)

	def test_boundaries_are_inclusive(self):
		self.assertEqual(classify(7.2, 8.0, TOL)[0], WITHIN)
		self.assertEqual(classify(8.8, 8.0, TOL)[0], WITHIN)

	def test_just_below_tolerance_is_flagged(self):
		self.assertEqual(classify(7.19, 8.0, TOL)[0], BELOW)

	def test_just_above_tolerance_is_flagged(self):
		"""Both directions - running too well usually means a missed fill."""
		self.assertEqual(classify(8.81, 8.0, TOL)[0], ABOVE)

	def test_hr_approval_required_in_both_directions(self):
		self.assertTrue(needs_hr_approval(7.19, 8.0, TOL))
		self.assertTrue(needs_hr_approval(8.81, 8.0, TOL))
		self.assertFalse(needs_hr_approval(8.00, 8.0, TOL))

	def test_zero_minimum_is_not_applicable(self):
		"""The chart gives the BYD EV a minimum of 0; km/l is meaningless there."""
		self.assertEqual(classify(5.0, 0, TOL)[0], NOT_APPLICABLE)
		self.assertIsNone(classify(5.0, 0, TOL)[1])

	def test_missing_minimum_is_not_applicable(self):
		self.assertEqual(classify(5.0, None, TOL)[0], NOT_APPLICABLE)

	def test_ev_never_requires_hr_approval(self):
		self.assertFalse(needs_hr_approval(0, 0, TOL))

	def test_no_float_drift_at_the_boundary(self):
		self.assertEqual(deviation_percent("7.2", "8"), Decimal("-10"))

	def test_tolerance_is_configuration(self):
		frappe.db.set_single_value("GDL Fleet Settings", "mileage_deviation_tolerance", 25)
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
		try:
			self.assertEqual(get_tolerance(), Decimal("25"))
			self.assertEqual(classify(6.5, 8.0)[0], WITHIN)   # -18.75%, inside 25
		finally:
			frappe.db.set_single_value("GDL Fleet Settings", "mileage_deviation_tolerance", 10)
			frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def test_chart_targets_from_the_document(self):
		"""Spot-check the minimums in the mileage chart."""
		for actual, minimum in ((8.0, 8.0), (9.0, 9.0), (6.5, 6.5), (7.45, 7.45),
		                        (10.0, 10.0), (12.0, 12.0), (3.0, 3.0), (8.5, 8.5)):
			self.assertEqual(classify(actual, minimum, TOL)[0], WITHIN,
			                 f"{actual} against minimum {minimum}")


class TestMileageOnPOLAbstract(FleetSettingsGuard, IntegrationTestCase):
	def setUp(self):
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def make_abstract(self, min_mileage, closing_km, litres, submit=False, **kwargs):
		vehicle = new_vehicle(last_odometer=10000, min_mileage=min_mileage)
		vehicle.insert()
		values = {
			"doctype": "POL Abstract", "vehicle": vehicle.name,
			"abstract_date": nowdate(), "period_from": add_days(nowdate(), -30),
			"period_to": nowdate(), "distance_basis": "KM",
			"opening_km": 10000, "closing_km": closing_km,
			"previous_tank_balance": 0, "present_tank_balance": 0,
			"recoupment_stcbl": 100000,
			"supplier_bill_attachment": "/files/test-supplier-bill.pdf",
			"entries": [{"supplier": fuel_supplier("STCBL"), "supply_memo_no": f"M-{frappe.generate_hash(length=6)}",
			             "date": nowdate(), "litres": litres, "rate": 100}],
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def test_vehicle_carries_a_minimum_mileage(self):
		v = new_vehicle(min_mileage=8.0)
		v.insert()
		self.assertEqual(flt(v.min_mileage), 8.0)

	def test_on_target_abstract_saves_without_a_reason(self):
		# 800 km on 100 L = 8.00 km/l against a minimum of 8
		doc = self.make_abstract(8.0, 10800, 100)
		self.assertEqual(doc.mileage_status, "Within Tolerance")
		self.assertAlmostEqual(doc.mileage_deviation, 0.0, places=4)

	def test_under_target_requires_a_deviation_reason(self):
		# 700 km on 100 L = 7.00 km/l, 12.5% under a minimum of 8
		self.assertRaises(frappe.ValidationError, self.make_abstract, 8.0, 10700, 100)

	def test_over_target_also_requires_a_reason(self):
		# 1000 km on 100 L = 10.00 km/l, 25% over a minimum of 8
		self.assertRaises(frappe.ValidationError, self.make_abstract, 8.0, 11000, 100)

	def test_reason_allows_the_abstract_through(self):
		doc = self.make_abstract(8.0, 10700, 100,
		                         deviation_reason="Hill route with heavy load all month")
		self.assertEqual(doc.mileage_status, "Below Tolerance")
		self.assertLess(doc.mileage_deviation, -10)

	def test_ev_is_never_held_up(self):
		"""Minimum 0 means efficiency does not apply."""
		doc = self.make_abstract(0, 11000, 100)
		self.assertEqual(doc.mileage_status, "Not Applicable")
		self.assertIsNone(doc.mileage_deviation)

	def test_hr_requirement_is_configurable(self):
		frappe.db.set_single_value("GDL Fleet Settings", "mileage_requires_hr_approval", 0)
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
		try:
			doc = self.make_abstract(8.0, 10700, 100)
			self.assertEqual(doc.mileage_status, "Below Tolerance")
		finally:
			frappe.db.set_single_value("GDL Fleet Settings", "mileage_requires_hr_approval", 1)
			frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def test_dashboard_reports_the_vehicle(self):
		doc = self.make_abstract(8.0, 10800, 100, submit=True)
		rows = get_vehicle_mileage(vehicle=doc.vehicle)
		self.assertTrue(rows)
		row = rows[0]
		self.assertAlmostEqual(row["actual_mileage"], 8.0, places=2)
		self.assertEqual(row["min_mileage"], 8.0)
		self.assertEqual(row["status"], WITHIN)
		self.assertFalse(row["hr_approval_required"])

	def test_dashboard_flags_a_deviating_vehicle(self):
		doc = self.make_abstract(8.0, 10700, 100, submit=True,
		                         deviation_reason="Hill route")
		row = next(r for r in get_vehicle_mileage(vehicle=doc.vehicle))
		self.assertEqual(row["status"], BELOW)
		self.assertTrue(row["hr_approval_required"])

	def test_dashboard_report_runs(self):
		self.make_abstract(8.0, 10800, 100, submit=True)
		result = frappe.get_attr(
			"gdl_fleet_extension.gdl_fleet.report.mileage_deviation_dashboard."
			"mileage_deviation_dashboard.execute"
		)({})
		self.assertTrue(result[0])
		self.assertIn("both directions", result[2])
