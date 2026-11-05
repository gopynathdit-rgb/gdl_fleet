# Copyright (c) 2026, GDL and contributors
"""
Desk visibility: one fleet entry, not two.

Two fleet modules are installed. `gdl_fleet_management` is the earlier app and
`gdl_fleet_extension` is the one in use, so users were seeing two fleet tiles
and had no way of telling which to open.

This hides the old workspace and brings the current one to the front. It is
done here, as data, because the old app's source must not be edited - its
`fleet_management/` module is uncommitted work. To bring the old page back, set
`public` to 1 and `is_hidden` to 0 on the Workspace record, or remove the call
to this module from setup/install.py and migrate.

Nothing belonging to the old app is deleted. Its DocTypes, records and source
all stay exactly as they are, and the workspace itself can be brought back.
"""

import frappe

SUPERSEDED_WORKSPACE = "Fleet Management"
CURRENT_WORKSPACE = "GDL Fleet"
CURRENT_SEQUENCE = 1.5          # just after Home, so it leads the fleet area


def hide_superseded_workspace():
	"""Take the old fleet workspace off the desk without deleting it."""
	if not frappe.db.exists("Workspace", SUPERSEDED_WORKSPACE):
		return False

	app = frappe.db.get_value("Workspace", SUPERSEDED_WORKSPACE, "app")
	if app != "gdl_fleet_management":
		# Someone has repointed it; leave it alone rather than hide the wrong page.
		return False

	current = frappe.db.get_value("Workspace", SUPERSEDED_WORKSPACE,
	                              ["is_hidden", "public"], as_dict=True)
	if current.is_hidden and not current.public:
		return False

	# `is_hidden` alone is only a hint to the front end, and anyone holding
	# Workspace Manager - Administrator included - bypasses the server filters
	# entirely and would still see the page. Clearing `public` is what actually
	# takes it off the desk: a non-public workspace belongs to the user named in
	# `for_user`, and with that empty it belongs to nobody. Both fields are set
	# so the intent is readable either way.
	frappe.db.set_value("Workspace", SUPERSEDED_WORKSPACE,
	                    {"is_hidden": 1, "public": 0}, update_modified=False)
	return True


def promote_current_workspace():
	"""Bring GDL Fleet to the front of the workspace order."""
	if not frappe.db.exists("Workspace", CURRENT_WORKSPACE):
		return False

	current = frappe.db.get_value("Workspace", CURRENT_WORKSPACE, "sequence_id")
	if current == CURRENT_SEQUENCE:
		return False

	frappe.db.set_value("Workspace", CURRENT_WORKSPACE, "sequence_id", CURRENT_SEQUENCE,
	                    update_modified=False)
	return True


def setup_workspace_visibility():
	"""Run on install and after every migrate, so a sync cannot undo it."""
	hidden = hide_superseded_workspace()
	promoted = promote_current_workspace()
	if hidden or promoted:
		frappe.clear_cache()
	return {"hid_superseded": hidden, "promoted_current": promoted}


def has_app_permission():
	"""Who sees the GDL Fleet tile on the apps screen.

	Anyone holding a fleet role, plus System Manager. Returning True on an
	unexpected error would be wrong, but so would hiding the app from everyone,
	so the check stays deliberately simple.
	"""
	roles = set(frappe.get_roles())
	if "System Manager" in roles or "Administrator" in roles:
		return True
	return any(role.startswith("Fleet ") for role in roles)
