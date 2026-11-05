# Copyright (c) 2026, GDL and contributors
"""
Mileage Deviation Dashboard.

Final document, Optimal Fleet Utilization: actual km/l against each vehicle's
minimum required mileage, with deviation beyond tolerance highlighted in BOTH
directions as GDL confirmed.
"""

import frappe
from frappe import _

from gdl_fleet_extension.utils.mileage_deviation import (
	ABOVE,
	BELOW,
	NOT_APPLICABLE,
	get_tolerance,
	get_vehicle_mileage,
)

INDICATOR = {
	BELOW: "red",
	ABOVE: "orange",
	"Within Tolerance": "green",
	NOT_APPLICABLE: "grey",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})

	columns = [
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 130},
		{"fieldname": "make", "label": _("Make"), "fieldtype": "Data", "width": 110},
		{"fieldname": "model", "label": _("Model"), "fieldtype": "Data", "width": 130},
		{"fieldname": "site", "label": _("Office / Site"), "fieldtype": "Link", "options": "Location", "width": 130},
		{"fieldname": "abstracts", "label": _("POL Abstracts"), "fieldtype": "Int", "width": 110},
		{"fieldname": "total_km", "label": _("Total KM"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "total_fuel_consumed", "label": _("Fuel Consumed (Ltr)"), "fieldtype": "Float", "precision": 3, "width": 150},
		{"fieldname": "actual_mileage", "label": _("Actual KM/L"), "fieldtype": "Float", "precision": 2, "width": 110},
		{"fieldname": "min_mileage", "label": _("Minimum KM/L"), "fieldtype": "Float", "precision": 2, "width": 120},
		{"fieldname": "deviation", "label": _("Deviation %"), "fieldtype": "Percent", "width": 110},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 150},
		{"fieldname": "hr_action", "label": _("HR Approval"), "fieldtype": "Data", "width": 120},
	]

	data = get_vehicle_mileage(
		from_date=filters.get("from_date"),
		to_date=filters.get("to_date"),
		vehicle=filters.get("vehicle"),
		site=filters.get("site"),
	)

	if filters.get("deviation_only"):
		data = [r for r in data if r["status"] in (BELOW, ABOVE)]

	for row in data:
		row["hr_action"] = _("Required") if row["hr_approval_required"] else ""
		row["indicator"] = INDICATOR.get(row["status"], "grey")

	tolerance = get_tolerance()
	flagged = sum(1 for r in data if r["hr_approval_required"])
	excluded = sum(1 for r in data if r["status"] == NOT_APPLICABLE)

	message = _(
		"Deviation is (Actual - Minimum) / Minimum. Tolerance is <b>&plusmn;{0}%</b> and "
		"applies in both directions: running well above target usually means a missed "
		"fill or a mis-keyed odometer, so it is flagged too. "
		"<b>{1}</b> vehicle(s) outside tolerance. "
		"<b>{2}</b> excluded because no minimum is set - an EV has no km/l target."
	).format(tolerance, flagged, excluded)

	chart = {
		"data": {
			"labels": [r["vehicle"] for r in data if r["actual_mileage"] is not None],
			"datasets": [
				{"name": _("Actual KM/L"),
				 "values": [r["actual_mileage"] for r in data if r["actual_mileage"] is not None]},
				{"name": _("Minimum KM/L"),
				 "values": [r["min_mileage"] or 0 for r in data if r["actual_mileage"] is not None]},
			],
		},
		"type": "bar",
	}

	return columns, data, message, chart
