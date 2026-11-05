# Copyright (c) 2026, GDL and contributors
"""
Part Replacement History - Business Blueprint, Spare Parts Management:
"Replacement History".

Parts Consumption answers "what did we spend". This answers "how long did it
last": for each vehicle and part, every time that part was fitted, and the
distance and days since the one before it.

The interval is what makes the report worth reading. A brake pad replaced
every 9,000 km on one vehicle and every 30,000 km on another is either a
driving problem or a parts-quality problem, and neither shows up in a spend
total.
"""

import frappe
from frappe import _

from gdl_fleet_extension.utils.parts import build_replacement_history, get_issued_parts


def execute(filters=None):
	filters = frappe._dict(filters or {})

	rows = get_issued_parts(
		from_date=filters.get("from_date"),
		to_date=filters.get("to_date"),
		vehicle=filters.get("vehicle"),
		item_code=filters.get("item_code"),
		site=filters.get("site"),
		tyres_only=bool(filters.get("tyres_only")),
		exclude_tyres=bool(filters.get("exclude_tyres")),
	)
	data = build_replacement_history(rows)

	if filters.get("repeated_only"):
		data = [r for r in data if r["replacements"] > 1]

	below = int(filters.get("replaced_within_km") or 0)
	if below:
		data = [
			r for r in data
			if r["km_since_previous"] is not None and r["km_since_previous"] < below
		]

	return get_columns(), data, summary(data, below), None


def get_columns():
	return [
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link",
		 "options": "Vehicle", "width": 120},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link",
		 "options": "Item", "width": 150},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 170},
		{"fieldname": "sequence", "label": _("#"), "fieldtype": "Int", "width": 60},
		{"fieldname": "replacements", "label": _("Times Fitted"), "fieldtype": "Int", "width": 110},
		{"fieldname": "issue_date", "label": _("Fitted On"), "fieldtype": "Date", "width": 100},
		{"fieldname": "odometer", "label": _("Odometer"), "fieldtype": "Int", "width": 100},
		{"fieldname": "km_since_previous", "label": _("KM Since Previous"),
		 "fieldtype": "Int", "width": 150},
		{"fieldname": "days_since_previous", "label": _("Days Since Previous"),
		 "fieldtype": "Int", "width": 150},
		{"fieldname": "serial_no", "label": _("Serial No"), "fieldtype": "Data", "width": 130},
		{"fieldname": "tyre_position", "label": _("Position"), "fieldtype": "Data", "width": 110},
		{"fieldname": "purpose", "label": _("Purpose"), "fieldtype": "Data", "width": 140},
		{"fieldname": "amount", "label": _("Cost"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "issue", "label": _("Issue"), "fieldtype": "Link",
		 "options": "Fleet Part Issue", "width": 140},
		{"fieldname": "previous_issue", "label": _("Previous Issue"), "fieldtype": "Link",
		 "options": "Fleet Part Issue", "width": 140},
	]


def summary(data, below):
	if not data:
		return _(
			"Nothing to show. A part appears here once it has been issued to a "
			"vehicle on a submitted Fleet Part Issue."
		)

	repeats = [r for r in data if r["km_since_previous"] is not None]
	parts = [
		_("<b>{0}</b> fitting(s) across <b>{1}</b> vehicle/part combination(s).").format(
			len(data), len({(r["vehicle"], r["item_code"]) for r in data})
		)
	]

	if repeats:
		intervals = [r["km_since_previous"] for r in repeats]
		parts.append(
			_(
				"Of the <b>{0}</b> that replaced an earlier part, the shortest ran "
				"<b>{1:,} km</b>, the longest <b>{2:,} km</b>, and the average was "
				"<b>{3:,.0f} km</b>."
			).format(len(repeats), min(intervals), max(intervals), sum(intervals) / len(intervals))
		)
	else:
		parts.append(
			_(
				"None of these replaced an earlier part yet, so no interval can be "
				"measured - the history starts building from the second fitting."
			)
		)

	if below:
		parts.append(
			_("Filtered to parts replaced within <b>{0:,} km</b> of the previous one.").format(below)
		)

	return " ".join(parts)
