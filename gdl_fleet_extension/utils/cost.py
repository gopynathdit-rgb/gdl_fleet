# Copyright (c) 2026, GDL and contributors
"""
Phase 14 - vehicle cost, read from the STANDARD General Ledger.

WHAT IS INCLUDED
----------------
Every posted expense carrying the Vehicle accounting dimension. Because the
dimension reaches `tabGL Entry` through the standard vouchers, one query covers
all of it with no risk of double counting:

    Expense Claim     fuel, parking, toll, washing, registration, insurance,
                      employee-paid repairs and spare parts
    Purchase Invoice  supplier fuel and workshop invoices
    Stock Entry       spare parts and tyres issued from store (valuation)
    Asset Repair      corrective repair cost and consumed items
    Journal Entry     anything posted manually against a vehicle

WHAT IS EXCLUDED
----------------
    * depreciation, unless GDL tags the depreciation entry with the vehicle
    * anything not tagged with the vehicle dimension
    * draft and cancelled vouchers (`is_cancelled = 0`, `docstatus = 1`)

Only debits to expense accounts are counted, so a payment settling a payable is
not counted a second time. This is the single source of vehicle cost - the app
keeps no parallel cost table.
"""

import frappe
from frappe.utils import cint, flt, get_first_day, nowdate

from gdl_fleet_extension.utils.mileage import get_actual_km


@frappe.whitelist()
def get_vehicle_cost(
	from_date=None, to_date=None, vehicle=None, site=None, cost_center=None, project=None
) -> list[dict]:
	"""Cost per vehicle, grouped by voucher type, straight from GL Entry."""
	frappe.has_permission("GL Entry", "read", throw=True)

	to_date = to_date or nowdate()
	from_date = from_date or get_first_day(to_date)

	conditions = [
		"gle.is_cancelled = 0",
		"gle.vehicle is not null",
		"gle.vehicle != ''",
		"gle.posting_date between %(from_date)s and %(to_date)s",
		"acc.root_type = 'Expense'",
	]
	values = {"from_date": from_date, "to_date": to_date}

	if vehicle:
		conditions.append("gle.vehicle = %(vehicle)s")
		values["vehicle"] = vehicle
	if cost_center:
		conditions.append("gle.cost_center = %(cost_center)s")
		values["cost_center"] = cost_center
	if project:
		conditions.append("gle.project = %(project)s")
		values["project"] = project

	rows = frappe.db.sql(
		"""
		select
			gle.vehicle, gle.voucher_type,
			sum(gle.debit) - sum(gle.credit) as amount
		from `tabGL Entry` gle
		inner join `tabAccount` acc on acc.name = gle.account
		where {conditions}
		group by gle.vehicle, gle.voucher_type
		""".format(conditions=" and ".join(conditions)),
		values,
		as_dict=True,
	)

	by_vehicle = {}
	for row in rows:
		entry = by_vehicle.setdefault(
			row.vehicle,
			{"vehicle": row.vehicle, "total_cost": 0.0, "by_voucher": {}},
		)
		entry["by_voucher"][row.voucher_type] = flt(row.amount, 2)
		entry["total_cost"] = flt(entry["total_cost"] + flt(row.amount), 2)

	# Vehicles with no cost still belong in the report.
	vehicle_filters = {}
	if vehicle:
		vehicle_filters["name"] = vehicle
	if site:
		vehicle_filters["site"] = site

	result = []
	for v in frappe.get_all(
		"Vehicle",
		filters=vehicle_filters,
		fields=["name", "gdl_vehicle_id", "vehicle_type", "site", "cost_center", "project"],
		order_by="gdl_vehicle_id asc",
	):
		entry = by_vehicle.get(v.name, {"total_cost": 0.0, "by_voucher": {}})
		distance = get_actual_km(v.name, from_date, to_date)

		result.append(
			{
				"vehicle": v.name,
				"gdl_vehicle_id": v.gdl_vehicle_id,
				"vehicle_type": v.vehicle_type,
				"site": v.site,
				"cost_center": v.cost_center,
				"project": v.project,
				"from_date": from_date,
				"to_date": to_date,
				"expense_claim": flt(entry["by_voucher"].get("Expense Claim", 0), 2),
				"purchase_invoice": flt(entry["by_voucher"].get("Purchase Invoice", 0), 2),
				"stock_entry": flt(entry["by_voucher"].get("Stock Entry", 0), 2),
				"asset_repair": flt(entry["by_voucher"].get("Asset Repair", 0), 2),
				"journal_entry": flt(entry["by_voucher"].get("Journal Entry", 0), 2),
				"total_cost": flt(entry["total_cost"], 2),
				"distance_km": distance,
				"cost_per_km": flt(entry["total_cost"] / distance, 2) if distance else None,
			}
		)

	return result
