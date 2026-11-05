"""Show one fleet entry on the desk instead of two.

Hides the `Fleet Management` workspace from the older gdl_fleet_management app
and brings `GDL Fleet` to the front. Nothing is deleted - see
setup/workspace_visibility.py for how to reverse it.
"""

import frappe

from gdl_fleet_extension.setup.workspace_visibility import setup_workspace_visibility


def execute():
	setup_workspace_visibility()
	frappe.db.commit()
