# Copyright (c) 2026, GDL and contributors
"""Phase 5 - standard Vehicle Log extension and the odometer cancellation fix."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, cint, nowdate

from gdl_fleet_extension.utils.odometer import get_last_odometer, get_odometer_readings
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle


def get_employee():
	return frappe.db.get_value("Employee", {"status": "Active"}, "name") or frappe.db.get_value(
		"Employee", {}, "name"
	)


class TestVehicleLogExtension(IntegrationTestCase):
	def setUp(self):
		self.employee = get_employee()
		if not self.employee:
			self.skipTest("no Employee on this site")

	def make_vehicle(self, last_odometer=1000, **kwargs):
		vehicle = new_vehicle(last_odometer=last_odometer, **kwargs)
		vehicle.insert()
		return vehicle

	def make_log(self, vehicle, odometer, submit=True, **kwargs):
		# Section 4.3 allows one primary daily record per vehicle, so a sequence of
		# readings is spread across consecutive days as it would be in practice.
		existing = frappe.db.count(
			"Vehicle Log", {"license_plate": vehicle.name, "docstatus": ("<", 2)}
		)
		values = {
			"doctype": "Vehicle Log",
			"license_plate": vehicle.name,
			"employee": self.employee,
			"date": add_days(nowdate(), -20 + existing),
			"odometer": odometer,
			"usage_type": "Official",
			"place_to_travel": "Local",
		}
		values.update(kwargs)
		log = frappe.get_doc(values)
		log.insert()
		if submit:
			log.submit()
		return log

	def vehicle_odometer(self, vehicle):
		return cint(frappe.db.get_value("Vehicle", vehicle.name, "last_odometer"))

	# --- the override is actually in force -----------------------------------
	def test_override_class_is_active(self):
		from gdl_fleet_extension.overrides.vehicle_log import GDLVehicleLog

		doc = frappe.get_doc({"doctype": "Vehicle Log"})
		self.assertIsInstance(doc, GDLVehicleLog)

	def test_no_duplicate_vehicle_log_doctype(self):
		"""The standard DocType must be extended, never cloned."""
		for name in ("GDL Vehicle Log", "Fleet Vehicle Log", "Vehicle Log Entry"):
			self.assertFalse(frappe.db.exists("DocType", name), f"{name} should not exist")
		self.assertEqual(frappe.db.get_value("DocType", "Vehicle Log", "module"), "HR")

	# --- fields ---------------------------------------------------------------
	def test_custom_fields_present(self):
		meta = frappe.get_meta("Vehicle Log")
		for fieldname in (
			"driver", "usage_type", "start_location", "destination", "purpose",
			"site", "department", "cost_center", "project",
			"start_odometer", "distance_travelled", "movement_order",
			"place_to_travel", "gdl_remarks",
		):
			self.assertTrue(meta.get_field(fieldname), f"missing custom field {fieldname}")

		# standard fields must survive
		for fieldname in ("license_plate", "odometer", "last_odometer", "fuel_qty",
		                  "price", "supplier", "invoice", "service_detail"):
			self.assertTrue(meta.get_field(fieldname), f"standard field {fieldname} lost")

	def test_no_duplicate_vehicle_field(self):
		"""`license_plate` is already the Link to Vehicle."""
		meta = frappe.get_meta("Vehicle Log")
		self.assertEqual(meta.get_field("license_plate").options, "Vehicle")
		self.assertIsNone(meta.get_field("vehicle"))

	# --- distance -------------------------------------------------------------
	def test_distance_calculation(self):
		vehicle = self.make_vehicle(last_odometer=1000)
		log = self.make_log(vehicle, 1250, start_odometer=1000)
		self.assertEqual(cint(log.distance_travelled), 250)

	def test_start_odometer_defaults_to_latest_reading(self):
		vehicle = self.make_vehicle(last_odometer=4200)
		log = self.make_log(vehicle, 4500)
		self.assertEqual(cint(log.start_odometer), 4200)
		self.assertEqual(cint(log.distance_travelled), 300)

	def test_ending_below_starting_rejected(self):
		vehicle = self.make_vehicle(last_odometer=1000)
		log = frappe.get_doc({
			"doctype": "Vehicle Log", "license_plate": vehicle.name,
			"employee": self.employee, "date": nowdate(),
			"start_odometer": 2000, "odometer": 1500, "usage_type": "Official", "place_to_travel": "Local",
		})
		self.assertRaises(frappe.ValidationError, log.insert)

	def test_standard_backwards_odometer_guard_still_fires(self):
		"""Standard hrms rule: reading below the vehicle's current one."""
		vehicle = self.make_vehicle(last_odometer=5000)
		log = frappe.get_doc({
			"doctype": "Vehicle Log", "license_plate": vehicle.name,
			"employee": self.employee, "date": nowdate(),
			"odometer": 100, "usage_type": "Official", "place_to_travel": "Local",
		})
		self.assertRaises(frappe.ValidationError, log.insert)

	# --- sequential readings --------------------------------------------------
	def test_sequential_logs_advance_the_vehicle(self):
		vehicle = self.make_vehicle(last_odometer=1000)
		self.make_log(vehicle, 1200)
		self.assertEqual(self.vehicle_odometer(vehicle), 1200)
		self.make_log(vehicle, 1500)
		self.assertEqual(self.vehicle_odometer(vehicle), 1500)
		self.make_log(vehicle, 1900)
		self.assertEqual(self.vehicle_odometer(vehicle), 1900)

	# --- THE DEFECT FIX -------------------------------------------------------
	def test_cancelling_the_latest_log_reverts_to_previous_reading(self):
		vehicle = self.make_vehicle(last_odometer=1000)
		self.make_log(vehicle, 1200)
		latest = self.make_log(vehicle, 1500)

		latest.cancel()
		self.assertEqual(
			self.vehicle_odometer(vehicle), 1200,
			"cancelling the latest log should fall back to the previous reading",
		)

	def test_cancelling_an_older_log_does_not_move_the_odometer(self):
		"""The standard ERPNext defect. Cancelling an OLDER log must change nothing."""
		vehicle = self.make_vehicle(last_odometer=1000)
		older = self.make_log(vehicle, 1200)
		self.make_log(vehicle, 1500)
		self.make_log(vehicle, 1900)

		self.assertEqual(self.vehicle_odometer(vehicle), 1900)
		older.cancel()

		self.assertEqual(
			self.vehicle_odometer(vehicle), 1900,
			"cancelling an older log must NOT reduce the vehicle's current odometer",
		)

	def test_cancelling_a_middle_log_does_not_move_the_odometer(self):
		vehicle = self.make_vehicle(last_odometer=1000)
		self.make_log(vehicle, 1200)
		middle = self.make_log(vehicle, 1500)
		self.make_log(vehicle, 1900)

		middle.cancel()
		self.assertEqual(self.vehicle_odometer(vehicle), 1900)

	def test_cancelling_every_log_falls_back_to_opening_odometer(self):
		vehicle = self.make_vehicle(last_odometer=1000, opening_odometer=800)
		first = self.make_log(vehicle, 1200)
		second = self.make_log(vehicle, 1500)

		second.cancel()
		first.cancel()
		self.assertEqual(
			self.vehicle_odometer(vehicle), 800,
			"with no live readings the vehicle should fall back to its opening odometer",
		)

	def test_cancel_order_does_not_matter(self):
		"""Cancelling oldest-first then newest must land on the same value."""
		vehicle = self.make_vehicle(last_odometer=1000)
		a = self.make_log(vehicle, 1200)
		b = self.make_log(vehicle, 1500)
		c = self.make_log(vehicle, 1900)

		a.cancel()
		self.assertEqual(self.vehicle_odometer(vehicle), 1900)
		c.cancel()
		self.assertEqual(self.vehicle_odometer(vehicle), 1500)
		b.cancel()
		# falls back to the opening odometer, which defaulted to the reading the
		# vehicle was created with
		self.assertEqual(self.vehicle_odometer(vehicle), 1000)

	# --- odometer helper ------------------------------------------------------
	def test_readings_exclude_cancelled_documents(self):
		vehicle = self.make_vehicle(last_odometer=1000)
		self.make_log(vehicle, 1200)
		cancelled = self.make_log(vehicle, 1800)
		cancelled.cancel()

		readings = get_odometer_readings(vehicle.name)
		self.assertEqual([r["odometer"] for r in readings], [1200])
		self.assertEqual(get_last_odometer(vehicle.name), 1200)

	def test_readings_exclude_drafts(self):
		vehicle = self.make_vehicle(last_odometer=1000)
		self.make_log(vehicle, 1200)
		self.make_log(vehicle, 9999, submit=False)
		self.assertEqual(get_last_odometer(vehicle.name), 1200)

	def test_no_separate_odometer_doctype(self):
		for name in ("Vehicle Odometer Reading", "Odometer Reading", "Fleet Odometer Log"):
			self.assertFalse(frappe.db.exists("DocType", name), f"{name} should not exist")

	# --- dimensions -----------------------------------------------------------
	def test_dimensions_inherited_from_vehicle(self):
		vehicle = self.make_vehicle(last_odometer=1000, site="Jamjee Farm")
		log = self.make_log(vehicle, 1100)
		self.assertEqual(log.site, "Jamjee Farm")

	def test_explicit_dimensions_are_not_overwritten(self):
		vehicle = self.make_vehicle(last_odometer=1000, site="Jamjee Farm")
		log = self.make_log(vehicle, 1100, site="Gedu")
		self.assertEqual(log.site, "Gedu")

	# --- standard behaviour preserved ----------------------------------------
	def test_expense_claim_creation_still_works(self):
		from hrms.hr.doctype.vehicle_log.vehicle_log import make_expense_claim

		vehicle = self.make_vehicle(last_odometer=1000)
		log = self.make_log(vehicle, 1300, fuel_qty=10, price=100)
		claim = make_expense_claim(log.name)
		self.assertEqual(claim.get("vehicle_log"), log.name)

	def test_service_child_table_still_works(self):
		service_item = "_Test GDL Service"
		if not frappe.db.exists("Vehicle Service Item", service_item):
			frappe.get_doc(
				{"doctype": "Vehicle Service Item", "service_item": service_item}
			).insert()

		vehicle = self.make_vehicle(last_odometer=1000)
		log = frappe.get_doc({
			"doctype": "Vehicle Log", "license_plate": vehicle.name,
			"employee": self.employee, "date": nowdate(), "odometer": 1400,
			"usage_type": "Official", "place_to_travel": "Local",
		})
		log.append("service_detail", {
			"service_item": service_item, "type": "Change",
			"frequency": "Mileage", "expense_amount": 1500,
		})
		log.insert()
		log.submit()
		self.assertEqual(len(log.service_detail), 1)

	# --- permissions ----------------------------------------------------------
	def test_fleet_manager_retains_standard_permission(self):
		perms = {p.role for p in frappe.get_meta("Vehicle Log").permissions}
		self.assertIn("Fleet Manager", perms)
