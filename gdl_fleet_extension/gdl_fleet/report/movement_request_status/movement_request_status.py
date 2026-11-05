import frappe
from frappe import _
from frappe.utils import flt, time_diff_in_hours


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "name", "label": _("Request"), "fieldtype": "Link", "options": "Movement Order Request", "width": 150},
		{"fieldname": "request_date", "label": _("Requested"), "fieldtype": "Date", "width": 100},
		{"fieldname": "requester", "label": _("Requested By"), "fieldtype": "Link", "options": "User", "width": 150},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Link", "options": "Department", "width": 130},
		{"fieldname": "required_date", "label": _("Travel Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "destination", "label": _("Destination"), "fieldtype": "Data", "width": 140},
		{"fieldname": "vehicle_type", "label": _("Type Required"), "fieldtype": "Link", "options": "Fleet Vehicle Type", "width": 130},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "turnaround_hours", "label": _("Turnaround (Hrs)"), "fieldtype": "Float", "precision": 1, "width": 130},
		{"fieldname": "movement_order", "label": _("Movement Order"), "fieldtype": "Link", "options": "Movement Order", "width": 150},
	]

	conditions = {"docstatus": ("<", 2)}
	if filters.get("vehicle"):
		conditions["vehicle"] = filters.vehicle
	if filters.get("department"):
		conditions["department"] = filters.department
	if filters.get("status"):
		conditions["status"] = filters.status
	if filters.get("from_date") and filters.get("to_date"):
		conditions["request_date"] = ("between", [filters.from_date, filters.to_date])

	data = frappe.get_all(
		"Movement Order Request", filters=conditions,
		fields=["name", "request_date", "requester", "department", "required_date",
		        "destination", "vehicle_type", "status", "creation", "modified"],
		order_by="request_date desc",
	)
	for row in data:
		row["turnaround_hours"] = (
			flt(time_diff_in_hours(row["modified"], row["creation"]), 1)
			if row["status"] in ("Accepted", "Rejected") else None
		)
		row["movement_order"] = frappe.db.get_value(
			"Movement Order", {"movement_order_request": row["name"], "docstatus": ("<", 2)}, "name"
		)
	return columns, data
