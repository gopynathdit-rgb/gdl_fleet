# Copyright (c) 2026, GDL and contributors
"""
POL Supplier / Book Balance - Fleet Mgmt.docx section 5.

One row per fuel supply line, with the abstract's BOD and STCBL recoupment and
book balance carried alongside.

Avoiding double counting: the abstract-level recoupment and book balance are
printed only once per abstract, against its first line. Repeating them on every
line would make a naive column total read as several times the real figure.
"""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})

	columns = [
		{"fieldname": "abstract", "label": _("POL Abstract"), "fieldtype": "Link", "options": "POL Abstract", "width": 150},
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 120},
		{"fieldname": "period", "label": _("Reporting Period"), "fieldtype": "Data", "width": 170},
		{"fieldname": "supply_memo_no", "label": _("Supply Memo No."), "fieldtype": "Data", "width": 130},
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "supplier", "label": _("Supplier"), "fieldtype": "Link", "options": "Supplier", "width": 140},
		{"fieldname": "fuel_type", "label": _("Fuel Type"), "fieldtype": "Data", "width": 100},
		{"fieldname": "litres", "label": _("Litres"), "fieldtype": "Float", "precision": 3, "width": 90},
		{"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "amount_bod", "label": _("Amount (BOD)"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "amount_stcbl", "label": _("Amount (STCBL)"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "overridden", "label": _("Overridden"), "fieldtype": "Data", "width": 90},
		{"fieldname": "opening_bod", "label": _("Opening Bal. (BOD)"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "recoupment_bod", "label": _("Recoupment (BOD)"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "opening_stcbl", "label": _("Opening Bal. (STCBL)"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "recoupment_stcbl", "label": _("Recoupment (STCBL)"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "book_balance_bod", "label": _("Closing Bal. (BOD)"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "book_balance_stcbl", "label": _("Closing Bal. (STCBL)"), "fieldtype": "Currency", "width": 150},
	]

	conditions = {"docstatus": ("<", 2)}
	if filters.get("vehicle"):
		conditions["vehicle"] = filters.vehicle
	if filters.get("site"):
		conditions["site"] = filters.site
	if filters.get("status"):
		conditions["status"] = filters.status
	if filters.get("from_date"):
		conditions["period_to"] = (">=", filters.from_date)
	if filters.get("to_date"):
		conditions["period_from"] = ("<=", filters.to_date)

	abstracts = frappe.get_all(
		"POL Abstract",
		filters=conditions,
		fields=["name", "vehicle", "period_from", "period_to", "recoupment_bod",
		        "recoupment_stcbl", "fuel_book_balance_bod", "fuel_book_balance_stcbl",
		        "opening_book_balance_bod", "opening_book_balance_stcbl"],
		order_by="vehicle asc, period_from asc",
	)
	if not abstracts:
		return columns, [], _("No POL abstracts match these filters.")

	by_name = {a.name: a for a in abstracts}

	entry_filters = {"parenttype": "POL Abstract", "parent": ("in", list(by_name))}
	if filters.get("supplier"):
		entry_filters["supplier"] = filters.supplier

	entries = frappe.get_all(
		"POL Entry",
		filters=entry_filters,
		fields=["parent", "supply_memo_no", "date", "supplier", "fuel_type",
		        "litres", "rate", "amount_bod", "amount_stcbl", "amount_overridden", "idx"],
		order_by="parent asc, idx asc",
	)

	data = []
	abstract_totals_shown = set()
	for entry in entries:
		abstract = by_name[entry.parent]
		first_line = entry.parent not in abstract_totals_shown
		abstract_totals_shown.add(entry.parent)

		data.append({
			"abstract": entry.parent,
			"vehicle": abstract.vehicle,
			"period": f"{abstract.period_from} to {abstract.period_to}",
			"supply_memo_no": entry.supply_memo_no,
			"date": entry.date,
			"supplier": entry.supplier,
			"fuel_type": entry.fuel_type,
			"litres": entry.litres,
			"rate": entry.rate,
			"amount_bod": entry.amount_bod,
			"amount_stcbl": entry.amount_stcbl,
			"overridden": _("Yes") if entry.amount_overridden else None,
			# Abstract-level figures appear once, against the first line only.
			"opening_bod": abstract.opening_book_balance_bod if first_line else None,
			"recoupment_bod": abstract.recoupment_bod if first_line else None,
			"opening_stcbl": abstract.opening_book_balance_stcbl if first_line else None,
			"recoupment_stcbl": abstract.recoupment_stcbl if first_line else None,
			"book_balance_bod": abstract.fuel_book_balance_bod if first_line else None,
			"book_balance_stcbl": abstract.fuel_book_balance_stcbl if first_line else None,
		})

	message = _(
		"Litres, rate and amount are per supply line. Opening balance, "
		"recoupment and closing balance belong to the abstract as a whole, so "
		"they are shown once against its first line and are not repeated - "
		"repeating them would multiply the column total. "
		"<b>Closing = Opening + Recouped - Spent</b>, and that closing figure "
		"becomes the opening balance of the vehicle's next abstract, which is "
		"the coupon's running to-date amount."
	)
	return columns, data, message
