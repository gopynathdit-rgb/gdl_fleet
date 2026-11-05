# Copyright (c) 2026, GDL and contributors
"""
Tyre Cost Analysis - Business Blueprint, Tire Lifecycle Management:
"Tire Cost Analysis".

The Tyre Mileage Report answers "did this tyre reach 20,000 km". This one
answers the money question behind it: what the fleet spent on tyres, and what
each kilometre of tyre life actually costs.

Cost per km is the only figure that compares a cheap tyre that lasts 12,000 km
against an expensive one that lasts 30,000 km, so it is what this groups by.
A tyre still on the vehicle is included at the distance it has run so far,
flagged as such, because excluding it would overstate the fleet average.
"""

import frappe
from frappe import _

from gdl_fleet_extension.utils.tyre import (
	ABOVE,
	BELOW,
	IN_SERVICE,
	cost_per_km,
	get_tyre_performance,
	get_tyre_target,
)

GROUP_BY = {
	"Vehicle": "vehicle",
	"Tyre Item": "item_code",
	"Site": "site",
	"Removal Reason": "removal_reason",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	group_field = GROUP_BY.get(filters.get("group_by") or "Vehicle", "vehicle")

	rows = get_tyre_performance(
		from_date=filters.get("from_date"),
		to_date=filters.get("to_date"),
		vehicle=filters.get("vehicle"),
		status=filters.get("status"),
	)
	rows = add_sites(rows)

	if filters.get("site"):
		rows = [r for r in rows if r.get("site") == filters.site]
	if not filters.get("include_in_service"):
		rows = [r for r in rows if r["performance"] != IN_SERVICE]
	rows = [r for r in rows if (r.get("cost") or 0) > 0]

	data = summarise(rows, group_field)
	columns = get_columns(group_field)
	message = get_message(rows, filters)
	chart = get_chart(data, group_field)
	return columns, data, message, chart


def add_sites(rows):
	"""One lookup for every vehicle on the report rather than one per tyre."""
	vehicles = {r["vehicle"] for r in rows if r.get("vehicle")}
	sites = {}
	if vehicles:
		sites = {
			v.name: v.site
			for v in frappe.get_all(
				"Vehicle", filters={"name": ("in", list(vehicles))}, fields=["name", "site"]
			)
		}
	for row in rows:
		row["site"] = sites.get(row.get("vehicle"))
	return rows


def summarise(rows, group_field):
	buckets = {}
	for row in rows:
		key = row.get(group_field) or _("Not Set")
		bucket = buckets.setdefault(
			key,
			{
				group_field: key,
				"tyres": 0,
				"in_service": 0,
				"total_cost": 0.0,
				"total_km": 0,
				"below": 0,
				"above": 0,
			},
		)
		bucket["tyres"] += 1
		bucket["total_cost"] += float(row.get("cost") or 0)
		bucket["total_km"] += int(row.get("km_so_far") or 0)
		if row["performance"] == IN_SERVICE:
			bucket["in_service"] += 1
		elif row["performance"] == BELOW:
			bucket["below"] += 1
		elif row["performance"] == ABOVE:
			bucket["above"] += 1

	data = []
	for bucket in buckets.values():
		bucket["avg_cost"] = bucket["total_cost"] / bucket["tyres"] if bucket["tyres"] else 0
		bucket["avg_km"] = bucket["total_km"] / bucket["tyres"] if bucket["tyres"] else 0
		bucket["cost_per_km"] = cost_per_km(bucket["total_cost"], bucket["total_km"])
		data.append(bucket)

	# Worst value first - that is the row a fleet manager acts on.
	data.sort(key=lambda r: (r["cost_per_km"] is None, -(r["cost_per_km"] or 0)))
	return data


def get_columns(group_field):
	label, fieldtype, options = {
		"vehicle": (_("Vehicle"), "Link", "Vehicle"),
		"item_code": (_("Tyre Item"), "Link", "Item"),
		"site": (_("Site"), "Link", "Location"),
		"removal_reason": (_("Removal Reason"), "Data", None),
	}[group_field]

	return [
		{"fieldname": group_field, "label": label, "fieldtype": fieldtype,
		 "options": options, "width": 190},
		{"fieldname": "tyres", "label": _("Tyres"), "fieldtype": "Int", "width": 80},
		{"fieldname": "in_service", "label": _("Still Fitted"), "fieldtype": "Int", "width": 100},
		{"fieldname": "total_cost", "label": _("Total Cost"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "avg_cost", "label": _("Avg Cost / Tyre"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "total_km", "label": _("Total KM"), "fieldtype": "Int", "width": 110},
		{"fieldname": "avg_km", "label": _("Avg KM / Tyre"), "fieldtype": "Float",
		 "precision": 0, "width": 130},
		{"fieldname": "cost_per_km", "label": _("Cost / KM"), "fieldtype": "Currency",
		 "precision": 4, "width": 110},
		{"fieldname": "below", "label": _("Below Band"), "fieldtype": "Int", "width": 110},
		{"fieldname": "above", "label": _("Above Band"), "fieldtype": "Int", "width": 110},
	]


def get_message(rows, filters):
	if not rows:
		return _(
			"No tyre on this filter carries a cost. A tyre picks its cost up from the "
			"Fleet Part Issue that fitted it; one recorded by hand needs the Cost "
			"entered on the tyre itself."
		)

	spend = sum(float(r.get("cost") or 0) for r in rows)
	km = sum(int(r.get("km_so_far") or 0) for r in rows)
	fleet_rate = cost_per_km(spend, km)
	still_fitted = sum(1 for r in rows if r["performance"] == IN_SERVICE)

	parts = [
		_(
			"<b>{0}</b> tyre(s) costing <b>{1:,.2f}</b> in total have run <b>{2:,} km</b>, "
			"a fleet average of <b>{3}</b> per kilometre."
		).format(len(rows), spend, km, f"{fleet_rate:,.4f}" if fleet_rate else _("n/a"))
	]
	if still_fitted:
		parts.append(
			_(
				"<b>{0}</b> of these are still fitted, so their cost per km will fall "
				"further before they come off."
			).format(still_fitted)
		)
	parts.append(
		_("A tyre meeting the <b>{0:,} km</b> target sets the benchmark each row is read against.")
		.format(get_tyre_target())
	)
	return " ".join(parts)


def get_chart(data, group_field):
	top = [r for r in data if r.get("cost_per_km")][:12]
	if not top:
		return None
	return {
		"data": {
			"labels": [str(r[group_field]) for r in top],
			"datasets": [{"name": _("Cost / KM"), "values": [r["cost_per_km"] for r in top]}],
		},
		"type": "bar",
	}
