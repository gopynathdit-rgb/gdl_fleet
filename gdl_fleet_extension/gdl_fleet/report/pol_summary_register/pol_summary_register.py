# Copyright (c) 2026, GDL and contributors
"""
POL Summary Register - Fleet Mgmt.docx section 5.

One row per POL Abstract, carrying the figures the customer's workbook
totals. Every derived number is read from the stored abstract rather than
recomputed, so the register always agrees with the approved document.
"""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})

	columns = [
		{"fieldname": "name", "label": _("POL Abstract"), "fieldtype": "Link", "options": "POL Abstract", "width": 150},
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 130},
		{"fieldname": "driver", "label": _("Driver"), "fieldtype": "Link", "options": "Driver", "width": 120},
		{"fieldname": "period_from", "label": _("From"), "fieldtype": "Date", "width": 100},
		{"fieldname": "period_to", "label": _("To"), "fieldtype": "Date", "width": 100},
		{"fieldname": "basis", "label": _("Basis"), "fieldtype": "Data", "width": 70},
		{"fieldname": "opening_km", "label": _("Opening"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "closing_km", "label": _("Closing"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "total_km", "label": _("Total KM"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "total_fuel_supplied", "label": _("Supplied (Ltr)"), "fieldtype": "Float", "precision": 3, "width": 110},
		{"fieldname": "previous_tank_balance", "label": _("Prev. Tank"), "fieldtype": "Float", "precision": 3, "width": 100},
		{"fieldname": "present_tank_balance", "label": _("Present Tank"), "fieldtype": "Float", "precision": 3, "width": 110},
		{"fieldname": "total_fuel_consumed", "label": _("Consumed (Ltr)"), "fieldtype": "Float", "precision": 3, "width": 120},
		{"fieldname": "performance_per_litre", "label": _("KM/L"), "fieldtype": "Float", "precision": 2, "width": 90},
		{"fieldname": "total_amount_stcbl", "label": _("Amount (STCBL)"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "total_amount_bod", "label": _("Amount (BOD)"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "fuel_book_balance_stcbl", "label": _("Book Bal. (STCBL)"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "fuel_book_balance_bod", "label": _("Book Bal. (BOD)"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 100},
	]

	conditions = {"docstatus": ("<", 2)}
	if filters.get("vehicle"):
		conditions["vehicle"] = filters.vehicle
	if filters.get("driver"):
		conditions["driver"] = filters.driver
	if filters.get("site"):
		conditions["site"] = filters.site
	if filters.get("status"):
		conditions["status"] = filters.status
	if filters.get("from_date"):
		conditions["period_to"] = (">=", filters.from_date)
	if filters.get("to_date"):
		conditions["period_from"] = ("<=", filters.to_date)

	rows = frappe.get_all(
		"POL Abstract",
		filters=conditions,
		fields=[
			"name", "vehicle", "driver", "period_from", "period_to", "distance_basis",
			"opening_km", "closing_km", "total_km", "total_fuel_supplied",
			"previous_tank_balance", "present_tank_balance", "total_fuel_consumed",
			"performance_per_litre", "total_amount_bod", "total_amount_stcbl",
			"fuel_book_balance_bod", "fuel_book_balance_stcbl", "status",
		],
		order_by="vehicle asc, period_from asc",
	)

	for row in rows:
		row["basis"] = row.pop("distance_basis", None)

	message = _(
		"Performance is Total KM divided by Total Fuel <b>Consumed</b> "
		"(supplied + previous tank balance - present tank balance), as in the "
		"POL workbook. It is left blank where consumption is not positive."
	)
	return columns, rows, message
