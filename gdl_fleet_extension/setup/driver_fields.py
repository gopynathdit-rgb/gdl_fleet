# Copyright (c) 2026, GDL and contributors
"""
Phase 12 - fleet context on the STANDARD erpnext Driver.

Driver already carries the licence number, issuing date, expiry date and licence
categories, so none of that is duplicated. Only the site posting and a default
vehicle are added.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from gdl_fleet_extension.setup.vehicle_fields import GDL_MODULE

DRIVER_CUSTOM_FIELDS = {
	"Driver": [
		{
			"fieldname": "gdl_fleet_section",
			"label": "Fleet",
			"fieldtype": "Section Break",
			"insert_after": "cell_number",
		},
		{
			"fieldname": "site",
			"label": "Site",
			"fieldtype": "Link",
			"options": "Location",
			"insert_after": "gdl_fleet_section",
			"in_standard_filter": 1,
			"description": "Standard ERPNext Location is the GDL site master.",
		},
		{
			"fieldname": "gdl_fleet_cb",
			"fieldtype": "Column Break",
			"insert_after": "site",
		},
		{
			"fieldname": "default_vehicle",
			"label": "Default Vehicle",
			"fieldtype": "Link",
			"options": "Vehicle",
			"insert_after": "gdl_fleet_cb",
		},
		{
			# GDL: "Can u show the Drive assignment if the drivers name is
			# assigned to any vehicle, in the drivers page."
			#
			# Read-only and derived, exactly as Vehicle.driver already is. The
			# Driver Assignment is the record; these two only report whichever
			# one is live today, so a driver's page answers "is this person on
			# a vehicle right now, and under which assignment" without opening
			# the assignment list and filtering it.
			"fieldname": "gdl_current_vehicle",
			"label": "Currently Assigned To",
			"fieldtype": "Link",
			"options": "Vehicle",
			"insert_after": "default_vehicle",
			"read_only": 1,
			"description": "The vehicle this driver is assigned to today. "
			               "Maintained from the Driver Assignment.",
		},
		{
			"fieldname": "gdl_current_assignment",
			"label": "Under Assignment",
			"fieldtype": "Link",
			"options": "Driver Assignment",
			"insert_after": "gdl_current_vehicle",
			"read_only": 1,
			"description": "Blank when the driver is not assigned to anything.",
		},
	]
}


def setup_driver_customisations():
	fields = {
		doctype: [dict(df, module=GDL_MODULE) for df in dfs]
		for doctype, dfs in DRIVER_CUSTOM_FIELDS.items()
	}
	create_custom_fields(fields, ignore_validate=True, update=True)
	refresh_current_vehicle_on_drivers()

	frappe.clear_cache(doctype="Driver")


def refresh_current_vehicle_on_drivers():
	"""Say on each Driver which vehicle they are on today.

	Run from setup, not as a patch. Patches execute BEFORE after_migrate, so a
	patch doing this found the fields it writes did not exist yet, returned
	quietly and logged itself as done - leaving every driver blank for good.

	Cheap and self-healing: it rewrites only what has changed, and an
	assignment submitted or cancelled keeps the driver in step by itself.
	"""
	if not frappe.db.has_column("Driver", "gdl_current_vehicle"):
		return

	from gdl_fleet_extension.gdl_fleet.doctype.driver_assignment.driver_assignment import (
		get_active_assignment,
	)

	for driver in frappe.get_all(
			"Driver", fields=["name", "gdl_current_vehicle", "gdl_current_assignment"]):
		live = get_active_assignment(driver.name)
		vehicle = live.vehicle if live else None
		assignment = live.name if live else None
		if (driver.gdl_current_vehicle, driver.gdl_current_assignment) == (vehicle, assignment):
			continue
		frappe.db.set_value("Driver", driver.name,
		                    {"gdl_current_vehicle": vehicle,
		                     "gdl_current_assignment": assignment},
		                    update_modified=False)
