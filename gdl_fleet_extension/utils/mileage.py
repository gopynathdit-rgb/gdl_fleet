# Copyright (c) 2026, GDL and contributors
"""
Vehicle utilisation - Fleet Mgmt.docx section 5, "Vehicle Utilization":
KM by vehicle/day/month, utilisation trend and idle vehicles.

Distance is read back from the documents that already record it through
utils.odometer. There is no second odometer ledger, which is what section 4.3
asks for.

The mileage-deviation feature (expected vs actual with an HR approval) is not a
requirement of this document and was de-scoped.
"""

import frappe
from frappe.utils import cint, date_diff, flt, get_first_day, getdate, nowdate

from gdl_fleet_extension.utils.odometer import ODOMETER_SOURCES, _source_is_usable


def get_odometer_bounds(vehicle: str, from_date, to_date) -> tuple[int, int]:
	"""Lowest and highest live readings inside a period, across every source."""
	readings = []

	for doctype, (vehicle_field, odometer_field) in ODOMETER_SOURCES.items():
		if not _source_is_usable(doctype, vehicle_field, odometer_field):
			continue

		meta = frappe.get_meta(doctype)
		date_field = None
		for candidate in ("date", "completion_date", "failure_date", "posting_date"):
			if meta.get_field(candidate):
				date_field = candidate
				break
		if not date_field:
			continue

		rows = frappe.get_all(
			doctype,
			filters={
				vehicle_field: vehicle,
				"docstatus": 1,
				date_field: ("between", [from_date, to_date]),
			},
			fields=[f"{odometer_field} as odometer"],
		)
		readings.extend(cint(r.odometer) for r in rows if r.odometer)

	if not readings:
		return 0, 0
	return min(readings), max(readings)


def get_actual_km(vehicle: str, from_date, to_date) -> int:
	"""Distance covered in a period.

	Daily KM records carry a distance directly, so those are summed. Other
	sources only carry a reading, so they contribute through the spread between
	the lowest and highest reading in the period. The larger of the two is used,
	which avoids both under-counting a month with no logs and double-counting a
	month that has them.
	"""
	logged = (
		frappe.db.sql(
			"""
			select sum(distance_travelled)
			from `tabVehicle Log`
			where license_plate = %(vehicle)s and docstatus = 1
			  and date between %(from_date)s and %(to_date)s
			""",
			{"vehicle": vehicle, "from_date": from_date, "to_date": to_date},
		)[0][0]
		or 0
	)

	low, high = get_odometer_bounds(vehicle, from_date, to_date)
	spread = high - low if high and low else 0

	return max(cint(logged), cint(spread))


@frappe.whitelist()
def get_utilization(from_date=None, to_date=None, vehicle=None, site=None,
                    department=None, driver=None, project=None) -> list[dict]:
	"""Distance, days used and idle days per vehicle for the period."""
	frappe.has_permission("Vehicle", "read", throw=True)

	to_date = to_date or nowdate()
	from_date = from_date or get_first_day(to_date)
	period_days = date_diff(getdate(to_date), getdate(from_date)) + 1

	filters = {"vehicle_status": ("!=", "Disposed")}
	if vehicle:
		filters["name"] = vehicle
	if site:
		filters["site"] = site
	if department:
		filters["department"] = department
	if project:
		filters["project"] = project
	if driver:
		filters["driver"] = driver

	rows = []
	for v in frappe.get_all(
		"Vehicle",
		filters=filters,
		fields=["name", "gdl_vehicle_id", "vehicle_type", "site", "department",
		        "project", "driver", "vehicle_status"],
		order_by="name asc",
	):
		actual = get_actual_km(v.name, from_date, to_date)

		# Days on an approved movement order, which is how travel is authorised.
		days_used = (
			frappe.db.sql(
				"""
				select count(distinct date(departure_datetime))
				from `tabMovement Order`
				where vehicle = %(vehicle)s and docstatus < 2
				  and status in ('Approved', 'Dispatched', 'Completed')
				  and date(departure_datetime) between %(from_date)s and %(to_date)s
				""",
				{"vehicle": v.name, "from_date": from_date, "to_date": to_date},
			)[0][0]
			or 0
		)

		rows.append({
			"vehicle": v.name,
			"gdl_vehicle_id": v.gdl_vehicle_id,
			"vehicle_type": v.vehicle_type,
			"site": v.site,
			"department": v.department,
			"project": v.project,
			"driver": v.driver,
			"vehicle_status": v.vehicle_status,
			"from_date": from_date,
			"to_date": to_date,
			"period_days": period_days,
			"days_used": cint(days_used),
			"idle_days": period_days - cint(days_used),
			"actual_km": actual,
			"utilization_pct": flt(days_used / period_days * 100.0, 2) if period_days else 0,
			"km_per_day": flt(actual / period_days, 2) if period_days else 0,
		})

	return rows
