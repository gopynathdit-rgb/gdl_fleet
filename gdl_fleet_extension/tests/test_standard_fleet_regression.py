# Copyright (c) 2026, GDL and contributors
"""
Proves that STANDARD ERPNext/HRMS fleet behaviour is unchanged by this app.

erpnext's own test modules cannot be discovered on this site (their global test
records collide with existing data), so the standard flows are exercised directly.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, nowdate

from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle


def get_employee():
	name = frappe.db.get_value("Employee", {"status": "Active"}, "name") or frappe.db.get_value(
		"Employee", {}, "name"
	)
	return name


class TestStandardFleetRegression(IntegrationTestCase):
	def setUp(self):
		self.employee = get_employee()
		if not self.employee:
			self.skipTest("no Employee on this site")

	def make_log(self, vehicle, odometer, **kwargs):
		values = {
			"doctype": "Vehicle Log",
			"license_plate": vehicle.name,
			"employee": self.employee,
			"date": nowdate(),
			"odometer": odometer,
			# section 4.3 makes this mandatory
			"place_to_travel": "Local",
		}
		values.update(kwargs)
		return frappe.get_doc(values)

	# --- standard odometer roll-forward ------------------------------------
	def test_vehicle_log_submit_updates_vehicle_odometer(self):
		vehicle = new_vehicle(last_odometer=1000)
		vehicle.insert()

		log = self.make_log(vehicle, 1500)
		log.insert()
		log.submit()

		self.assertEqual(frappe.db.get_value("Vehicle", vehicle.name, "last_odometer"), 1500)

	def test_vehicle_log_rejects_odometer_below_last(self):
		"""Standard hrms validation must still fire."""
		vehicle = new_vehicle(last_odometer=5000)
		vehicle.insert()

		log = self.make_log(vehicle, 100)
		self.assertRaises(frappe.ValidationError, log.insert)

	# --- standard refuelling + service child table -------------------------
	def test_standard_refuelling_and_service_fields_intact(self):
		vehicle = new_vehicle(last_odometer=1000)
		vehicle.insert()

		service_item = "_Test GDL Oil Change"
		if not frappe.db.exists("Vehicle Service Item", service_item):
			frappe.get_doc(
				{"doctype": "Vehicle Service Item", "service_item": service_item}
			).insert()

		log = self.make_log(vehicle, 1200, fuel_qty=40, price=90, invoice="INV-001")
		log.append(
			"service_detail",
			{
				"service_item": service_item,
				"type": "Change",
				"frequency": "Mileage",
				"expense_amount": 2500,
			},
		)
		log.insert()
		log.submit()

		log.reload()
		self.assertEqual(flt(log.fuel_qty), 40)
		self.assertEqual(flt(log.price), 90)
		self.assertEqual(len(log.service_detail), 1)
		self.assertEqual(flt(log.service_detail[0].expense_amount), 2500)

	# --- standard Expense Claim creation from a Vehicle Log ----------------
	def test_make_expense_claim_from_vehicle_log_still_works(self):
		from hrms.hr.doctype.vehicle_log.vehicle_log import make_expense_claim

		vehicle = new_vehicle(last_odometer=1000)
		vehicle.insert()

		log = self.make_log(vehicle, 1300, fuel_qty=10, price=100)
		log.insert()
		log.submit()

		claim = make_expense_claim(log.name)
		self.assertEqual(claim.get("vehicle_log"), log.name)
		self.assertEqual(flt(claim.get("expenses")[0].get("amount")), 1000)

	# --- standard report still runs ----------------------------------------
	def test_standard_vehicle_expenses_report_still_runs(self):
		from hrms.hr.report.vehicle_expenses.vehicle_expenses import execute

		vehicle = new_vehicle(last_odometer=1000)
		vehicle.insert()
		log = self.make_log(vehicle, 1400, fuel_qty=20, price=100)
		log.insert()
		log.submit()

		columns, data = execute(
			{
				"filter_based_on": "Date Range",
				"from_date": frappe.utils.add_days(nowdate(), -1),
				"to_date": frappe.utils.add_days(nowdate(), 1),
			}
		)[:2]

		self.assertTrue(columns)
		rows = [row for row in data if row.get("vehicle") == vehicle.name]
		self.assertEqual(len(rows), 1)
		self.assertEqual(flt(rows[0]["fuel_expense"]), 2000)

	# --- standard Vehicle fields untouched ---------------------------------
	def test_standard_vehicle_naming_unchanged(self):
		meta = frappe.get_meta("Vehicle")
		self.assertEqual(meta.autoname, "field:license_plate")
		self.assertTrue(meta.get_field("license_plate").unique)

	def test_standard_vehicle_service_child_table_intact(self):
		meta = frappe.get_meta("Vehicle Log")
		field = meta.get_field("service_detail")
		self.assertEqual(field.options, "Vehicle Service")
		for fieldname in ("odometer", "last_odometer", "fuel_qty", "price", "supplier", "invoice"):
			self.assertTrue(meta.get_field(fieldname), f"standard Vehicle Log field {fieldname} missing")
