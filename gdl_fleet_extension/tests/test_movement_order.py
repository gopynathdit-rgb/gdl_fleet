# Copyright (c) 2026, GDL and contributors
"""Fleet Mgmt.docx 4.8 and 4.9 - Movement Order and its approval."""

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, nowdate

from gdl_fleet_extension.gdl_fleet.doctype.movement_order.movement_order import (
	get_movement_register,
	fetch_request_details,
	make_movement_order,
)
from gdl_fleet_extension.tests.test_driver_assignment import make_driver
from gdl_fleet_extension.tests.test_movement_order_request import make_vehicle_type, new_booking
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle

MO_WORKFLOW = "GDL Movement Order Approval"
MOR_WORKFLOW = "GDL Movement Order Request Review"


class TestMovementOrder(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_vehicle_type()

	def setUp(self):
		self.vehicle = new_vehicle()
		self.vehicle.insert()
		self.driver = make_driver("MO", "DL-MO-900")

	def assign_driver(self, vehicle=None, driver=None, from_date=None):
		doc = frappe.get_doc({
			"doctype": "Driver Assignment", "vehicle": (vehicle or self.vehicle).name,
			"driver": driver or self.driver, "assignment_type": "Primary",
			"from_date": from_date or add_days(nowdate(), -30),
		})
		doc.insert()
		doc.submit()
		return doc

	def make_order(self, submit=False, **kwargs):
		values = {
			"doctype": "Movement Order", "vehicle": self.vehicle.name,
			"driver": self.driver,
			"departure_datetime": add_to_date(nowdate(), days=2, as_string=True) + " 08:00:00",
			"expected_return": add_to_date(nowdate(), days=2, as_string=True) + " 17:00:00",
			"purpose": "District office visit", "destination": "Gedu",
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert()
		if submit:
			doc.submit()
		return doc

	# --- creation -------------------------------------------------------------
	def test_create_movement_order(self):
		doc = self.make_order()
		self.assertTrue(doc.name.startswith("MO-"))
		self.assertEqual(doc.status, "Draft")

	def test_references_standard_masters(self):
		meta = frappe.get_meta("Movement Order")
		self.assertEqual(meta.get_field("vehicle").options, "Vehicle")
		self.assertEqual(meta.get_field("driver").options, "Driver")
		self.assertEqual(
			meta.get_field("movement_order_request").options, "Movement Order Request"
		)
		self.assertEqual(meta.get_field("passengers").options, "Movement Order Passenger")

	def test_document_field_set(self):
		"""Every field section 4.8 lists must exist."""
		meta = frappe.get_meta("Movement Order")
		for fieldname in ("movement_order_request", "vehicle", "driver",
		                  "departure_datetime", "expected_return", "purpose",
		                  "destination", "passengers", "contact_details", "status"):
			self.assertTrue(meta.get_field(fieldname), f"missing {fieldname}")

	def test_expected_return_must_follow_departure(self):
		doc = frappe.get_doc({
			"doctype": "Movement Order", "vehicle": self.vehicle.name,
			"driver": self.driver, "purpose": "x", "destination": "y",
			"departure_datetime": add_to_date(nowdate(), days=2, as_string=True) + " 17:00:00",
			"expected_return": add_to_date(nowdate(), days=2, as_string=True) + " 08:00:00",
		})
		self.assertRaises(frappe.ValidationError, doc.insert)

	# --- driver from the active assignment ------------------------------------
	def test_driver_fetched_from_active_assignment(self):
		self.assign_driver()
		doc = frappe.get_doc({
			"doctype": "Movement Order", "vehicle": self.vehicle.name,
			"purpose": "Field visit", "destination": "Jamjee Farm",
			"departure_datetime": add_to_date(nowdate(), days=1, as_string=True) + " 08:00:00",
			"expected_return": add_to_date(nowdate(), days=1, as_string=True) + " 16:00:00",
		})
		doc.insert()
		self.assertEqual(doc.driver, self.driver)
		self.assertTrue(doc.driver_assignment, "the assignment used was not recorded")

	def test_authorised_override_with_a_temporary_driver(self):
		"""Section 4.8 allows an authorised user to select a different driver."""
		self.assign_driver()
		relief = make_driver("Relief", "DL-REL-901")
		doc = self.make_order(driver=relief)
		self.assertEqual(doc.driver, relief)

	def test_driver_is_mandatory(self):
		self.assertTrue(frappe.get_meta("Movement Order").get_field("driver").reqd)

	# --- vehicle availability --------------------------------------------------
	def test_unavailable_vehicle_rejected(self):
		self.vehicle.db_set("vehicle_status", "Under Maintenance")
		doc = frappe.get_doc({
			"doctype": "Movement Order", "vehicle": self.vehicle.name,
			"driver": self.driver, "purpose": "x", "destination": "y",
			"departure_datetime": add_to_date(nowdate(), days=1, as_string=True) + " 08:00:00",
			"expected_return": add_to_date(nowdate(), days=1, as_string=True) + " 16:00:00",
		})
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_overlapping_orders_rejected(self):
		first = self.make_order()
		first.db_set("status", "Approved")

		clash = frappe.get_doc({
			"doctype": "Movement Order", "vehicle": self.vehicle.name,
			"driver": self.driver, "purpose": "x", "destination": "y",
			"departure_datetime": add_to_date(nowdate(), days=2, as_string=True) + " 10:00:00",
			"expected_return": add_to_date(nowdate(), days=2, as_string=True) + " 15:00:00",
		})
		self.assertRaises(frappe.ValidationError, clash.insert)

	def test_back_to_back_orders_allowed(self):
		first = self.make_order()
		first.db_set("status", "Approved")
		second = self.make_order(
			departure_datetime=add_to_date(nowdate(), days=2, as_string=True) + " 17:00:00",
			expected_return=add_to_date(nowdate(), days=2, as_string=True) + " 20:00:00",
		)
		self.assertTrue(second.name)

	def test_draft_order_does_not_hold_the_vehicle(self):
		self.make_order()
		second = self.make_order()
		self.assertTrue(second.name)

	# --- created from an accepted request --------------------------------------
	def accepted_request(self):
		request = new_booking()
		request.insert()
		apply_workflow(request, "Submit for Review")
		apply_workflow(request.reload(), "Accept")
		return request.reload()

	def test_created_from_an_accepted_request(self):
		request = self.accepted_request()
		data = make_movement_order(request.name)
		self.assertEqual(data["movement_order_request"], request.name)
		self.assertEqual(data["destination"], request.destination)
		self.assertEqual(data["purpose"], request.purpose)

	def test_the_allocation_carries_from_the_request(self):
		"""The vehicle and driver the MTO allocated must arrive on the order."""
		request = self.accepted_request()
		request.db_set("vehicle", self.vehicle.name)
		request.db_set("driver", self.driver)

		data = make_movement_order(request.name)
		self.assertEqual(data["vehicle"], self.vehicle.name)
		self.assertEqual(data["driver"], self.driver)

	def test_both_ways_of_starting_an_order_agree(self):
		"""An order can be started from the request's button OR by picking the
		request on a blank order. The two paths must produce the same order.

		They did not: vehicle and driver were set only in make_movement_order,
		so picking the request on a blank form left both mandatory fields empty
		and the user retyped an allocation the manager had already made.
		"""
		request = self.accepted_request()
		request.db_set("vehicle", self.vehicle.name)
		request.db_set("driver", self.driver)

		from_button = make_movement_order(request.name)
		from_form = fetch_request_details(request.name)

		for field in ("vehicle", "driver", "vehicle_type", "site", "purpose",
		              "destination", "departure_datetime", "expected_return"):
			self.assertEqual(
				from_form.get(field), from_button.get(field),
				f"{field} differs between the two ways of creating an order",
			)

	def test_every_mandatory_field_is_filled_from_the_request(self):
		"""Whatever the order marks mandatory had better arrive from the
		request, or the user is left filling in blanks by hand."""
		request = self.accepted_request()
		request.db_set("vehicle", self.vehicle.name)
		request.db_set("driver", self.driver)

		data = fetch_request_details(request.name)
		meta = frappe.get_meta("Movement Order")
		exempt = {"naming_series", "amended_from"}
		missing = [
			f.fieldname for f in meta.fields
			if f.reqd and f.fieldname not in exempt and not data.get(f.fieldname)
		]
		self.assertEqual(
			missing, [],
			f"these mandatory fields do not carry from the request: {missing}",
		)

	def test_cannot_create_from_an_unaccepted_request(self):
		request = new_booking()
		request.insert()
		self.assertRaises(frappe.ValidationError, make_movement_order, request.name)

	def test_cannot_create_two_orders_from_one_request(self):
		request = self.accepted_request()
		data = make_movement_order(request.name)
		order = frappe.get_doc(data)
		order.vehicle = self.vehicle.name
		order.driver = self.driver
		order.insert()
		self.assertRaises(frappe.ValidationError, make_movement_order, request.name)

	# --- workflow (section 4.9) ------------------------------------------------
	def test_workflow_is_active_and_role_driven(self):
		workflow = frappe.get_doc("Workflow", MO_WORKFLOW)
		self.assertTrue(workflow.is_active)
		self.assertEqual(workflow.document_type, "Movement Order")
		for row in workflow.transitions:
			self.assertTrue(frappe.db.exists("Role", row.allowed))

	def test_workflow_states_match_the_simple_chain(self):
		"""Client, 3 Nov 2026: "User will apply, manager will approve, and
		create Movement order." The blueprint's five-stage chain was more than
		GDL wants, so the live workflow is the simple one."""
		states = {s.state for s in frappe.get_doc("Workflow", MO_WORKFLOW).states}
		for state in ("Draft", "Pending Approval", "Approved", "Dispatched",
		              "Completed", "Rejected", "Cancelled"):
			self.assertIn(state, states)

	def test_the_chain_is_one_approval(self):
		workflow = frappe.get_doc("Workflow", MO_WORKFLOW)
		hops = {(t.state, t.action): (t.next_state, t.allowed) for t in workflow.transitions}
		self.assertEqual(hops[("Draft", "Submit for Approval")],
		                 ("Pending Approval", "Fleet User"))
		self.assertEqual(hops[("Pending Approval", "Approve")],
		                 ("Approved", "Fleet Approver"))
		# Nothing may reach Approved by any other route.
		routes = [t for t in workflow.transitions if t.next_state == "Approved"]
		self.assertEqual(len(routes), 1, "more than one way to approve an order")

	def test_the_approving_stage_can_reject_and_rejection_stays_editable(self):
		workflow = frappe.get_doc("Workflow", MO_WORKFLOW)
		rejecting = {t.state for t in workflow.transitions if t.action == "Reject"}
		self.assertIn("Pending Approval", rejecting)
		states = {s.state: int(s.doc_status) for s in workflow.states}
		self.assertEqual(states["Rejected"], 0, "a rejected order must stay editable")

	def test_not_dispatchable_until_approved(self):
		"""Section 4.9: the order is not valid for dispatch before approval."""
		workflow = frappe.get_doc("Workflow", MO_WORKFLOW)
		dispatch = next(t for t in workflow.transitions if t.action == "Dispatch")
		self.assertEqual(dispatch.state, "Approved",
		                 "Dispatch must only be reachable from Approved")

	def test_approval_progression(self):
		"""Walk the chain GDL actually uses, end to end."""
		doc = self.make_order()
		apply_workflow(doc, "Submit for Approval")
		doc.reload()
		self.assertEqual(doc.status, "Pending Approval")
		self.assertEqual(doc.docstatus, 0, "Pending Approval must remain editable")

		apply_workflow(doc, "Approve")
		doc.reload()
		self.assertEqual(doc.status, "Approved")
		self.assertEqual(doc.docstatus, 1)

		apply_workflow(doc, "Dispatch")
		doc.reload()
		self.assertEqual(doc.status, "Dispatched")

		apply_workflow(doc, "Complete")
		doc.reload()
		self.assertEqual(doc.status, "Completed")

	def test_rejection_leaves_it_editable_for_resubmission(self):
		doc = self.make_order()
		apply_workflow(doc, "Submit for Approval")
		apply_workflow(doc.reload(), "Reject")
		doc.reload()
		self.assertEqual(doc.status, "Rejected")
		self.assertEqual(doc.docstatus, 0)

		apply_workflow(doc, "Resubmit")
		doc.reload()
		self.assertEqual(doc.status, "Pending Approval")

	def test_cancellation_preserves_the_record(self):
		doc = self.make_order()
		for action in ("Submit for Approval", "Approve"):
			apply_workflow(doc.reload(), action)
		apply_workflow(doc.reload(), "Cancel")
		doc.reload()
		self.assertEqual(doc.status, "Cancelled")
		self.assertTrue(frappe.db.exists("Movement Order", doc.name))

	# --- register --------------------------------------------------------------
	def test_movement_register(self):
		doc = self.make_order()
		rows = get_movement_register(vehicle=self.vehicle.name)
		self.assertTrue(rows)
		row = rows[0]
		for key in ("vehicle", "driver", "departure_datetime", "destination",
		            "purpose", "status", "department"):
			self.assertIn(key, row)

	def test_passenger_list(self):
		doc = self.make_order()
		doc.append("passengers", {"passenger_name": "Kinley Zangmo",
		                          "designation": "Accounts Officer",
		                          "contact_no": "17112233"})
		doc.save()
		self.assertEqual(len(doc.passengers), 1)

	def test_permissions(self):
		roles = {p.role for p in frappe.get_meta("Movement Order").permissions}
		self.assertIn("Fleet Administrator", roles)
		self.assertIn("Fleet Approver", roles)
