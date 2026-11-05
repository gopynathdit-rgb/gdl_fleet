import frappe
from frappe import _
from frappe.utils import cint

from gdl_fleet_extension.utils.maintenance import get_due_maintenance


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 130},
		{"fieldname": "task", "label": _("Service"), "fieldtype": "Data", "width": 160},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "current_odometer", "label": _("Current KM"), "fieldtype": "Int", "width": 110},
		{"fieldname": "next_due_odometer", "label": _("Due at KM"), "fieldtype": "Int", "width": 110},
		{"fieldname": "km_remaining", "label": _("KM Remaining"), "fieldtype": "Int", "width": 120},
		{"fieldname": "next_due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "days_remaining", "label": _("Days Remaining"), "fieldtype": "Int", "width": 120},
		{"fieldname": "asset_maintenance", "label": _("Plan"), "fieldtype": "Link", "options": "Asset Maintenance", "width": 150},
	]
	data = get_due_maintenance(vehicle=filters.get("vehicle"))
	if cint(filters.get("overdue_only")):
		data = [d for d in data if d["status"] == "Overdue"]
	return columns, data
