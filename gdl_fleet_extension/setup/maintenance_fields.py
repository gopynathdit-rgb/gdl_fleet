# Copyright (c) 2026, GDL and contributors
"""
Phase 7 - extension of the STANDARD ERPNext Assets maintenance DocTypes.

Preventive : Asset Maintenance -> Asset Maintenance Task -> Asset Maintenance Log
Corrective : Asset Repair  (already gives downtime, repair_cost, stock_items that
             create a Material Issue Stock Entry, cost_center, project and GL)

`vehicle` on Asset Repair and Asset is supplied by the Phase 3 Accounting
Dimension, so it is deliberately NOT declared here. Asset Maintenance and Asset
Maintenance Log are not dimension DocTypes, so they get it as ordinary fields.

ERPNext has no distance-based interval anywhere, so `interval_km` and
`next_due_odometer` are added to Asset Maintenance Task alongside the standard
time-based `periodicity` and `next_due_date`.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from gdl_fleet_extension.setup.vehicle_fields import GDL_MODULE, upsert_property_setter

MAINTENANCE_CUSTOM_FIELDS = {
	"Asset Maintenance": [
		{
			"fieldname": "vehicle",
			"label": "Vehicle",
			"fieldtype": "Link",
			"options": "Vehicle",
			"insert_after": "asset_name",
			"in_standard_filter": 1,
		},
	],
	"Asset Maintenance Task": [
		{
			"fieldname": "service_item",
			"label": "Service Item",
			"fieldtype": "Link",
			"options": "Vehicle Service Item",
			"insert_after": "maintenance_task",
		},
		{
			"fieldname": "interval_km",
			"label": "Interval (KM)",
			"fieldtype": "Int",
			"insert_after": "periodicity",
			"description": "Distance between services. ERPNext periodicity covers time; "
			"this covers distance. Whichever falls due first wins.",
		},
		{
			"fieldname": "next_due_odometer",
			"label": "Next Due Odometer",
			"fieldtype": "Int",
			"insert_after": "next_due_date",
		},
		{
			"fieldname": "last_completion_odometer",
			"label": "Last Completion Odometer",
			"fieldtype": "Int",
			"insert_after": "last_completion_date",
		},
	],
	"Asset Maintenance Log": [
		{
			"fieldname": "vehicle",
			"label": "Vehicle",
			"fieldtype": "Link",
			"options": "Vehicle",
			"insert_after": "asset_name",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "odometer",
			"label": "Odometer",
			"fieldtype": "Int",
			"insert_after": "completion_date",
		},
		{
			# Puts Location beside Vehicle instead of under it - GDL: "same
			# line also". Two fields stacked in a half-width column left the
			# whole right side of the first section empty.
			"fieldname": "gdl_vehicle_cb",
			"fieldtype": "Column Break",
			"insert_after": "vehicle",
		},
		{
			# Bound to the vehicle and NOT editable - GDL: "and location not
			# editable". A fetch_from without fetch_if_empty is frappe's own
			# way of saying that: the value follows vehicle.site, and the
			# control goes read-only as soon as a vehicle is chosen
			# (read_only_because_of_fetch_from, base_input.js). It is also
			# re-asserted server-side on save, so it cannot drift.
			"fieldname": "location",
			"label": "Location",
			"fieldtype": "Link",
			"options": "Location",
			"insert_after": "gdl_vehicle_cb",
			"fetch_from": "vehicle.site",
			"description": "The vehicle's site. Follows the vehicle.",
		},
		{
			"fieldname": "service_provider",
			"label": "Service Provider",
			"fieldtype": "Link",
			"options": "Supplier",
			"insert_after": "odometer",
			"permlevel": 1,
		},
		{
			"fieldname": "labour_cost",
			"label": "Labour Cost",
			"fieldtype": "Currency",
			# Below the Service Items table, not above it. GDL: "need update below
			# this fields". Parts Cost is totalled FROM those rows, so reading
			# the rows and then their totals is the order the form is filled in.
			"insert_after": "gdl_cost_cb",
			"permlevel": 1,
		},
		{
			"fieldname": "parts_cost",
			"label": "Parts Cost",
			"fieldtype": "Currency",
			"insert_after": "labour_cost",
			"permlevel": 1,
		},
		{
			"fieldname": "total_cost",
			"label": "Total Cost",
			"fieldtype": "Currency",
			"read_only": 1,
			"insert_after": "parts_cost",
			"permlevel": 1,
		},
		{
			"fieldname": "service_items_section",
			"label": "Maintenance Items",
			"fieldtype": "Section Break",
			"insert_after": "service_provider",
		},
		{
			# The costs sit UNDER the table and on the RIGHT - GDL: "that field
			# need under service item table in right".
			#
			# Its own section, because a field cannot be moved out of its
			# section by insert_after alone: Meta.sort_fields keeps it where
			# its section puts it. The column break with nothing before it is
			# what pushes the costs to the right half; Column.refresh only
			# hides a column whose BREAK is hidden, never one that is merely
			# empty, so the empty left half renders and holds the space.
			"fieldname": "gdl_cost_section",
			"fieldtype": "Section Break",
			"insert_after": "service_items",
		},
		{
			# Two breaks, so Labour | Parts | Total sit side by side on ONE
			# line under the table rather than stacked down the page. GDL:
			# "need same line" and "form will more long need short".
			"fieldname": "gdl_cost_cb",
			"fieldtype": "Column Break",
			"insert_after": "labour_cost",
		},
		{
			"fieldname": "gdl_cost_cb2",
			"fieldtype": "Column Break",
			"insert_after": "parts_cost",
		},
		{
			"fieldname": "service_items",
			"label": "Maintenance Items",
			"fieldtype": "Table",
			"options": "Fleet Service Item",
			"insert_after": "service_items_section",
			"description": "Section 4.4: several maintenance items may be recorded "
			"against one visit. Parts Cost is totalled from these rows.",
		},
		{
			"fieldname": "cost_center",
			"label": "Cost Center",
			"fieldtype": "Link",
			"options": "Cost Center",
			"insert_after": "gdl_service_cb",
			"permlevel": 1,
		},
		{
			"fieldname": "project",
			"label": "Project",
			"fieldtype": "Link",
			"options": "Project",
			"insert_after": "cost_center",
			"permlevel": 1,
		},
		{
			"fieldname": "next_due_date",
			"label": "Next Service Date",
			"fieldtype": "Date",
			"read_only": 1,
			"insert_after": "project",
		},
		{
			"fieldname": "next_due_odometer",
			"label": "Next Service KM",
			"fieldtype": "Int",
			"read_only": 1,
			"insert_after": "next_due_date",
		},
	],
	# `vehicle`, `cost_center` and `project` are already on Asset Repair
	# (dimension + standard), so only the fleet-specific fields are added.
	"Asset Repair": [
		{
			"fieldname": "gdl_fleet_section",
			"label": "Fleet",
			"fieldtype": "Section Break",
			"insert_after": "asset_name",
		},
		{
			"fieldname": "maintenance_category",
			"label": "Maintenance Category",
			"fieldtype": "Select",
			"options": "Corrective\nPreventive\nAccident",
			"default": "Corrective",
			"insert_after": "gdl_fleet_section",
			"in_standard_filter": 1,
		},
		{
			"fieldname": "service_item",
			"label": "Service Type",
			"fieldtype": "Link",
			"options": "Vehicle Service Item",
			"insert_after": "maintenance_category",
		},
		{
			"fieldname": "location",
			"label": "Location",
			"fieldtype": "Link",
			"options": "Location",
			"description": "Site the vehicle was serviced at.",
		},
		{
			"fieldname": "service_provider",
			"label": "Service Provider",
			"fieldtype": "Link",
			"options": "Supplier",
			"insert_after": "service_item",
		},
		{
			"fieldname": "gdl_fleet_cb",
			"fieldtype": "Column Break",
			"insert_after": "service_provider",
		},
		{
			"fieldname": "odometer",
			"label": "Odometer",
			"fieldtype": "Int",
			"insert_after": "gdl_fleet_cb",
		},
		{
			"fieldname": "labour_cost",
			"label": "Labour Cost",
			"fieldtype": "Currency",
			"insert_after": "odometer",
		},
		{
			"fieldname": "next_service_date",
			"label": "Next Service Date",
			"fieldtype": "Date",
			"insert_after": "labour_cost",
		},
		{
			"fieldname": "next_service_odometer",
			"label": "Next Service KM",
			"fieldtype": "Int",
			"insert_after": "next_service_date",
		},
	],
}

MAINTENANCE_PROPERTY_SETTERS = [
	("Asset Maintenance Log", "completion_date", "label", "Service Date", "Data"),
	("Asset Repair", "failure_date", "label", "Repair / Failure Date", "Data"),
]


def setup_maintenance_customisations():
	fields = {
		doctype: [dict(df, module=GDL_MODULE) for df in dfs]
		for doctype, dfs in MAINTENANCE_CUSTOM_FIELDS.items()
	}
	create_custom_fields(fields, ignore_validate=True, update=True)

	enforce_field_order()

	for doctype, fieldname, prop, value, property_type in MAINTENANCE_PROPERTY_SETTERS:
		upsert_property_setter(doctype, fieldname, prop, value, property_type)

	for doctype in MAINTENANCE_CUSTOM_FIELDS:
		frappe.clear_cache(doctype=doctype)


# fieldname -> what it must sit after, applied AFTER every field exists.
#
# create_custom_fields saves each field in list order, so one pointing at a
# break defined further down the list is saved while that break does not yet
# exist and the value does not stick. Enforcing the chain afterwards is
# order-independent and idempotent.
FIELD_ORDER = {
	"Asset Maintenance Log": {
		"gdl_vehicle_cb": "vehicle",        # Location beside Vehicle, same line
		"location": "gdl_vehicle_cb",
		"cost_center": "gdl_service_cb",
		# The three costs on ONE line under the Service Items table:
		# section, then a field - break - field - break - field.
		"gdl_cost_section": "service_items",
		"labour_cost": "gdl_cost_section",
		"gdl_cost_cb": "labour_cost",
		"parts_cost": "gdl_cost_cb",
		"gdl_cost_cb2": "parts_cost",
		"total_cost": "gdl_cost_cb2",
	},
}


def enforce_field_order():
	for doctype, chain in FIELD_ORDER.items():
		changed = False
		for fieldname, after in chain.items():
			name = frappe.db.get_value(
				"Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
			if not name:
				continue
			if frappe.db.get_value("Custom Field", name, "insert_after") == after:
				continue
			frappe.db.set_value("Custom Field", name, "insert_after", after)
			changed = True
		if changed:
			frappe.clear_cache(doctype=doctype)
