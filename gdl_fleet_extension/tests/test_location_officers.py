# Copyright (c) 2026, GDL and contributors
"""
Location-wise MTO approval.

Client, 3 Nov 2026:
    "create a user and a manager (MTO location wise)."
    "and final MTO will be at head office."

One approval per request, given by the manager named for that location. The
head office MTO is a WIDER permission, not a second step - these tests pin
that distinction down, because getting it wrong turns one approval into two.
"""

import frappe
from frappe.tests import IntegrationTestCase

from gdl_fleet_extension.setup.workflows import (
	MO_SIMPLE_STATES,
	MO_SIMPLE_TRANSITIONS,
	MO_STATES,
	MO_WORKFLOW_NAME,
	WORKFLOW_NAME as MOR_WORKFLOW_NAME,
	allows_self,
	movement_chain_is_simple,
)
from gdl_fleet_extension.utils.location_officers import (
	get_approvers_for_location,
	get_head_office_mto,
	get_mto_for_location,
	may_approve,
	validate_approver,
)

HEAD = "Head Office"


def make_location(name):
	if not frappe.db.exists("Location", name):
		doc = frappe.get_doc({"doctype": "Location", "location_name": name, "is_group": 0})
		doc.flags.ignore_permissions = True
		doc.insert()
	return name


def make_user(email):
	if not frappe.db.exists("User", email):
		doc = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": email.split("@")[0],
			"user_type": "System User", "send_welcome_email": 0, "enabled": 1,
		})
		doc.flags.ignore_permissions = True
		doc.insert()
	return email


class LocationOfficerCase(IntegrationTestCase):
	"""Installs a known officer table and puts the original back afterwards."""

	LOCATIONS = ["GDL-TEST-ALPHA", "GDL-TEST-BRAVO", "GDL-TEST-HEAD"]

	def setUp(self):
		self.settings = frappe.get_single("GDL Fleet Settings")
		self.original = [row.as_dict() for row in self.settings.get("location_officers") or []]
		self.original_enforce = self.settings.enforce_location_mto

		for name in self.LOCATIONS:
			make_location(name)
		self.alpha_mto = make_user("alpha.mto@gdl.test")
		self.bravo_mto = make_user("bravo.mto@gdl.test")
		self.head_mto = make_user("head.mto@gdl.test")
		self.nobody = make_user("nobody@gdl.test")

		self.settings.set("location_officers", [])
		for location, mto, is_head in [
			("GDL-TEST-ALPHA", self.alpha_mto, 0),
			("GDL-TEST-BRAVO", self.bravo_mto, 0),
			("GDL-TEST-HEAD", self.head_mto, 1),
		]:
			self.settings.append("location_officers",
			                     {"location": location, "mto": mto, "is_head_office": is_head})
		self.settings.enforce_location_mto = 1
		self.settings.flags.ignore_permissions = True
		self.settings.save()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def tearDown(self):
		settings = frappe.get_single("GDL Fleet Settings")
		settings.set("location_officers", [])
		for row in self.original:
			settings.append("location_officers", row)
		settings.enforce_location_mto = self.original_enforce
		settings.flags.ignore_permissions = True
		settings.save()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")


class TestWhoApproves(LocationOfficerCase):
	def test_each_location_resolves_its_own_mto(self):
		self.assertEqual(get_mto_for_location("GDL-TEST-ALPHA"), self.alpha_mto)
		self.assertEqual(get_mto_for_location("GDL-TEST-BRAVO"), self.bravo_mto)

	def test_the_head_office_row_is_the_final_mto(self):
		self.assertEqual(get_head_office_mto(), self.head_mto)

	def test_an_mto_approves_their_own_location(self):
		self.assertTrue(may_approve("GDL-TEST-ALPHA", self.alpha_mto))

	def test_an_mto_cannot_approve_another_location(self):
		"""The whole point of naming a manager per location."""
		self.assertFalse(may_approve("GDL-TEST-BRAVO", self.alpha_mto))

	def test_the_head_office_mto_approves_anywhere(self):
		"""Final authority and the cover when a location MTO is away."""
		self.assertTrue(may_approve("GDL-TEST-ALPHA", self.head_mto))
		self.assertTrue(may_approve("GDL-TEST-BRAVO", self.head_mto))

	def test_someone_with_no_row_approves_nothing(self):
		self.assertFalse(may_approve("GDL-TEST-ALPHA", self.nobody))

	def test_head_office_is_listed_after_the_local_mto(self):
		"""The local manager should act first; head office is the fallback."""
		self.assertEqual(
			get_approvers_for_location("GDL-TEST-ALPHA"),
			[self.alpha_mto, self.head_mto],
		)

	def test_approval_is_one_step_not_two(self):
		"""Head office being allowed must not mean head office is REQUIRED.

		If this ever fails, the flow has quietly become a two-stage chain.
		"""
		self.assertTrue(may_approve("GDL-TEST-ALPHA", self.alpha_mto))

	def test_a_location_with_no_mto_is_covered_by_head_office(self):
		"""GDL will add locations before they add that location's manager.
		Until then the final MTO covers it - that is what final authority is
		for - rather than the request being approvable by anyone."""
		make_location("GDL-TEST-UNLISTED")
		self.assertTrue(may_approve("GDL-TEST-UNLISTED", self.head_mto))
		self.assertFalse(may_approve("GDL-TEST-UNLISTED", self.nobody))
		self.assertFalse(may_approve("GDL-TEST-UNLISTED", self.alpha_mto))

	def test_an_empty_table_falls_back_to_the_role_check(self):
		"""Before GDL configures anything, the workflow's own role gate is the
		only check - the module must not lock itself on day one."""
		settings = frappe.get_single("GDL Fleet Settings")
		settings.set("location_officers", [])
		settings.flags.ignore_permissions = True
		settings.save()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
		self.assertTrue(may_approve("GDL-TEST-ALPHA", self.nobody))

	def test_switching_enforcement_off_lets_the_role_decide(self):
		settings = frappe.get_single("GDL Fleet Settings")
		settings.enforce_location_mto = 0
		settings.flags.ignore_permissions = True
		settings.save()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
		self.assertTrue(may_approve("GDL-TEST-BRAVO", self.alpha_mto))

	def test_the_refusal_names_who_should_act(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			validate_approver("GDL-TEST-BRAVO", self.alpha_mto)
		message = str(caught.exception)
		self.assertIn(self.bravo_mto, message)
		self.assertIn(self.head_mto, message)


class TestOfficerTableValidation(LocationOfficerCase):
	def save_officers(self, rows):
		settings = frappe.get_single("GDL Fleet Settings")
		settings.set("location_officers", [])
		for row in rows:
			settings.append("location_officers", row)
		settings.flags.ignore_permissions = True
		settings.save()

	def test_one_location_cannot_have_two_mtos(self):
		with self.assertRaises(frappe.ValidationError):
			self.save_officers([
				{"location": "GDL-TEST-ALPHA", "mto": self.alpha_mto},
				{"location": "GDL-TEST-ALPHA", "mto": self.bravo_mto},
			])

	def test_there_is_only_one_final_mto(self):
		with self.assertRaises(frappe.ValidationError):
			self.save_officers([
				{"location": "GDL-TEST-ALPHA", "mto": self.alpha_mto, "is_head_office": 1},
				{"location": "GDL-TEST-HEAD", "mto": self.head_mto, "is_head_office": 1},
			])

	def test_a_disabled_user_cannot_be_an_mto(self):
		frappe.db.set_value("User", self.bravo_mto, "enabled", 0)
		try:
			with self.assertRaises(frappe.ValidationError):
				self.save_officers([{"location": "GDL-TEST-BRAVO", "mto": self.bravo_mto}])
		finally:
			frappe.db.set_value("User", self.bravo_mto, "enabled", 1)

	def test_a_group_location_is_refused(self):
		"""Vehicles belong to the locations under a group, not to the group."""
		if not frappe.db.exists("Location", "GDL-TEST-GROUP"):
			doc = frappe.get_doc({"doctype": "Location", "location_name": "GDL-TEST-GROUP",
			                      "is_group": 1})
			doc.flags.ignore_permissions = True
			doc.insert()
		with self.assertRaises(frappe.ValidationError):
			self.save_officers([{"location": "GDL-TEST-GROUP", "mto": self.alpha_mto}])


class TestSimplifiedChain(IntegrationTestCase):
	"""Client: "User will apply, manager will approve, and create Movement order"."""

	def test_the_simple_chain_is_one_approval(self):
		approvals = [t for t in MO_SIMPLE_TRANSITIONS if t[2] == "Approved"]
		self.assertEqual(len(approvals), 1, "more than one route to Approved")
		self.assertEqual(approvals[0][0], "Pending Approval")

	def test_the_simple_chain_has_no_intermediate_stages(self):
		for retired in ("Pending Validation", "Pending Review", "Pending MTO/CEO", "Pending FAS"):
			self.assertNotIn(retired, MO_SIMPLE_STATES)

	def test_the_full_chain_is_kept_not_deleted(self):
		"""Switchable, so an order mid-approval is never stranded."""
		for stage in ("Pending Validation", "Pending Review", "Pending MTO/CEO", "Pending FAS"):
			self.assertIn(stage, MO_STATES)

	def test_this_site_runs_the_simple_chain(self):
		self.assertTrue(movement_chain_is_simple())

	def test_the_live_workflow_matches_the_simple_chain(self):
		workflow = frappe.get_doc("Workflow", "GDL Movement Order Approval")
		self.assertEqual(
			{s.state for s in workflow.states}, set(MO_SIMPLE_STATES),
			"the workflow on this site is not the simple chain - run bench migrate",
		)

	def test_a_user_submits_and_an_approver_approves(self):
		workflow = frappe.get_doc("Workflow", "GDL Movement Order Approval")
		roles = {(t.state, t.action): t.allowed for t in workflow.transitions}
		self.assertEqual(roles[("Draft", "Submit for Approval")], "Fleet User")
		self.assertEqual(roles[("Pending Approval", "Approve")], "Fleet Approver")

	def test_the_request_is_accepted_by_the_manager_not_an_administrator(self):
		"""Fleet Administrator is a configuration seat; a farm manager should
		not need it just to accept a vehicle request."""
		workflow = frappe.get_doc("Workflow", "GDL Movement Order Request Review")
		accepting = {t.allowed for t in workflow.transitions
		             if t.action == "Accept" and t.state == "Pending Review"}
		self.assertIn("Fleet Approver", accepting)


class TestSelfApprovalGuard(IntegrationTestCase):
	"""Who may act on a document they themselves raised.

	Both of these were live defects found by driving the flow end to end on
	staging, not by reading the code.
	"""

	def test_a_user_can_submit_their_own_request(self):
		"""With the guard on every transition, nobody could send in a request
		at all - submitting is not approving."""
		self.assertEqual(allows_self("Submit for Review", MOR_WORKFLOW_NAME), 1)
		self.assertEqual(allows_self("Submit for Approval", MO_WORKFLOW_NAME), 1)
		self.assertEqual(allows_self("Resubmit", MO_WORKFLOW_NAME), 1)

	def test_the_request_decision_cannot_be_self_approved(self):
		"""An MTO who raises a request must not accept it themselves. The head
		office MTO covers that case."""
		self.assertEqual(allows_self("Accept", MOR_WORKFLOW_NAME), 0)
		self.assertEqual(allows_self("Reject", MOR_WORKFLOW_NAME), 0)

	def test_the_order_may_be_approved_by_the_manager_who_raised_it(self):
		"""The decision was already made when the request was accepted. Asking
		for a second person here would re-create the chain GDL removed."""
		self.assertEqual(allows_self("Approve", MO_WORKFLOW_NAME), 1)

	def test_the_pol_abstract_still_needs_a_second_pair_of_eyes(self):
		"""A driver may not approve their own fuel claim."""
		self.assertEqual(allows_self("Approve", "GDL POL Approval"), 0)

	def test_dispatch_and_complete_are_not_approvals(self):
		"""The administrator who raised an order still has to be able to send
		it out and close it off."""
		self.assertEqual(allows_self("Dispatch", MO_WORKFLOW_NAME), 1)
		self.assertEqual(allows_self("Complete", MO_WORKFLOW_NAME), 1)

	def test_the_live_workflows_agree(self):
		for workflow_name in (MOR_WORKFLOW_NAME, MO_WORKFLOW_NAME, "GDL POL Approval"):
			workflow = frappe.get_doc("Workflow", workflow_name)
			for row in workflow.transitions:
				self.assertEqual(
					int(row.allow_self_approval),
					allows_self(row.action, workflow_name),
					f"{workflow_name}: {row.action} disagrees with the rule",
				)


class TestTheManagerCanAllocate(IntegrationTestCase):
	"""The MTO allocates the vehicle when accepting - the requester never does."""

	def perm(self, role, permlevel):
		return frappe.db.get_value(
			"DocPerm",
			{"parent": "Movement Order Request", "role": role, "permlevel": permlevel},
			["read", "write"], as_dict=True,
		)

	def test_the_allocation_fields_are_protected(self):
		meta = frappe.get_meta("Movement Order Request")
		for fieldname in ("vehicle", "driver"):
			self.assertEqual(
				meta.get_field(fieldname).permlevel, 1,
				f"{fieldname} must sit above the requester's reach",
			)

	def test_the_requester_cannot_allocate(self):
		"""A user picking their own vehicle would make availability meaningless."""
		self.assertEqual(int(self.perm("Fleet User", 1).write), 0)

	def test_the_manager_can_allocate(self):
		"""Without this the allocation is silently dropped on save and the
		Movement Order is raised with no vehicle at all."""
		row = self.perm("Fleet Approver", 1)
		self.assertEqual(int(row.read), 1)
		self.assertEqual(int(row.write), 1, "the MTO cannot allocate a vehicle")
