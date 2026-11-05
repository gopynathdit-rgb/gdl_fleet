# Copyright (c) 2026, GDL and contributors
"""
Tyre performance against the target in the final requirements document.

    "Tire performance target: 20,000 km +/-20%."

Both the target and the tolerance are configuration in GDL Fleet Settings, so
GDL can change either without a code change.

A tyre that falls short of tolerance is a procurement or road-condition
question; one that runs far beyond it usually means a missed removal reading,
so both ends are reported.
"""

from decimal import Decimal

import frappe

from gdl_fleet_extension.utils.pol import quantize, to_decimal

DEFAULT_TARGET_KM = 20000
DEFAULT_TOLERANCE = Decimal("20")

IN_SERVICE = "In Service"
WITHIN = "Within Tolerance"
BELOW = "Below Tolerance"
ABOVE = "Above Tolerance"


def get_tyre_target() -> int:
	value = frappe.db.get_single_value("GDL Fleet Settings", "tyre_target_km")
	return int(value) if value else DEFAULT_TARGET_KM


def get_tyre_tolerance() -> Decimal:
	value = frappe.db.get_single_value("GDL Fleet Settings", "tyre_tolerance")
	return to_decimal(value) if value not in (None, "", 0) else DEFAULT_TOLERANCE


def tyre_bounds(target=None, tolerance=None):
	"""The acceptable kilometre band around the target."""
	target = to_decimal(target if target is not None else get_tyre_target())
	tolerance = to_decimal(tolerance if tolerance is not None else get_tyre_tolerance())
	margin = target * tolerance / Decimal("100")
	return target - margin, target + margin


def tyre_deviation_percent(km_achieved, target=None):
	"""Signed deviation of the kilometres achieved from the target."""
	target = to_decimal(target if target is not None else get_tyre_target())
	if target <= 0:
		return None
	return (to_decimal(km_achieved) - target) / target * Decimal("100")


def classify_tyre(km_achieved, target=None, tolerance=None) -> str:
	"""Where a removed tyre sits against the target band."""
	if km_achieved in (None, ""):
		return IN_SERVICE

	low, high = tyre_bounds(target, tolerance)
	km = to_decimal(km_achieved)
	if km < low:
		return BELOW
	if km > high:
		return ABOVE
	return WITHIN


def get_tyre_performance(from_date=None, to_date=None, vehicle=None, status=None) -> list[dict]:
	"""Every tyre with what it achieved, for the Tyre Mileage Report."""
	filters = {}
	if vehicle:
		filters["vehicle"] = vehicle
	if status:
		filters["status"] = status
	if from_date:
		filters["fitted_date"] = (">=", from_date)
	if to_date:
		filters["fitted_date"] = ("<=", to_date) if not from_date else ("between", [from_date, to_date])

	rows = frappe.get_all(
		"Vehicle Tyre",
		filters=filters,
		fields=["name", "vehicle", "item_code", "serial_no", "tyre_position", "status",
		        "fitted_date", "fitted_odometer", "removed_date", "removed_odometer",
		        "km_achieved", "removal_reason", "cost"],
		order_by="vehicle asc, fitted_date asc",
	)

	target = get_tyre_target()
	tolerance = get_tyre_tolerance()
	low, high = tyre_bounds(target, tolerance)

	for row in rows:
		row["target_km"] = target
		row["acceptable_from"] = float(low)
		row["acceptable_to"] = float(high)

		if row.get("km_achieved") in (None, ""):
			# still on the vehicle - show the distance run so far
			current = frappe.db.get_value("Vehicle", row["vehicle"], "last_odometer")
			running = (current or 0) - (row.get("fitted_odometer") or 0)
			row["km_so_far"] = running if running > 0 else 0
			row["performance"] = IN_SERVICE
			row["deviation"] = None
		else:
			row["km_so_far"] = row["km_achieved"]
			row["performance"] = classify_tyre(row["km_achieved"], target, tolerance)
			deviation = tyre_deviation_percent(row["km_achieved"], target)
			row["deviation"] = float(quantize(deviation, 2)) if deviation is not None else None

		row["cost"] = float(row.get("cost") or 0)
		row["cost_per_km"] = cost_per_km(row["cost"], row["km_so_far"])
		row["projected_cost_per_km"] = cost_per_km(row["cost"], target)

	return rows


def cost_per_km(cost, km):
	"""What a tyre costs for every kilometre it has actually run.

	None rather than zero when there is nothing to divide by: a tyre fitted
	today has no cost per km yet, and reporting 0.00 would read as "free".
	"""
	cost = to_decimal(cost or 0)
	km = to_decimal(km or 0)
	if cost <= 0 or km <= 0:
		return None
	return float(quantize(cost / km, 4))
