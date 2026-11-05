import frappe
from frappe import _

from gdl_fleet_extension.gdl_fleet.doctype.movement_order.movement_order import (
	get_movement_register,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "name", "label": _("Movement Order"), "fieldtype": "Link", "options": "Movement Order", "width": 150},
		{"fieldname": "departure_datetime", "label": _("Departure"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "expected_return", "label": _("Expected Return"), "fieldtype": "Datetime", "width": 150},
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 130},
		{"fieldname": "driver", "label": _("Driver"), "fieldtype": "Link", "options": "Driver", "width": 140},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department", "width": 130},
		{"fieldname": "destination", "label": _("Destination"), "fieldtype": "Data", "width": 140},
		{"fieldname": "purpose", "label": _("Purpose"), "fieldtype": "Data", "width": 200},
		{"fieldname": "passenger_count", "label": _("Passengers"), "fieldtype": "Int", "width": 100},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
	]
	data = get_movement_register(
		from_date=filters.get("from_date"), to_date=filters.get("to_date"),
		vehicle=filters.get("vehicle"), driver=filters.get("driver"),
		department=filters.get("department"), status=filters.get("status"),
	)
	return columns, data
