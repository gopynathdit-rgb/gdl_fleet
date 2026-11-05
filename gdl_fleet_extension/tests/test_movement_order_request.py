# Copyright (c) 2026, GDL and contributors
"""Fleet Mgmt.docx section 4.7 - Movement Order Request, Accept / Reject."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, get_datetime, nowdate

from gdl_fleet_extension.gdl_fleet.doctype.movement_order_request.movement_order_request import (
	get_available_vehicles,
)
from gdl_fleet_extension.tests.test_vehicle_extension import TEST_TYPE, make_vehicle_type, new_vehicle

WORKFLOW = "GDL Movement Order Request Review"


def new_booking(**kwargs):
	values = {
		"doctype": "Movement Order Request",
		"requester": "Administrator",
		"purpose": "Site inspection at Jamjee Farm",
		"usage_type": "Official",
		"priority": "Routine",
		"passenger_count": 2,
		"vehicle_type": make_vehicle_type(),
		"required_date": add_days(nowdate(), 3),
		"required_from_time": "08:00:00",
		"required_to_time": "17:00:00",
		"pickup_location": "Head Office",
		"destination": "Jamjee Farm",
	}
	values.update(kwargs)
	return frappe.get_doc(values)


def approved_booking(vehicle, **kwargs):
	"""A booking that occupies the vehicle, taken there by its own workflow.

	This used to call db_set("status", "Approved"). "Approved" is not one of
	this DocType's statuses - it was retired when the request was reduced to
	Draft / Pending Review / Accepted / Rejected - and db_set writes without
	validating, so the fixture produced a state the application could never
	reach. Every occupancy test then passed against it while the real queries,
	which filter on the statuses a request can actually hold, matched nothing.

	Driving the real transitions costs a little more and tests what ships.
	"""
	booking = new_booking(vehicle=vehicle, **kwargs)
	booking.insert()
	apply_workflow(booking, "Submit for Review")
	apply_workflow(booking, "Accept")
	booking.reload()
	return booking


class TestMovementOrderRequest(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_vehicle_type()

	# --- creation -----------------------------------------------------------
	def test_create_booking(self):
		booking = new_booking()
		booking.insert()
		self.assertTrue(
			booking.name.startswith("MOR-"),
			f"new requests use the MOR- series, got {booking.name}",
		)
		self.assertEqual(booking.status, "Draft")
		self.assertEqual(booking.docstatus, 0)

	def test_document_field_set(self):
		"""Every field section 4.7 lists must exist."""
		meta = frappe.get_meta("Movement Order Request")
		for fieldname in ("request_date", "requester", "department", "purpose",
		                  "from_location", "destination", "passenger_count",
		                  "vehicle_type", "vehicle", "approver_remarks"):
			self.assertTrue(meta.get_field(fieldname), f"missing {fieldname}")

	def test_references_standard_vehicle_doctype(self):
		meta = frappe.get_meta("Movement Order Request")
		self.assertEqual(meta.get_field("vehicle").options, "Vehicle")
		self.assertEqual(meta.get_field("driver").options, "Driver")
		self.assertEqual(meta.get_field("site").options, "Location")
		self.assertEqual(meta.get_field("employee").options, "Employee")
		self.assertEqual(meta.get_field("cost_center").options, "Cost Center")

	# --- schedule -----------------------------------------------------------
	def test_datetimes_and_duration_computed(self):
		booking = new_booking(required_from_time="08:00:00", required_to_time="17:30:00")
		booking.insert()
		self.assertTrue(booking.from_datetime)
		self.assertTrue(booking.to_datetime)
		self.assertEqual(flt(booking.duration_hours), 9.5)

	def test_multi_day_duration(self):
		booking = new_booking(
			required_date=add_days(nowdate(), 3),
			return_date=add_days(nowdate(), 4),
			required_from_time="08:00:00",
			required_to_time="08:00:00",
		)
		booking.insert()
		self.assertEqual(flt(booking.duration_hours), 24.0)

	def test_end_time_must_be_after_start(self):
		booking = new_booking(required_from_time="17:00:00", required_to_time="08:00:00")
		self.assertRaises(frappe.ValidationError, booking.insert)

	def test_past_date_rejected_on_new_booking(self):
		booking = new_booking(required_date=add_days(nowdate(), -2))
		self.assertRaises(frappe.ValidationError, booking.insert)

	def test_return_date_before_required_date_rejected(self):
		booking = new_booking(
			required_date=add_days(nowdate(), 5), return_date=add_days(nowdate(), 3)
		)
		self.assertRaises(frappe.ValidationError, booking.insert)

	# --- vehicle assignment -------------------------------------------------
	def test_assign_vehicle_and_driver(self):
		vehicle = new_vehicle()
		vehicle.insert()

		booking = new_booking(vehicle=vehicle.name)
		booking.insert()
		self.assertEqual(booking.vehicle, vehicle.name)
		self.assertTrue(booking.assigned_by)
		self.assertTrue(booking.assigned_on)

	def test_vehicle_type_must_match(self):
		other_type = "_Test GDL Bus"
		if not frappe.db.exists("Fleet Vehicle Type", other_type):
			frappe.get_doc(
				{"doctype": "Fleet Vehicle Type", "vehicle_type_name": other_type}
			).insert()

		vehicle = new_vehicle(vehicle_type=other_type)
		vehicle.insert()

		booking = new_booking(vehicle=vehicle.name, vehicle_type=TEST_TYPE)
		self.assertRaises(frappe.ValidationError, booking.insert)

	def test_unavailable_vehicle_cannot_be_assigned(self):
		vehicle = new_vehicle()
		vehicle.insert()
		vehicle.db_set("vehicle_status", "Under Maintenance")

		booking = new_booking(vehicle=vehicle.name)
		self.assertRaises(frappe.ValidationError, booking.insert)

	# --- overlap / conflict -------------------------------------------------
	def test_overlapping_booking_rejected(self):
		vehicle = new_vehicle()
		vehicle.insert()
		approved_booking(vehicle.name)

		clash = new_booking(vehicle=vehicle.name)  # identical window
		self.assertRaises(frappe.ValidationError, clash.insert)

	def test_partial_overlap_rejected(self):
		"""The classic case a naive query misses: the new booking starts mid-way."""
		vehicle = new_vehicle()
		vehicle.insert()
		approved_booking(vehicle.name, required_from_time="08:00:00", required_to_time="12:00:00")

		clash = new_booking(
			vehicle=vehicle.name, required_from_time="11:00:00", required_to_time="15:00:00"
		)
		self.assertRaises(frappe.ValidationError, clash.insert)

	def test_enclosing_overlap_rejected(self):
		vehicle = new_vehicle()
		vehicle.insert()
		approved_booking(vehicle.name, required_from_time="10:00:00", required_to_time="11:00:00")

		clash = new_booking(
			vehicle=vehicle.name, required_from_time="08:00:00", required_to_time="18:00:00"
		)
		self.assertRaises(frappe.ValidationError, clash.insert)

	def test_adjacent_booking_allowed(self):
		"""Back-to-back bookings must not be treated as a conflict."""
		vehicle = new_vehicle()
		vehicle.insert()
		approved_booking(vehicle.name, required_from_time="08:00:00", required_to_time="12:00:00")

		ok = new_booking(
			vehicle=vehicle.name, required_from_time="12:00:00", required_to_time="16:00:00"
		)
		ok.insert()
		self.assertTrue(ok.name)

	def test_different_day_allowed(self):
		vehicle = new_vehicle()
		vehicle.insert()
		approved_booking(vehicle.name, required_date=add_days(nowdate(), 3))

		ok = new_booking(vehicle=vehicle.name, required_date=add_days(nowdate(), 4))
		ok.insert()
		self.assertTrue(ok.name)

	def test_draft_booking_does_not_block(self):
		"""Only Approved/Assigned/In Use occupy a vehicle."""
		vehicle = new_vehicle()
		vehicle.insert()
		draft = new_booking(vehicle=vehicle.name)
		draft.insert()

		second = new_booking(vehicle=vehicle.name)
		second.insert()
		self.assertTrue(second.name)

	def test_cancelled_booking_frees_the_vehicle(self):
		vehicle = new_vehicle()
		vehicle.insert()
		booking = approved_booking(vehicle.name)
		booking.db_set("status", "Cancelled")

		reuse = new_booking(vehicle=vehicle.name)
		reuse.insert()
		self.assertTrue(reuse.name)

	def test_saving_an_occupying_booking_does_not_self_conflict(self):
		"""Rule 9 - the conflict query must exclude the record being saved.

		An accepted booking occupies its vehicle, so without the `name !=` term
		it would find itself and refuse every later edit. Reassignment is the
		case that matters: vehicle and driver stay editable after acceptance so
		a last-minute swap does not mean starting again.
		"""
		vehicle = new_vehicle()
		vehicle.insert()
		booking = approved_booking(vehicle.name)
		self.assertEqual(booking.status, "Accepted", "the fixture must actually occupy the vehicle")

		booking.assignment_remarks = "Driver swapped at the depot"
		booking.save()  # must not raise a conflict against itself

		booking.reload()
		booking.vehicle = vehicle.name  # re-assert the SAME vehicle
		booking.save()
		booking.reload()
		self.assertEqual(booking.vehicle, vehicle.name)

	def test_rescheduling_a_draft_does_not_self_conflict(self):
		"""The times are only editable before acceptance, so reschedule there."""
		vehicle = new_vehicle()
		vehicle.insert()
		booking = new_booking(vehicle=vehicle.name)
		booking.insert()

		booking.required_from_time = "09:00:00"
		booking.save()  # must not raise a conflict against itself
		booking.reload()
		# assert on the derived datetime rather than the raw Time field, which
		# frappe returns as a string before reload and a timedelta after
		self.assertEqual(get_datetime(booking.from_datetime).hour, 9)

	def test_times_are_fixed_once_accepted(self):
		"""Documents the boundary the test above relies on."""
		vehicle = new_vehicle()
		vehicle.insert()
		booking = approved_booking(vehicle.name)
		booking.required_from_time = "09:00:00"
		self.assertRaises(frappe.ValidationError, booking.save)

	# --- availability API ---------------------------------------------------
	def test_availability_excludes_booked_vehicle(self):
		free = new_vehicle()
		free.insert()
		busy = new_vehicle()
		busy.insert()
		booking = approved_booking(busy.name)

		available = get_available_vehicles(
			booking.from_datetime, booking.to_datetime, vehicle_type=TEST_TYPE
		)
		names = {v["name"] for v in available}
		self.assertIn(free.name, names)
		self.assertNotIn(busy.name, names)

	def test_availability_excludes_unavailable_vehicle(self):
		vehicle = new_vehicle()
		vehicle.insert()
		vehicle.db_set("vehicle_status", "Unavailable")

		booking = new_booking()
		booking.insert()
		available = get_available_vehicles(
			booking.from_datetime, booking.to_datetime, vehicle_type=TEST_TYPE
		)
		self.assertNotIn(vehicle.name, {v["name"] for v in available})

	# --- workflow -----------------------------------------------------------
	def test_workflow_is_active_and_role_driven(self):
		workflow = frappe.get_doc("Workflow", WORKFLOW)
		self.assertTrue(workflow.is_active)
		self.assertEqual(workflow.document_type, "Movement Order Request")
		self.assertEqual(workflow.workflow_state_field, "workflow_state")

		# every transition must name a Role, never a user
		for row in workflow.transitions:
			self.assertTrue(row.allowed)
			self.assertTrue(
				frappe.db.exists("Role", row.allowed), f"{row.allowed} is not a Role"
			)

	def test_workflow_chain_matches_the_document(self):
		"""Section 4.7: Draft -> Pending Review -> Accepted / Rejected.

		The earlier five-level chain (Validator / Reviewer / MTO-CEO / FAS) is not
		in Fleet Mgmt.docx; approval proper moved to the Movement Order (4.9).
		"""
		workflow = frappe.get_doc("Workflow", WORKFLOW)
		chain = {(t.state, t.action): (t.next_state, t.allowed) for t in workflow.transitions}

		self.assertEqual(
			chain[("Draft", "Submit for Review")], ("Pending Review", "Fleet User")
		)
		self.assertEqual(
			chain[("Pending Review", "Accept")], ("Accepted", "Fleet Administrator")
		)
		self.assertEqual(
			chain[("Pending Review", "Reject")], ("Rejected", "Fleet Administrator")
		)
		for retired in ("Submit for Validation", "Validate", "Review"):
			self.assertNotIn(
				retired, {t.action for t in workflow.transitions},
				f"{retired} is not part of the final scope",
			)

	def test_workflow_states_carry_correct_docstatus(self):
		workflow = frappe.get_doc("Workflow", WORKFLOW)
		docstatus = {s.state: int(s.doc_status) for s in workflow.states}
		self.assertEqual(docstatus["Draft"], 0)
		self.assertEqual(docstatus["Pending Review"], 0)
		self.assertEqual(docstatus["Accepted"], 1)
		self.assertEqual(docstatus["Rejected"], 0)
		self.assertEqual(docstatus["Cancelled"], 2)

	def test_workflow_updates_status_field(self):
		workflow = frappe.get_doc("Workflow", WORKFLOW)
		for state in workflow.states:
			self.assertEqual(state.update_field, "status")
			self.assertEqual(state.update_value, state.state)

	def test_vehicle_assignment_moved_to_the_movement_order(self):
		"""Section 4.8 allocates the vehicle and driver on the Movement Order."""
		workflow = frappe.get_doc("Workflow", WORKFLOW)
		self.assertNotIn(
			"Assign Vehicle", {t.action for t in workflow.transitions},
			"assignment belongs to the Movement Order, not the request",
		)

	def test_workflow_transition_applies(self):
		from frappe.model.workflow import apply_workflow

		booking = new_booking()
		booking.insert()
		apply_workflow(booking, "Submit for Review")
		booking.reload()
		self.assertEqual(booking.workflow_state, "Pending Review")
		self.assertEqual(booking.status, "Pending Review")

	def test_accept_and_reject(self):
		from frappe.model.workflow import apply_workflow

		accepted = new_booking()
		accepted.insert()
		apply_workflow(accepted, "Submit for Review")
		apply_workflow(accepted.reload(), "Accept")
		accepted.reload()
		self.assertEqual(accepted.status, "Accepted")
		self.assertEqual(accepted.docstatus, 1)

		rejected = new_booking()
		rejected.insert()
		apply_workflow(rejected, "Submit for Review")
		apply_workflow(rejected.reload(), "Reject")
		rejected.reload()
		self.assertEqual(rejected.status, "Rejected")

	def test_fleet_roles_have_document_permissions(self):
		meta = frappe.get_meta("Movement Order Request")
		roles = {p.role for p in meta.permissions if p.permlevel == 0}
		for role in (
			"Fleet Administrator",
			"Fleet User",
			"Fleet Validator",
			"Fleet Reviewer",
			"Fleet Approver",
			"Fleet Finance User",
		):
			self.assertIn(role, roles)

	# --- cancellation -------------------------------------------------------
	def test_cancellation_preserves_the_record(self):
		"""Rule 8 - cancelling keeps the document and its history."""
		vehicle = new_vehicle()
		vehicle.insert()
		booking = new_booking(vehicle=vehicle.name)
		booking.insert()
		booking.submit()
		booking.cancel()

		booking.reload()
		self.assertEqual(booking.docstatus, 2)
		self.assertEqual(booking.status, "Cancelled")
		self.assertTrue(frappe.db.exists("Movement Order Request", booking.name))


class TestPostApprovalAssignment(IntegrationTestCase):
	"""Assignment happens AFTER approval, so the fields must survive submission.

	Found by building sample data: walking the real workflow to Approved and then
	assigning a vehicle raised UpdateAfterSubmitError, which made the approved
	flow impossible to use as designed.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_vehicle_type()

	def test_allocation_fields_survive_submission(self):
		meta = frappe.get_meta("Movement Order Request")
		for fieldname in ("vehicle", "driver", "assignment_remarks", "status"):
			self.assertTrue(
				meta.get_field(fieldname).allow_on_submit,
				f"{fieldname} cannot be set after approval",
			)

	def test_vehicle_can_be_assigned_after_submission(self):
		vehicle = new_vehicle()
		vehicle.insert()

		booking = new_booking()
		booking.insert()
		booking.submit()

		booking.vehicle = vehicle.name
		booking.save()
		booking.reload()
		self.assertEqual(booking.vehicle, vehicle.name)
		self.assertEqual(booking.docstatus, 1)

	def test_conflict_check_still_runs_after_submission(self):
		"""Without before_update_after_submit this check would never fire."""
		vehicle = new_vehicle()
		vehicle.insert()
		approved_booking(vehicle.name)

		clash = new_booking()
		clash.insert()
		clash.submit()

		clash.vehicle = vehicle.name
		self.assertRaises(frappe.ValidationError, clash.save)

	def test_vehicle_type_check_still_runs_after_submission(self):
		other = "_Test GDL Van"
		if not frappe.db.exists("Fleet Vehicle Type", other):
			frappe.get_doc({"doctype": "Fleet Vehicle Type", "vehicle_type_name": other}).insert()

		vehicle = new_vehicle(vehicle_type=other)
		vehicle.insert()

		booking = new_booking(vehicle_type=TEST_TYPE)
		booking.insert()
		booking.submit()

		booking.vehicle = vehicle.name
		self.assertRaises(frappe.ValidationError, booking.save)
