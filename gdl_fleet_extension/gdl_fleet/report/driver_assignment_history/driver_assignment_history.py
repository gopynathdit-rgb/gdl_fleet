import frappe
from frappe import _

from gdl_fleet_extension.gdl_fleet.doctype.driver_assignment.driver_assignment import (
	get_assignment_history,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "name", "label": _("Assignment"), "fieldtype": "Link", "options": "Driver Assignment", "width": 150},
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 130},
		{"fieldname": "driver", "label": _("Driver"), "fieldtype": "Link", "options": "Driver", "width": 140},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 130},
		{"fieldname": "license_no", "label": _("License No."), "fieldtype": "Data", "width": 130},
		{"fieldname": "assignment_type", "label": _("Type"), "fieldtype": "Data", "width": 110},
		{"fieldname": "from_date", "label": _("From"), "fieldtype": "Date", "width": 100},
		{"fieldname": "to_date", "label": _("To"), "fieldtype": "Date", "width": 100},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "remarks", "label": _("Remarks"), "fieldtype": "Data", "width": 220},
	]
	data = get_assignment_history(
		vehicle=filters.get("vehicle"), driver=filters.get("driver"),
		from_date=filters.get("from_date"), to_date=filters.get("to_date"),
	)
	return columns, data
