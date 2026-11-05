# Copyright (c) 2026, GDL and contributors
"""
Spare parts issued to vehicles - Business Blueprint, Spare Parts Management:
"Spare Parts Tracking, Serial Number Tracking, Parts Consumption,
Replacement History".

Fleet Part Issue already holds every issue, with serial numbers and the
odometer it went on at. These helpers read that one trail two ways: what the
fleet consumed over a period, and how often a given part comes back on the
same vehicle.

Nothing here writes. The stock itself always lives in the standard Stock
Entry raised by the issue, so these figures never diverge from the ledger.
"""

import frappe

ISSUE_FIELDS = (
	"`tabFleet Part Issue`.name as issue",
	"`tabFleet Part Issue`.vehicle",
	"`tabFleet Part Issue`.issue_date",
	"`tabFleet Part Issue`.odometer",
	"`tabFleet Part Issue`.purpose",
	"`tabFleet Part Issue`.location as site",
	"`tabFleet Part Issue`.driver",
	"`tabFleet Part Issue`.cost_center",
	"`tabFleet Part Issue`.project",
	"`tabFleet Part Issue`.stock_entry",
	"item.item_code",
	"item.item_name",
	"item.is_tyre",
	"item.tyre_position",
	"item.serial_no",
	"item.qty",
	"item.uom",
	"item.rate",
	"item.amount",
	"item.idx",
)


def get_issued_parts(
	from_date=None, to_date=None, vehicle=None, item_code=None,
	site=None, purpose=None, tyres_only=False, exclude_tyres=False,
) -> list[dict]:
	"""Every submitted part-issue line, newest first.

	Draft issues are left out on purpose: nothing has moved out of store until
	the issue is submitted, so counting a draft would overstate consumption.
	"""
	conditions = ["`tabFleet Part Issue`.docstatus = 1"]
	values = {}

	if from_date:
		conditions.append("`tabFleet Part Issue`.issue_date >= %(from_date)s")
		values["from_date"] = from_date
	if to_date:
		conditions.append("`tabFleet Part Issue`.issue_date <= %(to_date)s")
		values["to_date"] = to_date
	if vehicle:
		conditions.append("`tabFleet Part Issue`.vehicle = %(vehicle)s")
		values["vehicle"] = vehicle
	if site:
		conditions.append("`tabFleet Part Issue`.location = %(site)s")
		values["site"] = site
	if purpose:
		conditions.append("`tabFleet Part Issue`.purpose = %(purpose)s")
		values["purpose"] = purpose
	if item_code:
		conditions.append("item.item_code = %(item_code)s")
		values["item_code"] = item_code
	if tyres_only:
		conditions.append("item.is_tyre = 1")
	if exclude_tyres:
		conditions.append("ifnull(item.is_tyre, 0) = 0")

	return frappe.db.sql(
		"""
		select {fields}
		from `tabFleet Part Issue`
		inner join `tabFleet Part Issue Item` as item
		    on item.parent = `tabFleet Part Issue`.name
		where {conditions}
		order by `tabFleet Part Issue`.vehicle asc,
		         `tabFleet Part Issue`.issue_date desc,
		         item.idx asc
		""".format(fields=", ".join(ISSUE_FIELDS), conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)


def build_replacement_history(rows) -> list[dict]:
	"""Turn the issue trail into a per-part replacement history.

	For each vehicle and item the rows are walked oldest first, so every issue
	after the first can state how long the part it replaced lasted - in days
	and in kilometres. That interval is the whole point of the report; a bare
	list of issues does not tell anyone whether a part is wearing out early.

	A zero or negative interval is reported as None rather than 0. It means two
	issues share a date or an odometer reading, which is a data question, not a
	part that lasted no distance.
	"""
	by_part = {}
	for row in rows:
		by_part.setdefault((row["vehicle"], row["item_code"]), []).append(row)

	history = []
	for (vehicle, item_code), issues in by_part.items():
		issues = sorted(issues, key=lambda r: (r["issue_date"], r["odometer"] or 0, r["idx"]))
		previous = None
		for sequence, row in enumerate(issues, start=1):
			entry = dict(row)
			entry["sequence"] = sequence
			entry["replacements"] = len(issues)
			entry["previous_issue"] = previous["issue"] if previous else None
			entry["km_since_previous"] = _positive(
				(row["odometer"] or 0) - (previous["odometer"] or 0)
			) if previous else None
			entry["days_since_previous"] = _positive(
				(row["issue_date"] - previous["issue_date"]).days
			) if previous else None
			history.append(entry)
			previous = row

	history.sort(key=lambda r: (r["vehicle"] or "", r["item_code"] or "", r["sequence"]))
	return history


def _positive(value):
	return value if value and value > 0 else None
