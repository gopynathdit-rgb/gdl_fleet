import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 130},
		{"fieldname": "reference", "label": _("Document"), "fieldtype": "Dynamic Link", "options": "doctype", "width": 160},
		{"fieldname": "doctype", "label": _("Type"), "fieldtype": "Data", "width": 150},
		{"fieldname": "category", "label": _("Category"), "fieldtype": "Data", "width": 110},
		{"fieldname": "service_items", "label": _("Service Items"), "fieldtype": "Data", "width": 240},
		{"fieldname": "service_date", "label": _("Service Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "odometer", "label": _("Odometer"), "fieldtype": "Int", "width": 100},
		{"fieldname": "service_provider", "label": _("Provider"), "fieldtype": "Link", "options": "Supplier", "width": 140},
		{"fieldname": "labour_cost", "label": _("Labour"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "parts_cost", "label": _("Parts"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "total_cost", "label": _("Total"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "downtime", "label": _("Downtime"), "fieldtype": "Data", "width": 100},
	]

	conditions = {"docstatus": 1}
	if filters.get("vehicle"):
		conditions["vehicle"] = filters.vehicle
	if filters.get("from_date") and filters.get("to_date"):
		conditions["failure_date"] = ("between", [filters.from_date, filters.to_date])

	data = []
	for row in frappe.get_all(
		"Asset Repair",
		filters=conditions,
		fields=["name", "vehicle", "maintenance_category", "failure_date", "odometer",
		        "service_provider", "labour_cost", "consumed_items_cost",
		        "total_repair_cost", "downtime", "service_item"],
	):
		data.append({
			"vehicle": row.vehicle, "reference": row.name, "doctype": "Asset Repair",
			"category": row.maintenance_category or "Corrective",
			"service_items": row.service_item,
			"service_date": row.failure_date, "odometer": row.odometer,
			"service_provider": row.service_provider,
			"labour_cost": flt(row.labour_cost),
			"parts_cost": flt(row.consumed_items_cost),
			"total_cost": flt(row.total_repair_cost), "downtime": row.downtime,
		})

	log_conditions = {"docstatus": 1}
	if filters.get("vehicle"):
		log_conditions["vehicle"] = filters.vehicle
	if filters.get("from_date") and filters.get("to_date"):
		log_conditions["completion_date"] = ("between", [filters.from_date, filters.to_date])

	logs = frappe.get_all(
		"Asset Maintenance Log",
		filters=log_conditions,
		fields=["name", "vehicle", "completion_date", "odometer", "service_provider",
		        "labour_cost", "parts_cost", "total_cost"],
	)

	# Section 4.4 wants the maintenance items visible on the history line, and a
	# single visit can carry several of them.
	items_by_log = {}
	if logs:
		for item in frappe.get_all(
			"Fleet Service Item",
			filters={"parenttype": "Asset Maintenance Log", "parent": ("in", [l.name for l in logs])},
			fields=["parent", "service_item"],
			order_by="idx",
		):
			items_by_log.setdefault(item.parent, []).append(item.service_item)

	for row in logs:
		data.append({
			"service_items": ", ".join(items_by_log.get(row.name, [])) or None,
			"vehicle": row.vehicle, "reference": row.name,
			"doctype": "Asset Maintenance Log", "category": "Preventive",
			"service_date": row.completion_date, "odometer": row.odometer,
			"service_provider": row.service_provider,
			"labour_cost": flt(row.labour_cost), "parts_cost": flt(row.parts_cost),
			"total_cost": flt(row.total_cost), "downtime": None,
		})

	# Asset Repair dates with a Datetime and Asset Maintenance Log with a Date,
	# so they are normalised to a string before sorting.
	data.sort(key=lambda r: (r["vehicle"] or "", str(r["service_date"] or "")))
	return columns, data
