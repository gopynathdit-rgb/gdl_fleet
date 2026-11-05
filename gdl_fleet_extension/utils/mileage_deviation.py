# Copyright (c) 2026, GDL and contributors
"""
Mileage deviation against each vehicle's minimum required km/l.

`Fleet Management- Final. 25-Sept.docx`, Optimal Fleet Utilization:

    "Mileage monitoring via ERPNext Vehicle Log.
     Deviation >10% requires HR approval workflow."

and in the GAP section, "chart deviation monitoring (±10%)".

GDL confirmed the tolerance applies in BOTH directions: a vehicle running far
better than its target is as much a data-quality signal as one running worse,
because it usually means a missed fill or a mis-keyed odometer.

    deviation % = (actual - minimum) / minimum * 100

Vehicles with no minimum set are excluded. The chart gives the BYD EV a minimum
of 0, and km/l is meaningless for an electric vehicle, so a minimum of zero is
read as "efficiency not applicable" rather than "target is zero" - which would
otherwise make every EV infinitely over target and divide by zero.
"""

from decimal import Decimal

import frappe

from gdl_fleet_extension.utils.pol import quantize, to_decimal

DEFAULT_TOLERANCE = Decimal("10")

WITHIN = "Within Tolerance"
BELOW = "Below Tolerance"
ABOVE = "Above Tolerance"
NOT_APPLICABLE = "Not Applicable"


def get_tolerance() -> Decimal:
	"""Configured in GDL Fleet Settings; never hard-coded."""
	value = frappe.db.get_single_value("GDL Fleet Settings", "mileage_deviation_tolerance")
	return to_decimal(value) if value not in (None, "", 0) else DEFAULT_TOLERANCE


def deviation_percent(actual, minimum):
	"""Signed deviation of actual km/l from the vehicle's minimum.

	Returns None when the minimum is not usable - no target, or a target of
	zero, which the chart uses for vehicles where fuel efficiency does not
	apply.
	"""
	minimum = to_decimal(minimum)
	if minimum <= 0:
		return None

	actual = to_decimal(actual)
	return (actual - minimum) / minimum * Decimal("100")


def classify(actual, minimum, tolerance=None):
	"""Where a vehicle sits against its target.

	Returns (status, deviation_percent). Deviation is None when the vehicle is
	not monitored.
	"""
	deviation = deviation_percent(actual, minimum)
	if deviation is None:
		return NOT_APPLICABLE, None

	tolerance = to_decimal(tolerance) if tolerance is not None else get_tolerance()
	if deviation < -tolerance:
		return BELOW, deviation
	if deviation > tolerance:
		return ABOVE, deviation
	return WITHIN, deviation


def needs_hr_approval(actual, minimum, tolerance=None) -> bool:
	"""True when the deviation is outside tolerance in either direction."""
	status, _deviation = classify(actual, minimum, tolerance)
	return status in (BELOW, ABOVE)


# ---------------------------------------------------------------------------
# Rolling the approved POL abstracts up per vehicle
# ---------------------------------------------------------------------------
def get_vehicle_mileage(from_date=None, to_date=None, vehicle=None, site=None) -> list[dict]:
	"""Actual km/l per vehicle for the period, against its minimum.

	Totals are summed across the vehicle's approved abstracts and the ratio is
	taken once at the end. Averaging each abstract's km/l would weight a short
	period the same as a long one.
	"""
	filters = {"docstatus": 1}
	if vehicle:
		filters["vehicle"] = vehicle
	if site:
		filters["site"] = site
	if from_date:
		filters["period_to"] = (">=", from_date)
	if to_date:
		filters["period_from"] = ("<=", to_date)

	abstracts = frappe.get_all(
		"POL Abstract",
		filters=filters,
		fields=["name", "vehicle", "site", "total_km", "total_fuel_consumed",
		        "total_fuel_supplied", "period_from", "period_to"],
		order_by="vehicle asc, period_from asc",
	)

	tolerance = get_tolerance()
	rolled: dict[str, dict] = {}
	for row in abstracts:
		bucket = rolled.setdefault(row.vehicle, {
			"vehicle": row.vehicle, "site": row.site, "abstracts": 0,
			"total_km": Decimal("0"), "total_fuel_consumed": Decimal("0"),
			"total_fuel_supplied": Decimal("0"),
		})
		bucket["abstracts"] += 1
		bucket["site"] = bucket["site"] or row.site
		for field in ("total_km", "total_fuel_consumed", "total_fuel_supplied"):
			bucket[field] += to_decimal(row.get(field))

	if not rolled:
		return []

	targets = {
		v.name: v.get("min_mileage")
		for v in frappe.get_all("Vehicle", filters={"name": ("in", list(rolled))},
		                        fields=["name", "min_mileage", "make", "model"])
	}
	details = {
		v.name: v for v in frappe.get_all(
			"Vehicle", filters={"name": ("in", list(rolled))},
			fields=["name", "make", "model", "vehicle_type"])
	}

	data = []
	for bucket in rolled.values():
		consumed = bucket["total_fuel_consumed"]
		actual = (bucket["total_km"] / consumed) if consumed > 0 else None
		minimum = targets.get(bucket["vehicle"])
		status, deviation = classify(actual or 0, minimum, tolerance)
		if actual is None:
			status, deviation = NOT_APPLICABLE, None

		info = details.get(bucket["vehicle"], {})
		data.append({
			"vehicle": bucket["vehicle"],
			"make": info.get("make"),
			"model": info.get("model"),
			"vehicle_type": info.get("vehicle_type"),
			"site": bucket["site"],
			"abstracts": bucket["abstracts"],
			"total_km": float(bucket["total_km"]),
			"total_fuel_consumed": float(consumed),
			"actual_mileage": float(quantize(actual, 2)) if actual is not None else None,
			"min_mileage": float(to_decimal(minimum)) if minimum else None,
			"deviation": float(quantize(deviation, 2)) if deviation is not None else None,
			"status": status,
			"hr_approval_required": status in (BELOW, ABOVE),
		})

	data.sort(key=lambda r: r["vehicle"] or "")
	return data
