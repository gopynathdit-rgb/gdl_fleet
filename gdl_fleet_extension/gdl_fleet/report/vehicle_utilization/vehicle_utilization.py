import frappe
from frappe import _

from gdl_fleet_extension.utils.mileage import get_utilization


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 130},
		{"fieldname": "gdl_vehicle_id", "label": _("Vehicle ID"), "fieldtype": "Data", "width": 120},
		{"fieldname": "vehicle_type", "label": _("Type"), "fieldtype": "Link", "options": "Fleet Vehicle Type", "width": 110},
		{"fieldname": "site", "label": _("Site"), "fieldtype": "Link", "options": "Location", "width": 120},
		{"fieldname": "driver", "label": _("Driver"), "fieldtype": "Link", "options": "Driver", "width": 120},
		{"fieldname": "period_days", "label": _("Period Days"), "fieldtype": "Int", "width": 100},
		{"fieldname": "days_used", "label": _("Days Used"), "fieldtype": "Int", "width": 100},
		{"fieldname": "utilization_pct", "label": _("Utilization %"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "actual_km", "label": _("Actual KM"), "fieldtype": "Int", "width": 100},
		{"fieldname": "km_per_day", "label": _("KM / Day"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "idle_days", "label": _("Idle Days"), "fieldtype": "Int", "width": 90},
	]
	data = get_utilization(
		filters.get("from_date"), filters.get("to_date"), vehicle=filters.get("vehicle"),
		site=filters.get("site"), department=filters.get("department"),
		driver=filters.get("driver"), project=filters.get("project"),
	)
	return columns, data
