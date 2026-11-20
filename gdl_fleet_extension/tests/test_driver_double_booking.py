# Copyright (c) 2026, GDL and contributors
"""A driver cannot be out on two movement orders at once.

GDL: "Movement Order, if the Driver is Assigned to another vehicle at the same
time, it shouldnt show in the Driver selection."

Two halves, and both matter. The dropdown leaves a committed driver out, so
nobody has to spot the clash. The server refuses one anyway, because a driver
can arrive from the request, from a draft whose times have since moved, or
from the API - a filtered list is a convenience, not the rule.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, nowdate

from gdl_fleet_extension.gdl_fleet.doctype.movement_order.movement_order import (
	driver_query,
)
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle


def a_driver(suffix):
	name = f"GDL Test Driver {suffix}"
	existing = frappe.db.get_value("Driver", {"full_name": name}, "name")
	if existing:
		return existing
	employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
	doc = frappe.get_doc({
		"doctype": "Driver", "full_name": name,
		"license_number": f"LIC-{suffix}",
		"employee": employee,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


class TestADriverIsNotDoubleBooked(IntegrationTestCase):
	def setUp(self):
		self.driver = a_driver(frappe.generate_hash(length=5))
		self.start = add_to_date(nowdate(), days=3, as_string=False)
		self.vehicle_a = new_vehicle()
		self.vehicle_a.insert()
		self.vehicle_b = new_vehicle()
		self.vehicle_b.insert()

	def order(self, vehicle, start_offset=0, hours=4, driver=None, status="Approved"):
		departure = add_to_date(self.start, hours=start_offset)
		doc = frappe.get_doc({
			"doctype": "Movement Order",
			"vehicle": vehicle.name,
			"driver": driver or self.driver,
			"departure_datetime": departure,
			"expected_return": add_to_date(departure, hours=hours),
			"purpose": "test",
			"destination": "Paro",
			"status": status,
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc

	# --- the rule -------------------------------------------------------
	def test_the_same_driver_cannot_overlap_on_another_vehicle(self):
		self.order(self.vehicle_a)
		with self.assertRaises(frappe.ValidationError) as cm:
			self.order(self.vehicle_b, start_offset=1)
		self.assertIn("already out", str(cm.exception))

	def test_the_refusal_names_the_order_and_the_other_vehicle(self):
		first = self.order(self.vehicle_a)
		with self.assertRaises(frappe.ValidationError) as cm:
			self.order(self.vehicle_b, start_offset=1)
		message = str(cm.exception)
		self.assertIn(first.name, message)
		self.assertIn(self.vehicle_a.name, message)

	def test_back_to_back_trips_are_allowed(self):
		"""Ending exactly when the next begins is not an overlap."""
		self.order(self.vehicle_a, hours=4)
		self.order(self.vehicle_b, start_offset=4)

	def test_a_different_driver_is_unaffected(self):
		self.order(self.vehicle_a)
		self.order(self.vehicle_b, start_offset=1,
		           driver=a_driver(frappe.generate_hash(length=5)))

	def test_a_cancelled_order_frees_the_driver(self):
		first = self.order(self.vehicle_a)
		first.status = "Cancelled"
		first.flags.ignore_permissions = True
		first.save()
		self.order(self.vehicle_b, start_offset=1)

	def test_editing_an_order_does_not_clash_with_itself(self):
		order = self.order(self.vehicle_a)
		order.purpose = "changed"
		order.flags.ignore_permissions = True
		order.save()

	# --- the dropdown ---------------------------------------------------
	def ask(self, exclude=""):
		return [row[0] for row in driver_query(
			"Driver", "", "name", 0, 50,
			{"departure_datetime": self.start,
			 "expected_return": add_to_date(self.start, hours=4),
			 "name": exclude})]

	def test_a_committed_driver_is_left_out_of_the_list(self):
		self.assertIn(self.driver, self.ask())
		self.order(self.vehicle_a)
		self.assertNotIn(self.driver, self.ask(),
		                 "a driver already out is still being offered")

	def test_the_order_being_edited_does_not_hide_its_own_driver(self):
		order = self.order(self.vehicle_a)
		self.assertIn(self.driver, self.ask(exclude=order.name))

	def test_with_no_window_every_driver_is_offered(self):
		"""Nothing to judge against yet."""
		self.order(self.vehicle_a)
		offered = [row[0] for row in driver_query(
			"Driver", "", "name", 0, 50, {})]
		self.assertIn(self.driver, offered)
