# Copyright (c) 2026, GDL and contributors
"""
Fleet Mgmt.docx section 4.7 reduces the request to Draft / Pending Review /
Accepted / Rejected. Requests raised under the earlier multi-level chain carry
statuses that no longer exist, so they are mapped onto the new set.
"""

import frappe

MAPPING = {
	"Pending Validation": "Pending Review",
	"Pending Review": "Pending Review",
	"Pending MTO/CEO": "Pending Review",
	"Pending FAS": "Pending Review",
	"Approved": "Accepted",
	"Assigned": "Accepted",
	"In Use": "Accepted",
	"Completed": "Accepted",
	"Rejected": "Rejected",
	"Cancelled": "Cancelled",
	"Draft": "Draft",
}


def execute():
	if not frappe.db.exists("DocType", "Movement Order Request"):
		return

	for old, new in MAPPING.items():
		if old == new:
			continue
		frappe.db.sql(
			"""update `tabMovement Order Request`
			   set status = %(new)s where status = %(old)s""",
			{"old": old, "new": new},
		)

	# workflow_state is a Link to Workflow State; point the retired ones at the
	# state the record now sits in.
	for old, new in MAPPING.items():
		if old == new:
			continue
		frappe.db.sql(
			"""update `tabMovement Order Request`
			   set workflow_state = %(new)s where workflow_state = %(old)s""",
			{"old": old, "new": new},
		)
	frappe.db.commit()
