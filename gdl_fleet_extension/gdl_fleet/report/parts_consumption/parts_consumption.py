# Copyright (c) 2026, GDL and contributors
"""
Parts Consumption - Business Blueprint, Spare Parts Management:
"Parts Consumption".

What the fleet took out of store over a period, and what it cost. Groups the
same issue trail several ways because the question differs by reader: stores
asks which item moves, the fleet manager asks which vehicle consumes, finance
asks which site spends.
"""

import frappe
from frappe import _

from gdl_fleet_extension.utils.parts import get_issued_parts

GROUP_BY = {
	"Item": ("item_code", _("Item"), "Link", "Item"),
	"Vehicle": ("vehicle", _("Vehicle"), "Link", "Vehicle"),
	"Site": ("site", _("Site"), "Link", "Location"),
	"Purpose": ("purpose", _("Purpose"), "Data", None),
	"Detail": (None, None, None, None),
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	group_by = filters.get("group_by") or "Item"

	rows = get_issued_parts(
		from_date=filters.get("from_date"),
		to_date=filters.get("to_date"),
		vehicle=filters.get("vehicle"),
		item_code=filters.get("item_code"),
		site=filters.get("site"),
		purpose=filters.get("purpose"),
		tyres_only=bool(filters.get("tyres_only")),
		exclude_tyres=bool(filters.get("exclude_tyres")),
	)

	if group_by == "Detail":
		return detail_columns(), rows, summary(rows), None

	field, label, fieldtype, options = GROUP_BY[group_by]
	data = summarise(rows, field)
	return (
		grouped_columns(field, label, fieldtype, options),
		data,
		summary(rows),
		chart(data, field),
	)


def summarise(rows, field):
	buckets = {}
	for row in rows:
		key = row.get(field) or _("Not Set")
		bucket = buckets.setdefault(
			key,
			{field: key, "issues": set(), "vehicles": set(), "items": set(),
			 "qty": 0.0, "amount": 0.0, "tyres": 0},
		)
		bucket["issues"].add(row["issue"])
		bucket["vehicles"].add(row["vehicle"])
		bucket["items"].add(row["item_code"])
		bucket["qty"] += float(row.get("qty") or 0)
		bucket["amount"] += float(row.get("amount") or 0)
		if row.get("is_tyre"):
			bucket["tyres"] += 1

	data = []
	for bucket in buckets.values():
		bucket["issues"] = len(bucket["issues"])
		bucket["vehicles"] = len(bucket["vehicles"])
		bucket["items"] = len(bucket["items"])
		data.append(bucket)

	data.sort(key=lambda r: -r["amount"])
	return data


def grouped_columns(field, label, fieldtype, options):
	return [
		{"fieldname": field, "label": label, "fieldtype": fieldtype,
		 "options": options, "width": 200},
		{"fieldname": "issues", "label": _("Issues"), "fieldtype": "Int", "width": 90},
		{"fieldname": "vehicles", "label": _("Vehicles"), "fieldtype": "Int", "width": 90},
		{"fieldname": "items", "label": _("Distinct Items"), "fieldtype": "Int", "width": 120},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "precision": 2, "width": 100},
		{"fieldname": "tyres", "label": _("Tyres"), "fieldtype": "Int", "width": 80},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 140},
	]


def detail_columns():
	return [
		{"fieldname": "issue", "label": _("Issue"), "fieldtype": "Link",
		 "options": "Fleet Part Issue", "width": 140},
		{"fieldname": "issue_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link",
		 "options": "Vehicle", "width": 120},
		{"fieldname": "site", "label": _("Site"), "fieldtype": "Link",
		 "options": "Location", "width": 120},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link",
		 "options": "Item", "width": 150},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "serial_no", "label": _("Serial No"), "fieldtype": "Data", "width": 130},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "precision": 2, "width": 80},
		{"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM", "width": 80},
		{"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "odometer", "label": _("Odometer"), "fieldtype": "Int", "width": 100},
		{"fieldname": "purpose", "label": _("Purpose"), "fieldtype": "Data", "width": 140},
		{"fieldname": "driver", "label": _("Driver"), "fieldtype": "Link",
		 "options": "Driver", "width": 120},
		{"fieldname": "stock_entry", "label": _("Stock Entry"), "fieldtype": "Link",
		 "options": "Stock Entry", "width": 140},
	]


def summary(rows):
	if not rows:
		return _(
			"No parts were issued on this filter. Parts appear here once the "
			"Fleet Part Issue is submitted - a draft issue has not left store yet."
		)

	amount = sum(float(r.get("amount") or 0) for r in rows)
	issues = len({r["issue"] for r in rows})
	vehicles = len({r["vehicle"] for r in rows})
	tyres = sum(1 for r in rows if r.get("is_tyre"))
	serialised = sum(1 for r in rows if r.get("serial_no"))

	return _(
		"<b>{0}</b> line(s) across <b>{1}</b> issue(s) to <b>{2}</b> vehicle(s), "
		"costing <b>{3:,.2f}</b>. <b>{4}</b> were tyres and <b>{5}</b> carried a serial number."
	).format(len(rows), issues, vehicles, amount, tyres, serialised)


def chart(data, field):
	top = data[:12]
	if not top:
		return None
	return {
		"data": {
			"labels": [str(r[field]) for r in top],
			"datasets": [{"name": _("Amount"), "values": [r["amount"] for r in top]}],
		},
		"type": "bar",
	}
