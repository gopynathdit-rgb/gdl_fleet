# Copyright (c) 2026, GDL and contributors
"""
Phase 4 - approval chain as standard ERPNext Workflow data.

    User -> Validator -> Reviewer -> MTO/CEO -> FAS -> Approved

Every transition names a ROLE, never a user. States, roles and the number of
levels are data, so GDL can change the chain without a code change.
"""

import frappe

WORKFLOW_NAME = "GDL Movement Order Request Review"
DOCTYPE = "Movement Order Request"


# Fleet Mgmt.docx section 4.7: the request is reviewed for vehicle availability
# and simply Accepted or Rejected. Approval proper moves to the Movement Order
# (section 4.9), so the earlier five-level chain does not apply here.
STATES = {
	"Draft": (0, "Fleet User", ""),
	"Pending Review": (0, "Fleet Administrator", "Warning"),
	"Accepted": (1, "Fleet Administrator", "Success"),
	"Rejected": (0, "Fleet Administrator", "Danger"),
	"Cancelled": (2, "Fleet Administrator", "Danger"),
}

# Client, 3 Nov 2026: "User will apply, manager will approve." The manager is
# the location MTO, who holds Fleet Approver - not Fleet Administrator, which
# is a configuration seat and should not have to be handed to every farm. The
# administrator keeps the ability through a second row on the same transition.
TRANSITIONS = [
	("Draft", "Submit for Review", "Pending Review", "Fleet User", None),
	("Pending Review", "Accept", "Accepted", "Fleet Approver", None),
	("Pending Review", "Reject", "Rejected", "Fleet Approver", None),
	("Pending Review", "Accept", "Accepted", "Fleet Administrator", None),
	("Pending Review", "Reject", "Rejected", "Fleet Administrator", None),
	("Accepted", "Cancel", "Cancelled", "Fleet Administrator", None),
]


# Actions the ORIGINATOR performs on their own document. Frappe's
# allow_self_approval guard blocks a user from acting on a document they own -
# which is right for an approval and wrong for a submission: with it set on
# "Submit for Review", nobody can send in their own vehicle request at all.
#
# The approval actions - Accept, Validate, Review, Approve, Clear - keep the
# guard, so an MTO who raises a request cannot approve it themselves. The head
# office MTO covers that case, which is what a final authority is for.
ORIGINATOR_ACTIONS = {
	"Submit for Review",
	"Submit for Approval",
	"Submit for Validation",
	"Resubmit",
	# Post-approval operational steps, not approvals. The administrator who
	# raised an order still has to be able to send it out and close it off.
	"Dispatch",
	"Complete",
	"Cancel",
}


# The Movement Order is raised FROM a request the location MTO has already
# accepted, so the approval decision is made before the order exists. Blocking
# that same MTO from approving the order they just created would turn one
# decision into two - exactly the chain GDL asked us to remove - and the
# location check in movement_order.py already proves they are the right
# approver. The REQUEST keeps the guard, so the decision itself still cannot
# be self-approved.
SELF_APPROVABLE_BY_WORKFLOW = {
	"GDL Movement Order Approval": {"Approve"},
}


def allows_self(action: str, workflow: str | None = None) -> int:
	if action in ORIGINATOR_ACTIONS:
		return 1
	return 1 if action in SELF_APPROVABLE_BY_WORKFLOW.get(workflow, ()) else 0


def create_workflow_states():
	for state, (_docstatus, _role, style) in STATES.items():
		if frappe.db.exists("Workflow State", state):
			continue
		frappe.get_doc(
			{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
		).insert(ignore_permissions=True)


def create_workflow_actions():
	actions = sorted({t[1] for t in TRANSITIONS})
	for action in actions:
		if frappe.db.exists("Workflow Action Master", action):
			continue
		frappe.get_doc(
			{"doctype": "Workflow Action Master", "workflow_action_name": action}
		).insert(ignore_permissions=True)


def create_movement_request_workflow():
	"""Idempotent. Section 4.7 review workflow on the Movement Order Request."""
	create_workflow_states()
	create_workflow_actions()

	if frappe.db.exists("Workflow", WORKFLOW_NAME):
		workflow = frappe.get_doc("Workflow", WORKFLOW_NAME)
	else:
		workflow = frappe.new_doc("Workflow")
		workflow.workflow_name = WORKFLOW_NAME

	workflow.document_type = DOCTYPE
	workflow.workflow_state_field = "workflow_state"
	workflow.is_active = 1
	workflow.send_email_alert = 0
	# `status` is a plain Select kept in step with the workflow state.
	workflow.override_status = 0

	workflow.set("states", [])
	for state, (docstatus, role, _style) in STATES.items():
		workflow.append(
			"states",
			{
				"state": state,
				"doc_status": str(docstatus),
				"allow_edit": role,
				"update_field": "status",
				"update_value": state,
			},
		)

	workflow.set("transitions", [])
	for from_state, action, to_state, role, condition in TRANSITIONS:
		row = {
			"state": from_state,
			"action": action,
			"next_state": to_state,
			"allowed": role,
			"allow_self_approval": allows_self(action, WORKFLOW_NAME),
		}
		if condition:
			row["condition"] = condition
		workflow.append("transitions", row)

	workflow.flags.ignore_permissions = True
	workflow.save()
	return workflow.name


# ---------------------------------------------------------------------------
# Fleet Mgmt.docx sections 4.8 and 4.9 - Movement Order approval.
# The order is not valid for dispatch until an authorised approver approves it.
# ---------------------------------------------------------------------------
MO_WORKFLOW_NAME = "GDL Movement Order Approval"
MO_DOCTYPE = "Movement Order"

# Final document, GAP item 2: the approval chain is
#
#     User -> Validate -> Reviewer -> MTO/CEO -> FAS
#
# Every stage before approval stays at docstatus 0, because frappe cannot
# return a submitted document to draft - a rejection has to leave the record
# editable so the originator can correct and resubmit it. Only the final FAS
# clearance carries the order to docstatus 1, after which it can be dispatched.
#
# Roles already exist from the role setup; no new role is invented here.
MO_STATES = {
	"Draft": (0, "Fleet User", ""),
	"Pending Validation": (0, "Fleet Validator", "Warning"),
	"Pending Review": (0, "Fleet Reviewer", "Warning"),
	"Pending MTO/CEO": (0, "Fleet Approver", "Warning"),
	"Pending FAS": (0, "Fleet Finance User", "Warning"),
	"Approved": (1, "Fleet Administrator", "Success"),
	"Dispatched": (1, "Fleet Administrator", "Primary"),
	"Completed": (1, "Fleet Administrator", "Success"),
	"Rejected": (0, "Fleet Administrator", "Danger"),
	"Cancelled": (2, "Fleet Administrator", "Danger"),
}

# Client, 3 Nov 2026: "User will apply, manager will approve, and create
# Movement order." The five-stage chain above was more than GDL wants, so the
# SIMPLE chain below is the default and the full one is kept, switched off, in
# GDL Fleet Settings. Nothing is deleted: an order already sitting at Pending
# FAS keeps its state, and flipping the setting back restores the full chain.
MO_SIMPLE_STATES = {
	"Draft": (0, "Fleet User", ""),
	"Pending Approval": (0, "Fleet Approver", "Warning"),
	"Approved": (1, "Fleet Administrator", "Success"),
	"Dispatched": (1, "Fleet Administrator", "Primary"),
	"Completed": (1, "Fleet Administrator", "Success"),
	"Rejected": (0, "Fleet Administrator", "Danger"),
	"Cancelled": (2, "Fleet Administrator", "Danger"),
}

MO_SIMPLE_TRANSITIONS = [
	("Draft", "Submit for Approval", "Pending Approval", "Fleet User", None),
	("Pending Approval", "Approve", "Approved", "Fleet Approver", None),
	("Pending Approval", "Reject", "Rejected", "Fleet Approver", None),
	("Rejected", "Resubmit", "Pending Approval", "Fleet User", None),
	("Approved", "Dispatch", "Dispatched", "Fleet Administrator", None),
	("Dispatched", "Complete", "Completed", "Fleet Administrator", None),
	("Approved", "Cancel", "Cancelled", "Fleet Administrator", None),
]

SIMPLE = "Simple"


def movement_chain_is_simple() -> bool:
	"""Which chain GDL has chosen. Defaults to Simple on a site with no setting."""
	chosen = frappe.db.get_single_value("GDL Fleet Settings", "movement_approval_chain")
	return (chosen or SIMPLE) == SIMPLE


MO_TRANSITIONS = [
	("Draft", "Submit for Validation", "Pending Validation", "Fleet User", None),
	("Pending Validation", "Validate", "Pending Review", "Fleet Validator", None),
	("Pending Validation", "Reject", "Rejected", "Fleet Validator", None),
	("Pending Review", "Review", "Pending MTO/CEO", "Fleet Reviewer", None),
	("Pending Review", "Reject", "Rejected", "Fleet Reviewer", None),
	("Pending MTO/CEO", "Approve", "Pending FAS", "Fleet Approver", None),
	("Pending MTO/CEO", "Reject", "Rejected", "Fleet Approver", None),
	("Pending FAS", "Clear", "Approved", "Fleet Finance User", None),
	("Pending FAS", "Reject", "Rejected", "Fleet Finance User", None),
	("Rejected", "Resubmit", "Pending Validation", "Fleet User", None),
	("Approved", "Dispatch", "Dispatched", "Fleet Administrator", None),
	("Dispatched", "Complete", "Completed", "Fleet Administrator", None),
	("Approved", "Cancel", "Cancelled", "Fleet Administrator", None),
]


def create_movement_order_workflow():
	simple = movement_chain_is_simple()
	states = MO_SIMPLE_STATES if simple else MO_STATES
	transitions = MO_SIMPLE_TRANSITIONS if simple else MO_TRANSITIONS

	# Every state of BOTH chains is created, so an order left mid-approval on
	# the full chain still resolves its state after a switch to the simple one.
	for state, (_docstatus, _role, style) in {**MO_STATES, **MO_SIMPLE_STATES}.items():
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
			).insert(ignore_permissions=True)

	for action in sorted({t[1] for t in MO_TRANSITIONS + MO_SIMPLE_TRANSITIONS}):
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	if frappe.db.exists("Workflow", MO_WORKFLOW_NAME):
		workflow = frappe.get_doc("Workflow", MO_WORKFLOW_NAME)
	else:
		workflow = frappe.new_doc("Workflow")
		workflow.workflow_name = MO_WORKFLOW_NAME

	workflow.document_type = MO_DOCTYPE
	workflow.workflow_state_field = "workflow_state"
	workflow.is_active = 1
	workflow.send_email_alert = 0
	workflow.override_status = 0

	workflow.set("states", [])
	for state, (docstatus, role, _style) in states.items():
		workflow.append("states", {"state": state, "doc_status": str(docstatus),
		                           "allow_edit": role, "update_field": "status",
		                           "update_value": state})

	workflow.set("transitions", [])
	for from_state, action, to_state, role, condition in transitions:
		row = {"state": from_state, "action": action, "next_state": to_state,
		       "allowed": role, "allow_self_approval": allows_self(action, MO_WORKFLOW_NAME)}
		if condition:
			row["condition"] = condition
		workflow.append("transitions", row)

	workflow.flags.ignore_permissions = True
	workflow.save()
	return workflow.name


# ---------------------------------------------------------------------------
# POL Abstract approval
#
# The workbook signs off "Submitted By: Thinley Dorji / Driver" and
# "Approved by: Mr. Sonam Tobgye / Head-HR", so the driver raises the abstract
# and HR/MTO approves it.
#
# Approval is what carries the abstract to docstatus 1. Everything before that
# stays at docstatus 0, because frappe cannot return a submitted document to
# draft - a rejection has to leave the record editable so the driver can
# correct and resubmit it.
# ---------------------------------------------------------------------------
POL_WORKFLOW_NAME = "GDL POL Approval"
POL_DOCTYPE = "POL Abstract"

POL_STATES = {
	"Draft": (0, "Fleet Driver", ""),
	"Submitted": (0, "Fleet HR Approver", "Warning"),
	"Approved": (1, "Fleet HR Approver", "Success"),
	"Rejected": (0, "Fleet Driver", "Danger"),
	"Cancelled": (2, "Fleet Administrator", "Danger"),
}

POL_TRANSITIONS = [
	("Draft", "Submit for Approval", "Submitted", "Fleet Driver", None),
	("Submitted", "Approve", "Approved", "Fleet HR Approver", None),
	("Submitted", "Reject", "Rejected", "Fleet HR Approver", None),
	("Rejected", "Resubmit", "Submitted", "Fleet Driver", None),
	("Approved", "Cancel", "Cancelled", "Fleet Administrator", None),
]


def create_pol_workflow():
	for state, (_docstatus, _role, style) in POL_STATES.items():
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
			).insert(ignore_permissions=True)

	for action in sorted({t[1] for t in POL_TRANSITIONS}):
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	if frappe.db.exists("Workflow", POL_WORKFLOW_NAME):
		workflow = frappe.get_doc("Workflow", POL_WORKFLOW_NAME)
	else:
		workflow = frappe.new_doc("Workflow")
		workflow.workflow_name = POL_WORKFLOW_NAME

	workflow.document_type = POL_DOCTYPE
	workflow.workflow_state_field = "workflow_state"
	workflow.is_active = 1
	workflow.send_email_alert = 0
	workflow.override_status = 0

	workflow.set("states", [])
	for state, (docstatus, role, _style) in POL_STATES.items():
		workflow.append("states", {"state": state, "doc_status": str(docstatus),
		                           "allow_edit": role, "update_field": "status",
		                           "update_value": state})

	workflow.set("transitions", [])
	for from_state, action, to_state, role, condition in POL_TRANSITIONS:
		row = {"state": from_state, "action": action, "next_state": to_state,
		       "allowed": role, "allow_self_approval": allows_self(action, POL_WORKFLOW_NAME)}
		if condition:
			row["condition"] = condition
		workflow.append("transitions", row)

	workflow.flags.ignore_permissions = True
	workflow.save()
	return workflow.name
