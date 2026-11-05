# Copyright (c) 2026, GDL and contributors
"""
Fuel Consumption and Performance - Fleet Mgmt.docx section 5.

Primary source is the approved POL Abstract, so the figures here are the ones
GDL signed off rather than a parallel calculation:

    Performance = Total KM / Total Fuel CONSUMED

where consumed is supplied + previous tank balance - present tank balance.

Fuel quantity comes from the POL entries themselves, which is what the final
requirements document specifies: "Calculate fuel efficiency based on mileage and
fuel quantity."
"""

import frappe
from frappe import _

from gdl_fleet_extension.utils.pol import performance_per_litre, to_decimal


def execute(filters=None):
	filters = frappe._dict(filters or {})

	columns = [
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 130},
		{"fieldname": "abstracts", "label": _("POL Abstracts"), "fieldtype": "Int", "width": 110},
		{"fieldname": "total_km", "label": _("Total KM"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "total_fuel_supplied", "label": _("Fuel Supplied (Ltr)"), "fieldtype": "Float", "precision": 3, "width": 140},
		{"fieldname": "previous_tank_balance", "label": _("Previous Tank"), "fieldtype": "Float", "precision": 3, "width": 120},
		{"fieldname": "present_tank_balance", "label": _("Present Tank"), "fieldtype": "Float", "precision": 3, "width": 120},
		{"fieldname": "total_fuel_consumed", "label": _("Fuel Consumed (Ltr)"), "fieldtype": "Float", "precision": 3, "width": 150},
		{"fieldname": "performance", "label": _("Performance KM/L"), "fieldtype": "Float", "precision": 2, "width": 140},
		{"fieldname": "total_amount_stcbl", "label": _("Amount (STCBL)"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 260},
	]

	data = get_pol_performance(
		from_date=filters.get("from_date"),
		to_date=filters.get("to_date"),
		vehicle=filters.get("vehicle"),
	)

	message = _(
		"Performance is Total KM / Total Fuel <b>Consumed</b> "
		"(supplied + previous tank balance - present tank balance), taken from "
		"approved POL Abstracts."
	)
	return columns, data, message


def get_pol_performance(from_date=None, to_date=None, vehicle=None):
	"""Roll POL abstracts up per vehicle for the period.

	Totals are summed across abstracts and performance is recomputed from those
	totals. Averaging each abstract's KM/L would weight a short period the same
	as a long one.
	"""
	filters = {"docstatus": 1}
	if vehicle:
		filters["vehicle"] = vehicle
	if from_date:
		filters["period_to"] = (">=", from_date)
	if to_date:
		filters["period_from"] = ("<=", to_date)

	abstracts = frappe.get_all(
		"POL Abstract",
		filters=filters,
		fields=["vehicle", "total_km", "total_fuel_supplied", "previous_tank_balance",
		        "present_tank_balance", "total_fuel_consumed", "total_amount_stcbl"],
		order_by="vehicle asc, period_from asc",
	)

	rolled = {}
	for row in abstracts:
		bucket = rolled.setdefault(row.vehicle, {
			"vehicle": row.vehicle, "abstracts": 0, "total_km": 0.0,
			"total_fuel_supplied": 0.0, "previous_tank_balance": 0.0,
			"present_tank_balance": 0.0, "total_fuel_consumed": 0.0,
			"total_amount_stcbl": 0.0,
		})
		bucket["abstracts"] += 1
		for field in ("total_km", "total_fuel_supplied", "total_fuel_consumed", "total_amount_stcbl"):
			bucket[field] += row.get(field) or 0

		# Opening balance of the period is the first abstract's; closing is the last.
		if bucket["abstracts"] == 1:
			bucket["previous_tank_balance"] = row.previous_tank_balance or 0
		bucket["present_tank_balance"] = row.present_tank_balance or 0

	data = []
	for bucket in rolled.values():
		performance = performance_per_litre(
			bucket["total_km"], bucket["total_fuel_consumed"], precision=None
		)
		bucket["performance"] = float(performance) if performance is not None else None

		if performance is None:
			bucket["note"] = _("Fuel consumed is not positive - performance cannot be calculated.")
		elif to_decimal(bucket["total_km"]) <= 0:
			bucket["note"] = _("No distance recorded on the approved abstracts.")
		else:
			bucket["note"] = None
		data.append(bucket)

	data.sort(key=lambda r: r["vehicle"] or "")
	return data
