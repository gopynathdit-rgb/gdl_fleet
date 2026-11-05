# Copyright (c) 2026, GDL and contributors
"""
Phase 5 - extension of the STANDARD hrms Vehicle Log.

No duplicate Vehicle Log DocType. Standard fields reused rather than duplicated:

    license_plate   -> Vehicle (the Link to the standard Vehicle)
    odometer        -> Ending Odometer
    date            -> Date
    employee        -> Employee
    fuel_qty/price/supplier/invoice/service_detail  -> untouched

Vehicle Log is NOT in erpnext's `accounting_dimension_doctypes`, so cost_center
and project are added here as ordinary custom fields.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from gdl_fleet_extension.setup.vehicle_fields import GDL_MODULE, upsert_property_setter

VEHICLE_LOG_CUSTOM_FIELDS = {
	"Vehicle Log": [
		# --- trip ---
		{
			"fieldname": "gdl_trip_section",
			"label": "Trip",
			"fieldtype": "Section Break",
			"insert_after": "employee",
		},
		{
			"fieldname": "driver",
			"label": "Driver",
			"fieldtype": "Link",
			"options": "Driver",
			"insert_after": "gdl_trip_section",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "movement_order",
			"label": "Movement Order",
			"fieldtype": "Link",
			"options": "Movement Order",
			"insert_after": "driver",
			"in_standard_filter": 1,
			"description": "Where the travel was authorised through a Movement Order.",
		},
		{
			"fieldname": "usage_type",
			"label": "Usage",
			"fieldtype": "Select",
			"options": "Business\nOfficial\nPersonal\nOther",
			"default": "Official",
			"reqd": 1,
			"insert_after": "movement_order",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "gdl_trip_cb",
			"fieldtype": "Column Break",
			"insert_after": "usage_type",
		},
		{
			"fieldname": "start_location",
			"label": "Start Location",
			"fieldtype": "Data",
			"insert_after": "gdl_trip_cb",
		},
		{
			"fieldname": "destination",
			"label": "Destination",
			"fieldtype": "Data",
			"insert_after": "start_location",
		},
		{
			"fieldname": "place_to_travel",
			"label": "Place to Travel",
			"fieldtype": "Small Text",
			"reqd": 1,
			"insert_after": "destination",
			"description": "Local, district or the exact location. Mandatory per "
			"Fleet Mgmt.docx section 4.3.",
		},
		{
			"fieldname": "purpose",
			"label": "Purpose",
			"fieldtype": "Small Text",
			"insert_after": "place_to_travel",
		},
		{
			"fieldname": "gdl_remarks",
			"label": "Remarks",
			"fieldtype": "Small Text",
			"insert_after": "purpose",
			"description": "Exceptions, breakdowns, meter correction and so on.",
		},
		# --- dimensions ---
		{
			"fieldname": "gdl_dimension_section",
			"label": "Site and Accounting Dimensions",
			"fieldtype": "Section Break",
			"insert_after": "purpose",
		},
		{
			"fieldname": "site",
			"label": "Site",
			"fieldtype": "Link",
			"options": "Location",
			"insert_after": "gdl_dimension_section",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "department",
			"label": "Department",
			"fieldtype": "Link",
			"options": "Department",
			"insert_after": "site",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "gdl_dimension_cb",
			"fieldtype": "Column Break",
			"insert_after": "department",
		},
		{
			"fieldname": "cost_center",
			"label": "Cost Center",
			"fieldtype": "Link",
			"options": "Cost Center",
			"insert_after": "gdl_dimension_cb",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "project",
			"label": "Project",
			"fieldtype": "Link",
			"options": "Project",
			"insert_after": "cost_center",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "task",
			"label": "Task",
			"fieldtype": "Link",
			"options": "Task",
			"insert_after": "project",
		},
		# --- odometer ---
		{
			"fieldname": "start_odometer",
			"label": "Opening Odometer",
			"fieldtype": "Int",
			"insert_after": "last_odometer",
			"description": "Should normally equal the previous closing odometer.",
		},
		{
			"fieldname": "distance_travelled",
			"label": "Distance Travelled (KM)",
			"fieldtype": "Int",
			"read_only": 1,
			"insert_after": "odometer",
			"in_list_view": 1,
			"description": "Closing Odometer minus Opening Odometer.",
		},
	]
}

VEHICLE_LOG_PROPERTY_SETTERS = [
	("Vehicle Log", "license_plate", "label", "Vehicle", "Data"),
	("Vehicle Log", "odometer", "label", "Closing Odometer", "Data"),
	("Vehicle Log", "last_odometer", "label", "Vehicle Current Odometer", "Data"),
	("Vehicle Log", None, "search_fields", "license_plate,employee,date,odometer", "Data"),
]


def setup_vehicle_log_customisations():
	fields = {
		doctype: [dict(df, module=GDL_MODULE) for df in dfs]
		for doctype, dfs in VEHICLE_LOG_CUSTOM_FIELDS.items()
	}
	create_custom_fields(fields, ignore_validate=True, update=True)

	for doctype, fieldname, prop, value, property_type in VEHICLE_LOG_PROPERTY_SETTERS:
		upsert_property_setter(doctype, fieldname, prop, value, property_type)

	frappe.clear_cache(doctype="Vehicle Log")
