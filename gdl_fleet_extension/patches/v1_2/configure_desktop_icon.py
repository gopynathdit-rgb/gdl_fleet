"""Put GDL Fleet on the Desk home and clear the dead Fleet Management tile.

The Desk home grid is built from Desktop Icon records. gdl_fleet_management
left one behind when it was uninstalled - it was created at runtime rather than
shipped by the app, so the uninstall did not claim it - and it pointed at a
workspace that no longer exists, which is what produced "Icon is not correctly
configured please check the workspace sidebar to it".
"""

import frappe

from gdl_fleet_extension.setup.desktop_icon import setup_desktop_icon


def execute():
	setup_desktop_icon()
	frappe.db.commit()
