# Copyright (c) 2026, GDL and contributors
"""Fleet Mgmt.docx 4.1 and 4.3 - Vehicle Master fields and Daily KM recording."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, cint, nowdate

from gdl_fleet_extension.tests.test_driver_assignment import make_driver
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle


def get_employee():
	return frappe.db.get_value("Employee", {}, "name")


class TestVehicleMasterFields(IntegrationTestCase):
	"""Section 4.1."""

	def test_capacity_fields_exist(self):
		meta = frappe.get_meta("Vehicle")
		self.assertTrue(meta.get_field("capacity"))
		self.assertEqual(meta.get_field("capacity_uom").options, "UOM")

	def test_capacity_recorded(self):
		vehicle = new_vehicle(capacity=5, capacity_uom="Nos")
		vehicle.insert()
		self.assertEqual(cint(vehicle.capacity), 5)

	def test_vehicle_status_matches_the_document(self):
		options = frappe.get_meta("Vehicle").get_field("vehicle_status").options.split("\n")
		self.assertEqual(options, ["Active", "Under Maintenance", "Unavailable", "Disposed"])

	def test_retired_status_values_are_gone(self):
		options = frappe.get_meta("Vehicle").get_field("vehicle_status").options
		for retired in ("Reserved", "In Use", "Sold / Disposed"):
			self.assertNotIn(retired, options.split("\n"))

	def test_existing_vehicles_were_migrated(self):
		stale = frappe.get_all(
			"Vehicle",
			filters={"vehicle_status": ("in", ["Available", "Reserved", "In Use",
			                                   "Sold / Disposed"])},
			pluck="name",
		)
		self.assertEqual(stale, [], f"vehicles left on a retired status: {stale}")

	def test_document_field_set(self):
		meta = frappe.get_meta("Vehicle")
		for fieldname in ("license_plate", "make", "model", "vehicle_type", "capacity",
		                  "engine_no", "chassis_no", "fuel_type", "acquisition_date",
		                  "last_odometer", "vehicle_status"):
			self.assertTrue(meta.get_field(fieldname), f"missing {fieldname}")


class TestDailyKM(IntegrationTestCase):
	"""Section 4.3."""

	def setUp(self):
		self.employee = get_employee()
		if not self.employee:
			self.skipTest("no Employee on this site")
		self.vehicle = new_vehicle(last_odometer=10000)
		self.vehicle.insert()

	def log(self, closing, date=None, submit=True, **kwargs):
		values = {
			"doctype": "Vehicle Log", "license_plate": self.vehicle.name,
			"employee": self.employee, "date": date or nowdate(),
			"odometer": closing, "usage_type": "Official",
			"place_to_travel": "Gedu",
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert()
		if submit:
			doc.submit()
		return doc

	# --- fields ---------------------------------------------------------------
	def test_document_field_set(self):
		meta = frappe.get_meta("Vehicle Log")
		for fieldname in ("date", "license_plate", "driver", "start_odometer",
		                  "odometer", "distance_travelled", "movement_order",
		                  "place_to_travel", "gdl_remarks"):
			self.assertTrue(meta.get_field(fieldname), f"missing {fieldname}")

	def test_opening_and_closing_labels(self):
		meta = frappe.get_meta("Vehicle Log")
		self.assertEqual(meta.get_field("start_odometer").label, "Opening Odometer")
		self.assertEqual(meta.get_field("odometer").label, "Closing Odometer")

	def test_place_to_travel_is_mandatory(self):
		"""The document marks it mandatory."""
		self.assertTrue(frappe.get_meta("Vehicle Log").get_field("place_to_travel").reqd)

	def test_movement_order_link_replaced_the_booking_link(self):
		meta = frappe.get_meta("Vehicle Log")
		self.assertEqual(meta.get_field("movement_order").options, "Movement Order")
		self.assertIsNone(meta.get_field("booking"))

	# --- calculation and validation -------------------------------------------
	def test_distance_is_closing_minus_opening(self):
		doc = self.log(10450)
		self.assertEqual(cint(doc.start_odometer), 10000)
		self.assertEqual(cint(doc.distance_travelled), 450)

	def test_opening_defaults_to_the_previous_closing(self):
		self.log(10400)
		second = self.log(10750, date=add_days(nowdate(), 1))
		self.assertEqual(cint(second.start_odometer), 10400)

	def test_closing_below_opening_rejected(self):
		doc = frappe.get_doc({
			"doctype": "Vehicle Log", "license_plate": self.vehicle.name,
			"employee": self.employee, "date": nowdate(), "usage_type": "Official",
			"place_to_travel": "Gedu", "start_odometer": 12000, "odometer": 11500,
		})
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_negative_distance_is_impossible(self):
		doc = self.log(10300)
		self.assertGreaterEqual(cint(doc.distance_travelled), 0)

	def test_one_primary_record_per_vehicle_per_day(self):
		self.log(10400)
		duplicate = frappe.get_doc({
			"doctype": "Vehicle Log", "license_plate": self.vehicle.name,
			"employee": self.employee, "date": nowdate(), "odometer": 10600,
			"usage_type": "Official", "place_to_travel": "Jamjee Farm",
		})
		self.assertRaises(frappe.ValidationError, duplicate.insert)

	def test_second_trip_allowed_against_its_own_movement_order(self):
		driver = make_driver("DK", "DL-DK-777")
		order = frappe.get_doc({
			"doctype": "Movement Order", "vehicle": self.vehicle.name, "driver": driver,
			"departure_datetime": nowdate() + " 08:00:00",
			"expected_return": nowdate() + " 12:00:00",
			"purpose": "Second authorised trip", "destination": "Gedu",
		})
		order.insert()

		self.log(10400)
		second = self.log(10600, movement_order=order.name)
		self.assertEqual(second.movement_order, order.name)

	def test_vehicle_odometer_updated_from_the_latest_reading(self):
		self.log(10900)
		self.assertEqual(
			cint(frappe.db.get_value("Vehicle", self.vehicle.name, "last_odometer")), 10900
		)

	def test_abnormal_mileage_warns_but_does_not_block(self):
		threshold = cint(
			frappe.db.get_single_value("GDL Fleet Settings", "abnormal_daily_km")
		)
		self.assertTrue(threshold, "abnormal_daily_km must be configured")

		doc = self.log(10000 + threshold + 250)
		self.assertEqual(doc.docstatus, 1, "an abnormal reading must warn, not block")
		self.assertGreater(cint(doc.distance_travelled), threshold)

	def test_abnormal_threshold_is_configuration(self):
		self.assertTrue(
			frappe.get_meta("GDL Fleet Settings").get_field("abnormal_daily_km")
		)

	# --- driver from the active assignment -------------------------------------
	def test_driver_fetched_from_the_active_assignment(self):
		driver = make_driver("Daily", "DL-DAILY-800")
		assignment = frappe.get_doc({
			"doctype": "Driver Assignment", "vehicle": self.vehicle.name,
			"driver": driver, "assignment_type": "Primary",
			"from_date": add_days(nowdate(), -10),
		})
		assignment.insert()
		assignment.submit()

		doc = self.log(10350)
		self.assertEqual(doc.driver, driver)

	def test_driver_taken_from_the_movement_order_when_present(self):
		primary = make_driver("Primary2", "DL-P2-810")
		relief = make_driver("Relief2", "DL-R2-811")
		frappe.get_doc({
			"doctype": "Driver Assignment", "vehicle": self.vehicle.name,
			"driver": primary, "assignment_type": "Primary",
			"from_date": add_days(nowdate(), -10),
		}).insert().submit()

		order = frappe.get_doc({
			"doctype": "Movement Order", "vehicle": self.vehicle.name, "driver": relief,
			"departure_datetime": nowdate() + " 08:00:00",
			"expected_return": nowdate() + " 12:00:00",
			"purpose": "Relief run", "destination": "Gedu",
		})
		order.insert()

		doc = self.log(10500, movement_order=order.name)
		self.assertEqual(doc.driver, relief)

	# --- no second ledger ------------------------------------------------------
	def test_no_separate_odometer_ledger(self):
		for name in ("Vehicle Odometer Reading", "Daily KM Log", "Odometer Reading"):
			self.assertFalse(frappe.db.exists("DocType", name))


class TestServiceRecord(IntegrationTestCase):
	"""Section 4.4."""

	def test_twelve_maintenance_items_configured(self):
		settings = frappe.get_single("GDL Fleet Settings")
		configured = {row.service_item for row in settings.maintenance_rules}
		for item in ("Engine Oil", "Brake Fluid", "Engine Oil Filter", "Fuel Filter",
		             "Air Filter", "Brake Pads", "Coolant", "Gear Oil",
		             "Tyre Replacement / Rotation", "Battery Replacement",
		             "General Inspection", "Other Repair or Maintenance"):
			self.assertIn(item, configured, f"{item} is named in section 4.4")

	def test_multi_item_service_table_exists(self):
		meta = frappe.get_meta("Asset Maintenance Log")
		field = meta.get_field("service_items")
		self.assertTrue(field, "a service visit must take several maintenance items")
		self.assertEqual(field.options, "Fleet Service Item")

	def test_service_item_row_fields(self):
		meta = frappe.get_meta("Fleet Service Item")
		for fieldname in ("service_item", "qty", "part_brand", "cost",
		                  "invoice_reference", "remarks"):
			self.assertTrue(meta.get_field(fieldname), f"missing {fieldname}")

	def test_intervals_remain_configuration(self):
		settings = frappe.get_single("GDL Fleet Settings")
		oil = next(r for r in settings.maintenance_rules if r.service_item == "Engine Oil")
		self.assertEqual(cint(oil.interval_km), 7500)
		self.assertEqual(cint(oil.interval_months), 6)
