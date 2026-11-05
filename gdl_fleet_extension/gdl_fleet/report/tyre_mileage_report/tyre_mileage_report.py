# Copyright (c) 2026, GDL and contributors
"""
Tyre Mileage Report - actual distance achieved against the 20,000 km +/-20%
target in the final requirements document.
"""

import frappe
from frappe import _

from gdl_fleet_extension.utils.tyre import (
	ABOVE,
	BELOW,
	IN_SERVICE,
	get_tyre_performance,
	get_tyre_target,
	get_tyre_tolerance,
	tyre_bounds,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})

	columns = [
		{"fieldname": "name", "label": _("Tyre"), "fieldtype": "Link", "options": "Vehicle Tyre", "width": 130},
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 120},
		{"fieldname": "item_code", "label": _("Tyre Item"), "fieldtype": "Link", "options": "Item", "width": 150},
		{"fieldname": "serial_no", "label": _("Serial No"), "fieldtype": "Data", "width": 120},
		{"fieldname": "tyre_position", "label": _("Position"), "fieldtype": "Data", "width": 110},
		{"fieldname": "fitted_date", "label": _("Fitted"), "fieldtype": "Date", "width": 100},
		{"fieldname": "fitted_odometer", "label": _("Fitted KM"), "fieldtype": "Int", "width": 100},
		{"fieldname": "removed_date", "label": _("Removed"), "fieldtype": "Date", "width": 100},
		{"fieldname": "removed_odometer", "label": _("Removed KM"), "fieldtype": "Int", "width": 110},
		{"fieldname": "km_so_far", "label": _("KM Achieved"), "fieldtype": "Int", "width": 110},
		{"fieldname": "target_km", "label": _("Target KM"), "fieldtype": "Int", "width": 100},
		{"fieldname": "deviation", "label": _("Deviation %"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "cost", "label": _("Cost"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "cost_per_km", "label": _("Cost / KM"), "fieldtype": "Currency",
		 "precision": 4, "width": 110},
		{"fieldname": "performance", "label": _("Performance"), "fieldtype": "Data", "width": 140},
		{"fieldname": "removal_reason", "label": _("Removal Reason"), "fieldtype": "Data", "width": 130},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
	]

	data = get_tyre_performance(
		from_date=filters.get("from_date"),
		to_date=filters.get("to_date"),
		vehicle=filters.get("vehicle"),
		status=filters.get("status"),
	)

	if filters.get("outside_tolerance_only"):
		data = [r for r in data if r["performance"] in (BELOW, ABOVE)]

	target = get_tyre_target()
	low, high = tyre_bounds()
	removed = [r for r in data if r["performance"] != IN_SERVICE]
	under = sum(1 for r in removed if r["performance"] == BELOW)
	over = sum(1 for r in removed if r["performance"] == ABOVE)
	avg = (sum(r["km_so_far"] for r in removed) / len(removed)) if removed else 0

	message = _(
		"Target <b>{0:,} km</b> with a tolerance of <b>&plusmn;{1}%</b>, so an acceptable "
		"tyre runs between <b>{2:,.0f}</b> and <b>{3:,.0f} km</b>. "
		"Of <b>{4}</b> removed tyre(s), <b>{5}</b> fell short and <b>{6}</b> exceeded the band; "
		"average achieved <b>{7:,.0f} km</b>. "
		"A tyre well above the band usually means the removal reading was missed."
	).format(target, get_tyre_tolerance(), low, high, len(removed), under, over, avg)

	chart = {
		"data": {
			"labels": [r["name"] for r in removed],
			"datasets": [
				{"name": _("KM Achieved"), "values": [r["km_so_far"] for r in removed]},
				{"name": _("Target"), "values": [target for _r in removed]},
			],
		},
		"type": "bar",
	}
	return columns, data, message, chart
