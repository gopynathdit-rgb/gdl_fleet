# Copyright (c) 2026, GDL and contributors
"""
The statuses that occupy a vehicle must be statuses that can occur.

This exists because of a defect that survived a 500-test suite. Movement Order
Request once used a multi-level chain whose states included Approved, Assigned
and In Use. Fleet Mgmt.docx reduced it to Draft / Pending Review / Accepted /
Rejected, and patches/v1_1/map_movement_request_status.py folded the retired
states into Accepted - but OCCUPYING_STATUSES went on naming the retired ones.

Two queries filter on it: the double-booking guard, and get_available_vehicles.
Both became dead code. No request could hold any of those statuses, so nothing
was ever found to conflict: two requests could be accepted for the same vehicle
over the same window, and Check Availability offered vehicles already committed.

The suite said otherwise only because its fixture wrote the impossible status
with db_set, which skips validation. A test whose fixture cannot occur in the
application proves nothing about the application.

So this compares each constant against the DocType's own Select options. A
rename cannot silently empty these queries again.
"""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase

from gdl_fleet_extension.gdl_fleet.doctype.movement_order.movement_order import (
	OCCUPYING_STATUSES as ORDER_STATUSES,
)
from gdl_fleet_extension.gdl_fleet.doctype.movement_order_request.movement_order_request import (
	OCCUPYING_STATUSES as REQUEST_STATUSES,
	UNASSIGNABLE_VEHICLE_STATUSES,
)


def allowed(doctype, fieldname):
	field = frappe.get_meta(doctype).get_field(fieldname)
	return {o.strip() for o in (field.options or "").split("\n") if o.strip()}


class TestOccupyingStatusesAreReal(IntegrationTestCase):
	def test_request_occupying_statuses_exist(self):
		options = allowed("Movement Order Request", "status")
		unknown = set(REQUEST_STATUSES) - options
		self.assertEqual(
			unknown, set(),
			f"Movement Order Request cannot hold {unknown}, so every query "
			f"filtering on OCCUPYING_STATUSES matches nothing. Allowed: {sorted(options)}",
		)

	def test_order_occupying_statuses_exist(self):
		options = allowed("Movement Order", "status")
		unknown = set(ORDER_STATUSES) - options
		self.assertEqual(
			unknown, set(),
			f"Movement Order cannot hold {unknown}. Allowed: {sorted(options)}",
		)

	def test_unassignable_vehicle_statuses_exist(self):
		options = allowed("Vehicle", "vehicle_status")
		unknown = set(UNASSIGNABLE_VEHICLE_STATUSES) - options
		self.assertEqual(unknown, set(), f"Vehicle cannot hold {unknown}. Allowed: {sorted(options)}")

	def test_none_of_them_is_empty(self):
		"""An empty tuple would disable the queries just as completely."""
		for name, values in (("Movement Order Request", REQUEST_STATUSES),
		                     ("Movement Order", ORDER_STATUSES),
		                     ("Vehicle", UNASSIGNABLE_VEHICLE_STATUSES)):
			with self.subTest(doctype=name):
				self.assertTrue(values, f"{name}: the occupancy filter is empty")

	def test_the_retired_statuses_are_really_gone(self):
		"""Names the exact values that caused the defect."""
		options = allowed("Movement Order Request", "status")
		for retired in ("Approved", "Assigned", "In Use"):
			self.assertNotIn(
				retired, options,
				f"{retired} is selectable again - revisit OCCUPYING_STATUSES",
			)


class TestWorkflowStatesCoverOccupancy(IntegrationTestCase):
	"""The workflow has to be able to reach the occupying state."""

	def test_the_request_workflow_reaches_an_occupying_state(self):
		states = {s.state for s in frappe.get_doc("Workflow", "GDL Movement Order Request Review").states}
		self.assertTrue(
			states & set(REQUEST_STATUSES),
			f"no transition reaches {REQUEST_STATUSES}, so a vehicle can never be "
			f"marked occupied. Workflow states: {sorted(states)}",
		)

	def test_the_order_workflow_reaches_an_occupying_state(self):
		states = {s.state for s in frappe.get_doc("Workflow", "GDL Movement Order Approval").states}
		self.assertTrue(states & set(ORDER_STATUSES), f"workflow states: {sorted(states)}")


class TestAvailabilitySeesMovementOrders(IntegrationTestCase):
	"""A vehicle on an approved Movement Order is not available.

	get_available_vehicles once read only Movement Order Request. In the usual
	flow that is enough, because the accepted request holds the same window as
	the order raised from it. Two cases escaped it: an order created without a
	request, and an order whose window was widened after approval. In both the
	helper offered a vehicle that the Movement Order conflict guard then
	refused - advice contradicting the rule it is meant to anticipate.
	"""

	def setUp(self):
		from gdl_fleet_extension.tests.test_driver_assignment import make_driver
		from gdl_fleet_extension.tests.test_vehicle_extension import make_vehicle_type
		make_vehicle_type()
		self.driver = make_driver("OCC", "DL-OCC-901")

	def book(self, vehicle, driver, days_ahead, hours=4):
		from frappe.utils import add_days, add_to_date, nowdate
		departure = add_to_date(add_days(nowdate(), days_ahead), hours=9)
		order = frappe.get_doc({
			"doctype": "Movement Order", "vehicle": vehicle, "driver": driver,
			"departure_datetime": departure,
			"expected_return": add_to_date(departure, hours=hours),
			"destination": "Jamjee Farm", "purpose": "Occupancy test",
		})
		order.flags.ignore_permissions = True
		order.insert()
		for action in ("Submit for Approval", "Approve"):
			apply_workflow(order, action)
			order.reload()
		return order

	def test_an_order_with_no_request_withholds_the_vehicle(self):
		from frappe.utils import add_days, add_to_date, nowdate
		from gdl_fleet_extension.gdl_fleet.doctype.movement_order_request.movement_order_request import (
			get_available_vehicles,
		)
		from gdl_fleet_extension.tests.test_vehicle_extension import TEST_TYPE, new_vehicle

		busy = new_vehicle(); busy.insert()
		free = new_vehicle(); free.insert()
		order = self.book(busy.name, self.driver, 9)
		self.assertEqual(order.docstatus, 1)

		start = add_to_date(add_days(nowdate(), 9), hours=9)
		offered = {v["name"] for v in get_available_vehicles(
			start, add_to_date(start, hours=4), vehicle_type=TEST_TYPE)}
		self.assertIn(free.name, offered)
		self.assertNotIn(busy.name, offered, "a vehicle on an approved order is not available")

	def test_a_draft_order_does_not_withhold_the_vehicle(self):
		"""Consistent with bookings: only an approved commitment occupies."""
		from frappe.utils import add_days, add_to_date, nowdate
		from gdl_fleet_extension.gdl_fleet.doctype.movement_order_request.movement_order_request import (
			get_available_vehicles,
		)
		from gdl_fleet_extension.tests.test_vehicle_extension import TEST_TYPE, new_vehicle

		vehicle = new_vehicle(); vehicle.insert()
		departure = add_to_date(add_days(nowdate(), 11), hours=9)
		draft = frappe.get_doc({
			"doctype": "Movement Order", "vehicle": vehicle.name, "driver": self.driver,
			"departure_datetime": departure, "expected_return": add_to_date(departure, hours=4),
			"destination": "Jamjee Farm", "purpose": "Draft occupancy test",
		})
		draft.flags.ignore_permissions = True
		draft.insert()
		self.assertEqual(draft.docstatus, 0)

		offered = {v["name"] for v in get_available_vehicles(
			departure, add_to_date(departure, hours=4), vehicle_type=TEST_TYPE)}
		self.assertIn(vehicle.name, offered, "a draft order must not hold a vehicle")
