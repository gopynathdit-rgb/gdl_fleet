# Copyright (c) 2026, GDL and contributors
"""
Fleet Mgmt.docx section 4.7 names this document the Movement Order Request.

frappe.rename_doc on the DocType renames the table and repoints every Link field
that referenced the old name, so existing requests and their history survive.
"""

import frappe

OLD = "Vehicle Booking Request"
NEW = "Movement Order Request"


def execute():
	if frappe.db.exists("DocType", NEW) or not frappe.db.exists("DocType", OLD):
		return

	# NOTE: the frappe.rename_doc wrapper does not accept ignore_permissions;
	# patches already run as Administrator.
	frappe.rename_doc("DocType", OLD, NEW, force=True)
	frappe.db.commit()

	# The old review workflow is replaced by the section 4.7 one.
	old_workflow = "GDL Vehicle Booking Approval"
	if frappe.db.exists("Workflow", old_workflow):
		frappe.delete_doc("Workflow", old_workflow, force=1, ignore_permissions=True)
