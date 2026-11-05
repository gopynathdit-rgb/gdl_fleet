# Copyright (c) 2026, GDL and contributors
"""
Spare-part and tyre issuance (final document GAP item 4) and the
20,000 km +/-20% tyre performance target (Tire Mileage).
"""

from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
from gdl_fleet_extension.utils.tyre import (
	ABOVE,
	BELOW,
	IN_SERVICE,
	WITHIN,
	classify_tyre,
	get_tyre_target,
	get_tyre_tolerance,
	tyre_bounds,
	tyre_deviation_percent,
)

TARGET, TOL = 20000, Decimal("20")


def make_item(code, serialised=False, is_tyre=False):
	if frappe.db.exists("Item", code):
		return code
	doc = frappe.get_doc({
		"doctype": "Item", "item_code": code, "item_name": code,
		"item_group": "All Item Groups", "stock_uom": "Nos",
		"is_stock_item": 1, "has_serial_no": 1 if serialised else 0,
	})
	if serialised:
		doc.serial_no_series = f"{code}-.#####"
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


class TestTyreTarget(IntegrationTestCase):
	def test_band_is_target_plus_minus_tolerance(self):
		low, high = tyre_bounds(TARGET, TOL)
		self.assertEqual(low, Decimal("16000"))
		self.assertEqual(high, Decimal("24000"))

	def test_on_target(self):
		self.assertEqual(classify_tyre(20000, TARGET, TOL), WITHIN)

	def test_boundaries_are_inclusive(self):
		self.assertEqual(classify_tyre(16000, TARGET, TOL), WITHIN)
		self.assertEqual(classify_tyre(24000, TARGET, TOL), WITHIN)

	def test_just_outside_the_band(self):
		self.assertEqual(classify_tyre(15999, TARGET, TOL), BELOW)
		self.assertEqual(classify_tyre(24001, TARGET, TOL), ABOVE)

	def test_not_yet_removed_is_in_service(self):
		self.assertEqual(classify_tyre(None, TARGET, TOL), IN_SERVICE)

	def test_deviation_percent(self):
		self.assertEqual(tyre_deviation_percent(10000, TARGET), Decimal("-50"))
		self.assertEqual(tyre_deviation_percent(30000, TARGET), Decimal("50"))

	def test_target_and_tolerance_are_configuration(self):
		self.assertEqual(get_tyre_target(), 20000)
		self.assertEqual(get_tyre_tolerance(), Decimal("20"))


class TestFleetPartIssue(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(last_odometer=50000)
		self.vehicle.insert()
		self.part = make_item("GDL-TEST-PART-01")
		self.tyre = make_item("GDL-TEST-TYRE-01")

	def make_issue(self, items, submit=False, odometer=50000, **kwargs):
		values = {
			"doctype": "Fleet Part Issue", "vehicle": self.vehicle.name,
			"issue_date": nowdate(), "odometer": odometer,
			"purpose": "Routine Replacement", "items": items,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert()
		if submit:
			doc.submit()
		return doc

	# --- validation -----------------------------------------------------
	def test_issue_needs_at_least_one_item(self):
		self.assertRaises(frappe.ValidationError, self.make_issue, [])

	def test_zero_qty_is_rejected(self):
		self.assertRaises(frappe.ValidationError, self.make_issue,
		                  [{"item_code": self.part, "qty": 0, "rate": 100}])

	def test_amount_is_calculated(self):
		doc = self.make_issue([{"item_code": self.part, "qty": 3, "rate": 250}])
		self.assertEqual(flt(doc.items[0].amount), 750)
		self.assertEqual(flt(doc.total_amount), 750)
		self.assertEqual(flt(doc.total_qty), 3)

	def test_a_tyre_must_be_issued_one_per_row(self):
		"""Each tyre is tracked to the kilometres it achieves."""
		self.assertRaises(frappe.ValidationError, self.make_issue,
		                  [{"item_code": self.tyre, "qty": 4, "rate": 9000,
		                    "is_tyre": 1, "tyre_position": "Front Left"}])

	def test_a_tyre_needs_a_position(self):
		self.assertRaises(frappe.ValidationError, self.make_issue,
		                  [{"item_code": self.tyre, "qty": 1, "rate": 9000, "is_tyre": 1}])

	def test_duplicate_serial_on_one_issue_is_rejected(self):
		self.assertRaises(frappe.ValidationError, self.make_issue, [
			{"item_code": self.part, "qty": 1, "rate": 10, "serial_no": "SN-DUP"},
			{"item_code": self.part, "qty": 1, "rate": 10, "serial_no": "SN-DUP"},
		])

	def test_negative_odometer_is_rejected(self):
		self.assertRaises(frappe.ValidationError, self.make_issue,
		                  [{"item_code": self.part, "qty": 1, "rate": 10}], odometer=-5)

	# --- tyre lifecycle --------------------------------------------------
	def test_submitting_creates_a_tyre_record(self):
		doc = self.make_issue([{"item_code": self.tyre, "qty": 1, "rate": 9000,
		                        "is_tyre": 1, "tyre_position": "Front Left",
		                        "serial_no": f"TY-{frappe.generate_hash(length=6)}"}],
		                      submit=True)
		tyres = frappe.get_all("Vehicle Tyre", filters={"part_issue": doc.name},
		                       fields=["name", "status", "fitted_odometer", "tyre_position"])
		self.assertEqual(len(tyres), 1)
		self.assertEqual(tyres[0].status, "Fitted")
		self.assertEqual(tyres[0].fitted_odometer, 50000)
		self.assertEqual(tyres[0].tyre_position, "Front Left")

	def test_a_plain_part_creates_no_tyre_record(self):
		doc = self.make_issue([{"item_code": self.part, "qty": 2, "rate": 100}], submit=True)
		self.assertEqual(frappe.db.count("Vehicle Tyre", {"part_issue": doc.name}), 0)

	def test_same_tyre_cannot_be_fitted_twice(self):
		serial = f"TY-{frappe.generate_hash(length=6)}"
		row = {"item_code": self.tyre, "qty": 1, "rate": 9000, "is_tyre": 1,
		       "tyre_position": "Front Left", "serial_no": serial}
		self.make_issue([row], submit=True)
		self.assertRaises(frappe.ValidationError, self.make_issue, [dict(row)])

	def test_cancelling_removes_the_tyre_record(self):
		doc = self.make_issue([{"item_code": self.tyre, "qty": 1, "rate": 9000,
		                        "is_tyre": 1, "tyre_position": "Rear Left",
		                        "serial_no": f"TY-{frappe.generate_hash(length=6)}"}],
		                      submit=True)
		self.assertEqual(frappe.db.count("Vehicle Tyre", {"part_issue": doc.name}), 1)
		doc.cancel()
		self.assertEqual(frappe.db.count("Vehicle Tyre", {"part_issue": doc.name}), 0)

	def test_status_follows_docstatus(self):
		doc = self.make_issue([{"item_code": self.part, "qty": 1, "rate": 10}])
		self.assertEqual(doc.status, "Draft")
		doc.submit()
		self.assertEqual(frappe.db.get_value("Fleet Part Issue", doc.name, "status"), "Issued")

	def test_the_module_keeps_no_stock_of_its_own(self):
		"""Quantities live in ERPNext stock, never in a parallel fleet ledger."""
		for name in ("Fleet Stock", "Fleet Part Balance", "Vehicle Stock"):
			self.assertFalse(frappe.db.exists("DocType", name))


class TestVehicleTyreLifecycle(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(last_odometer=50000)
		self.vehicle.insert()
		self.item = make_item("GDL-TEST-TYRE-02")

	def make_tyre(self, fitted=50000, removed=None, **kwargs):
		values = {
			"doctype": "Vehicle Tyre", "vehicle": self.vehicle.name,
			"item_code": self.item, "tyre_position": "Front Left",
			"fitted_date": add_days(nowdate(), -200), "fitted_odometer": fitted,
			"serial_no": f"TY-{frappe.generate_hash(length=6)}",
		}
		if removed is not None:
			values["removed_odometer"] = removed
			values["removed_date"] = nowdate()
			values["removal_reason"] = "Worn Out"
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc

	def test_in_service_tyre_has_no_km_achieved(self):
		t = self.make_tyre()
		self.assertIsNone(t.km_achieved)
		self.assertEqual(t.performance, "In Service")

	def test_km_achieved_on_removal(self):
		t = self.make_tyre(fitted=50000, removed=70000)
		self.assertEqual(t.km_achieved, 20000)
		self.assertEqual(t.performance, "Within Tolerance")
		self.assertEqual(t.status, "Removed")

	def test_tyre_that_fell_short(self):
		t = self.make_tyre(fitted=50000, removed=61000)   # 11,000 km
		self.assertEqual(t.km_achieved, 11000)
		self.assertEqual(t.performance, "Below Tolerance")

	def test_tyre_that_ran_beyond_the_band(self):
		t = self.make_tyre(fitted=50000, removed=80000)   # 30,000 km
		self.assertEqual(t.performance, "Above Tolerance")

	def test_removed_odometer_cannot_precede_fitted(self):
		self.assertRaises(frappe.ValidationError, self.make_tyre, 50000, 40000)

	def test_target_is_stamped_from_settings(self):
		self.assertEqual(self.make_tyre().target_km, 20000)

	def test_report_runs_and_explains_the_band(self):
		self.make_tyre(fitted=50000, removed=70000)
		result = frappe.get_attr(
			"gdl_fleet_extension.gdl_fleet.report.tyre_mileage_report.tyre_mileage_report.execute"
		)({"vehicle": self.vehicle.name})
		self.assertTrue(result[0])
		self.assertIn("20,000 km", result[2])
		rows = [r for r in result[1] if r["vehicle"] == self.vehicle.name]
		self.assertTrue(rows)
		self.assertEqual(rows[0]["km_so_far"], 20000)
