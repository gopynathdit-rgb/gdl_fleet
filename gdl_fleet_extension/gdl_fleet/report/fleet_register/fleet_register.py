import frappe
from frappe import _

from gdl_fleet_extension.gdl_fleet.doctype.driver_assignment.driver_assignment import (
	get_active_driver,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "name", "label": _("Registration No."), "fieldtype": "Link", "options": "Vehicle", "width": 140},
		{"fieldname": "make", "label": _("Make"), "fieldtype": "Data", "width": 110},
		{"fieldname": "model", "label": _("Model"), "fieldtype": "Data", "width": 120},
		{"fieldname": "vehicle_type", "label": _("Type"), "fieldtype": "Link", "options": "Fleet Vehicle Type", "width": 120},
		{"fieldname": "capacity", "label": _("Capacity"), "fieldtype": "Int", "width": 90},
		{"fieldname": "capacity_uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 80},
		{"fieldname": "engine_no", "label": _("Engine No."), "fieldtype": "Data", "width": 120},
		{"fieldname": "chassis_no", "label": _("Chassis No."), "fieldtype": "Data", "width": 130},
		{"fieldname": "fuel_type", "label": _("Fuel"), "fieldtype": "Data", "width": 90},
		{"fieldname": "acquisition_date", "label": _("Acquired"), "fieldtype": "Date", "width": 100},
		{"fieldname": "last_odometer", "label": _("Current Odometer"), "fieldtype": "Int", "width": 130},
		{"fieldname": "assigned_driver", "label": _("Assigned Driver"), "fieldtype": "Link", "options": "Driver", "width": 140},
		{"fieldname": "site", "label": _("Site"), "fieldtype": "Link", "options": "Location", "width": 120},
		{"fieldname": "vehicle_status", "label": _("Status"), "fieldtype": "Data", "width": 130},
	]

	conditions = {}
	if filters.get("vehicle"):
		conditions["name"] = filters.vehicle
	if filters.get("site"):
		conditions["site"] = filters.site

	data = frappe.get_all(
		"Vehicle", filters=conditions,
		fields=["name", "make", "model", "vehicle_type", "capacity", "capacity_uom",
		        "engine_no", "chassis_no", "fuel_type", "acquisition_date",
		        "last_odometer", "site", "vehicle_status"],
		order_by="name asc",
	)
	for row in data:
		row["assigned_driver"] = get_active_driver(row["name"])
	if filters.get("driver"):
		data = [r for r in data if r["assigned_driver"] == filters.driver]
	return columns, data
