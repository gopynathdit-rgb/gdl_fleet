import frappe
from frappe import _
from frappe.utils import now_datetime


def execute(filters=None):
	"""Section 5: available, booked, under maintenance or unavailable.

	Section 4.1 stores only Active / Under Maintenance / Unavailable / Disposed,
	so "booked" is derived here from the vehicle's Movement Orders rather than
	held as a status of its own.
	"""
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "name", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 140},
		{"fieldname": "vehicle_type", "label": _("Type"), "fieldtype": "Link", "options": "Fleet Vehicle Type", "width": 130},
		{"fieldname": "site", "label": _("Site"), "fieldtype": "Link", "options": "Location", "width": 130},
		{"fieldname": "assigned_driver", "label": _("Driver"), "fieldtype": "Link", "options": "Driver", "width": 140},
		{"fieldname": "vehicle_status", "label": _("Vehicle Status"), "fieldtype": "Data", "width": 140},
		{"fieldname": "availability", "label": _("Availability"), "fieldtype": "Data", "width": 130},
		{"fieldname": "movement_order", "label": _("On Movement Order"), "fieldtype": "Link", "options": "Movement Order", "width": 160},
		{"fieldname": "busy_until", "label": _("Expected Return"), "fieldtype": "Datetime", "width": 150},
	]

	from gdl_fleet_extension.gdl_fleet.doctype.driver_assignment.driver_assignment import (
		get_active_driver,
	)

	conditions = {}
	if filters.get("vehicle"):
		conditions["name"] = filters.vehicle
	if filters.get("site"):
		conditions["site"] = filters.site

	as_at = filters.get("as_at") or now_datetime()
	data = []
	for row in frappe.get_all(
		"Vehicle", filters=conditions,
		fields=["name", "vehicle_type", "site", "vehicle_status"],
		order_by="name asc",
	):
		row["assigned_driver"] = get_active_driver(row["name"])
		row["movement_order"] = None
		row["busy_until"] = None

		if row["vehicle_status"] != "Active":
			row["availability"] = row["vehicle_status"]
		else:
			booked = frappe.db.sql(
				"""
				select name, expected_return
				from `tabMovement Order`
				where vehicle = %(vehicle)s and docstatus < 2
				  and status in ('Approved', 'Dispatched')
				  and departure_datetime <= %(as_at)s
				  and coalesce(expected_return, departure_datetime) >= %(as_at)s
				limit 1
				""",
				{"vehicle": row["name"], "as_at": as_at}, as_dict=True,
			)
			if booked:
				row["availability"] = "Booked"
				row["movement_order"] = booked[0].name
				row["busy_until"] = booked[0].expected_return
			else:
				row["availability"] = "Available"
		data.append(row)

	if filters.get("availability"):
		data = [r for r in data if r["availability"] == filters.availability]
	return columns, data
