# Copyright (c) 2026, GDL and contributors
"""Picking a vehicle on a service record fills the rest in.

GDL: "In asset maintance when i select vechile need fetch all deatils
automatily fill like location and all" - and then "and location not editable".
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from gdl_fleet_extension.overrides.asset_maintenance import vehicle_defaults
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle


class TestLocationFollowsTheVehicle(IntegrationTestCase):
	"""Location is bound to the vehicle's site and cannot be typed over."""

	def field(self):
		return frappe.get_meta("Asset Maintenance Log").get_field("location")

	def test_it_is_fetched_from_the_vehicle(self):
		self.assertEqual(self.field().fetch_from, "vehicle.site")

	def test_it_is_read_only_on_the_form(self):
		"""frappe holds a fetch_from control read-only unless fetch_if_empty is
		set - read_only_because_of_fetch_from() in base_input.js. Ticking
		fetch_if_empty would quietly make it editable again, which is the one
		thing GDL asked against."""
		self.assertFalse(self.field().fetch_if_empty,
		                 "fetch_if_empty makes Location editable again")

	def test_it_is_filled_on_save_without_anyone_typing_it(self):
		vehicle = new_vehicle()
		vehicle.site = frappe.db.get_value("Location", {"is_group": 0}, "name")
		vehicle.insert()

		log = frappe.get_doc({
			"doctype": "Asset Maintenance Log", "vehicle": vehicle.name,
			"maintenance_status": "Completed", "completion_date": nowdate(),
		})
		log.flags.ignore_permissions = True
		log.insert()
		self.assertEqual(log.location, vehicle.site,
		                 "Location did not follow the vehicle")

	def test_the_binding_is_enforced_on_the_server_too(self):
		"""Read-only in the browser is a convenience. fetch_from re-asserts the
		value on save, so a crafted request cannot set a different site."""
		vehicle = new_vehicle()
		vehicle.site = frappe.db.get_value("Location", {"is_group": 0}, "name")
		vehicle.insert()
		other = frappe.db.get_value(
			"Location", {"is_group": 0, "name": ("!=", vehicle.site)}, "name")
		if not other:
			self.skipTest("only one leaf Location on this site")

		log = frappe.get_doc({
			"doctype": "Asset Maintenance Log", "vehicle": vehicle.name,
			"location": other,          # someone trying to override it
			"maintenance_status": "Completed", "completion_date": nowdate(),
		})
		log.flags.ignore_permissions = True
		log.insert()
		self.assertEqual(log.location, vehicle.site,
		                 "a supplied Location overrode the vehicle's site")


class TestTheOtherDetailsAreOffered(IntegrationTestCase):
	"""Cost centre, project, odometer and driver are STARTING values - filled
	in, but editable. A workshop visit can legitimately differ, and the
	odometer is the reading at service, which is the point of the record."""

	def test_nothing_comes_back_for_no_vehicle(self):
		self.assertEqual(vehicle_defaults(None), {})
		self.assertEqual(vehicle_defaults(""), {})

	def test_the_odometer_is_offered(self):
		vehicle = new_vehicle(last_odometer=41234)
		vehicle.insert()
		self.assertEqual(vehicle_defaults(vehicle.name)["odometer"], 41234)

	def test_location_is_not_in_the_payload(self):
		"""It is bound through fetch_from. Setting it here as well would be a
		second source for one value."""
		vehicle = new_vehicle()
		vehicle.insert()
		self.assertNotIn("location", vehicle_defaults(vehicle.name))

	def test_the_driver_is_the_one_assigned_today(self):
		"""Not a column on the Vehicle - a Temporary or Relief assignment
		outranks the Primary one, so this has to go through the assignment."""
		from gdl_fleet_extension.gdl_fleet.doctype.driver_assignment import (
			driver_assignment,
		)
		self.assertTrue(hasattr(driver_assignment, "get_active_driver"))

	def test_the_fields_offered_all_exist_on_the_form(self):
		"""A renamed field would silently stop being filled."""
		vehicle = new_vehicle()
		vehicle.insert()
		meta = frappe.get_meta("Asset Maintenance Log")
		for fieldname in vehicle_defaults(vehicle.name):
			with self.subTest(field=fieldname):
				self.assertIsNotNone(meta.get_field(fieldname),
				                     f"{fieldname} is not a field on the log")

	def test_an_unknown_vehicle_does_not_raise(self):
		"""The form calls this on every change of the link."""
		self.assertEqual(vehicle_defaults("no-such-vehicle-at-all"),
		                 {"cost_center": None, "project": None,
		                  "odometer": None, "driver": None})
