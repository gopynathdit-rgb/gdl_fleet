# Copyright (c) 2026, GDL and contributors
"""Raising the Movement Order from the request it belongs to.

make_movement_order() has always been able to build the order from an accepted
request, and nothing on the request form ever called it: the MTO had to leave
the page, open a blank Movement Order and type the request number back in.

These tests cover the server side of the button - that it carries the trip
across, that it refuses a request that is not accepted, and that it cannot be
pressed twice.
"""

import frappe
from frappe.tests import IntegrationTestCase

from gdl_fleet_extension.gdl_fleet.doctype.movement_order.movement_order import (
	USABLE_REQUEST_STATUSES,
	make_movement_order,
)
from frappe.model.workflow import apply_workflow

from gdl_fleet_extension.tests.test_movement_order_request import new_booking
from gdl_fleet_extension.tests.test_vehicle_extension import TEST_TYPE, new_vehicle


class TestTheOrderIsBuiltFromTheRequest(IntegrationTestCase):
	def accepted_request(self):
		"""Taken to Accepted by its own workflow, not by db_set.

		test_movement_order_request carries the scar: a fixture that wrote the
		status directly produced a state the application could never reach, and
		every test built on it passed against a fiction.
		"""
		request = new_booking()
		request.insert()
		apply_workflow(request, "Submit for Review")
		apply_workflow(request, "Accept")
		request.reload()
		self.assertEqual(request.status, "Accepted")
		return request

	def request_at(self, state_action=None):
		request = new_booking()
		request.insert()
		if state_action:
			apply_workflow(request, state_action)
			request.reload()
		return request

	def test_an_accepted_request_yields_a_draft_order(self):
		request = self.accepted_request()
		order = make_movement_order(request.name)
		self.assertEqual(order.get("doctype"), "Movement Order")
		self.assertEqual(order.get("docstatus"), 0)
		self.assertEqual(order.get("movement_order_request"), request.name)

	def test_it_comes_back_unsaved_so_the_mto_can_check_it(self):
		"""The button opens a draft for review, it does not file an order."""
		request = self.accepted_request()
		order = make_movement_order(request.name)
		self.assertTrue(order.get("__islocal"),
		                "the order was saved before anyone looked at it")
		self.assertFalse(frappe.db.exists(
			"Movement Order", {"movement_order_request": request.name}))

	def test_the_trip_is_carried_across(self):
		"""The order's own field names, which are not the request's: a request
		has a required window, an order has a departure and a return."""
		request = self.accepted_request()
		order = make_movement_order(request.name)
		for on_the_order, on_the_request in (
			("purpose", "purpose"),
			("departure_datetime", "from_datetime"),
			("expected_return", "to_datetime"),
			("vehicle_type", "vehicle_type"),
			("from_location", "pickup_location"),
			("destination", "destination"),
			("passenger_count", "passenger_count"),
		):
			self.assertEqual(order.get(on_the_order), request.get(on_the_request),
			                 f"{on_the_order} was not carried from {on_the_request}")

	def test_the_vehicle_is_left_for_the_mto_to_allocate(self):
		"""An unallocated request yields an order with no vehicle, and Movement
		Order will not save without one - so the MTO must choose before filing.
		That is the control, not a gap."""
		request = self.accepted_request()
		order = make_movement_order(request.name)
		self.assertIsNone(order.get("vehicle"))
		self.assertIsNone(order.get("driver"))

		doc = frappe.get_doc(order)
		doc.flags.ignore_permissions = True
		self.assertRaises(frappe.MandatoryError, doc.insert)

	def test_a_draft_request_is_refused(self):
		"""The button is hidden for these, but the form is not the only caller."""
		request = self.request_at()
		self.assertRaises(frappe.ValidationError, make_movement_order, request.name)

	def test_a_request_still_under_review_is_refused(self):
		request = self.request_at("Submit for Review")
		self.assertEqual(request.status, "Pending Review")
		self.assertRaises(frappe.ValidationError, make_movement_order, request.name)

	def test_a_rejected_request_is_refused(self):
		request = self.request_at("Submit for Review")
		apply_workflow(request, "Reject")
		request.reload()
		self.assertEqual(request.status, "Rejected")
		self.assertRaises(frappe.ValidationError, make_movement_order, request.name)

	def test_accepted_is_the_only_usable_status(self):
		self.assertEqual(tuple(USABLE_REQUEST_STATUSES), ("Accepted",))

	def test_the_same_request_cannot_be_ordered_twice(self):
		"""Why the form offers the existing order instead of a second Create."""
		request = self.accepted_request()
		order = frappe.get_doc(make_movement_order(request.name))
		order.vehicle, order.driver = self.a_vehicle_and_driver()
		order.flags.ignore_permissions = True
		order.insert()

		self.assertRaises(frappe.ValidationError, make_movement_order, request.name)

	@staticmethod
	def a_vehicle_and_driver():
		"""A Movement Order cannot be filed without both."""
		vehicle = new_vehicle(vehicle_type=TEST_TYPE)
		vehicle.insert()
		driver = frappe.get_doc({
			"doctype": "Driver", "full_name": "Test MTO Driver",
			"status": "Active", "license_number": frappe.generate_hash(length=8),
		})
		driver.flags.ignore_permissions = True
		driver.insert()
		return vehicle.name, driver.name

	def test_a_cancelled_request_is_refused(self):
		request = self.accepted_request()
		apply_workflow(request, "Cancel")
		request.reload()
		self.assertRaises(frappe.ValidationError, make_movement_order, request.name)
