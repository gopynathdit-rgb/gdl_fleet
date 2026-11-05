# Copyright (c) 2026, GDL and contributors

import frappe

# Roles are created here so that DocType permissions and Workflow transitions can
# reference them by name. No role is ever hard-coded inside business logic.
GDL_FLEET_ROLES = [
	"Fleet Administrator",
	"Fleet User",
	"Fleet Driver",
	"Fleet Validator",
	"Fleet Reviewer",
	"Fleet Approver",
	"Fleet Maintenance User",
	"Fleet Store User",
	"Fleet Finance User",
	"Fleet HR Approver",
]


def create_roles():
	"""Idempotent: creates any missing GDL fleet role."""
	for role_name in GDL_FLEET_ROLES:
		if frappe.db.exists("Role", role_name):
			continue

		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 1,
				"is_custom": 1,
			}
		).insert(ignore_permissions=True)
