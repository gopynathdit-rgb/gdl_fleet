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
	]
}


def setup_driver_customisations():
	fields = {
		doctype: [dict(df, module=GDL_MODULE) for df in dfs]
		for doctype, dfs in DRIVER_CUSTOM_FIELDS.items()
	}
	create_custom_fields(fields, ignore_validate=True, update=True)
	frappe.clear_cache(doctype="Driver")
