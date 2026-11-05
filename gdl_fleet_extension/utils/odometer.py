# Copyright (c) 2026, GDL and contributors
"""
Odometer history WITHOUT a second ledger DocType.

The readings already exist on the documents that record them. This module reads
them back on demand instead of copying them into an Odometer Reading table that
could drift out of step:

    Vehicle Log        submitted, `odometer`          (standard hrms)
    Asset Repair       submitted, `odometer`          (Phase 7, custom field)
    Asset Maintenance Log  submitted, `odometer`      (Phase 7, custom field)
    Vehicle            `opening_odometer`             (floor)

This is also what makes the standard cancellation defect fixable. ERPNext
subtracts the cancelled log's distance from the vehicle's current reading, which
is only correct when the cancelled log happens to be the most recent one. Here
the current reading is recomputed as MAX() over whatever is still live, which is
correct regardless of the order things are cancelled in.
"""

import frappe
from frappe.utils import cint

# doctype -> (vehicle fieldname, odometer fieldname)
ODOMETER_SOURCES = {
	"Vehicle Log": ("license_plate", "odometer"),
	"Asset Repair": ("vehicle", "odometer"),
	"Asset Maintenance Log": ("vehicle", "odometer"),
}


def _source_is_usable(doctype: str, vehicle_field: str, odometer_field: str) -> bool:
	"""Later phases add some of these, so skip anything not present yet."""
	if not frappe.db.exists("DocType", doctype):
		return False
	meta = frappe.get_meta(doctype)
	return bool(meta.get_field(vehicle_field) and meta.get_field(odometer_field))


def get_odometer_readings(
	vehicle: str, exclude: tuple[str, str] | None = None
) -> list[dict]:
	"""Every live reading for a vehicle, newest first.

	`exclude` is a (doctype, name) pair to leave out - used while cancelling, so
	the document being cancelled does not count towards the new current reading.
	"""
	readings = []

	for doctype, (vehicle_field, odometer_field) in ODOMETER_SOURCES.items():
		if not _source_is_usable(doctype, vehicle_field, odometer_field):
			continue

		filters = {vehicle_field: vehicle, "docstatus": 1}
		if exclude and exclude[0] == doctype:
			filters["name"] = ("!=", exclude[1])

		for row in frappe.get_all(
			doctype,
			filters=filters,
			fields=["name", f"{odometer_field} as odometer", "modified"],
		):
			if row.odometer is None:
				continue
			readings.append(
				{"doctype": doctype, "name": row.name, "odometer": cint(row.odometer)}
			)

	readings.sort(key=lambda r: r["odometer"], reverse=True)
	return readings


def get_last_odometer(
	vehicle: str,
	exclude: tuple[str, str] | None = None,
	include_vehicle_current: bool = False,
) -> int:
	"""The highest valid reading, never below the vehicle's opening odometer.

	`include_vehicle_current` also considers Vehicle.last_odometer. That is right
	when DEFAULTING a new trip's starting reading, because a vehicle loaded by
	data import has a real current reading with no document behind it. It must
	stay False when RECOMPUTING after a cancellation - the field being recomputed
	cannot also be its own floor, or it could never come down.
	"""
	readings = get_odometer_readings(vehicle, exclude=exclude)
	candidates = [readings[0]["odometer"]] if readings else [0]

	fields = ["opening_odometer"]
	if include_vehicle_current:
		fields.append("last_odometer")

	values = frappe.db.get_value("Vehicle", vehicle, fields, as_dict=True) or {}
	candidates.extend(cint(values.get(f)) for f in fields)

	return max(candidates)


def recalculate_vehicle_odometer(
	vehicle: str, exclude: tuple[str, str] | None = None
) -> int:
	"""Set Vehicle.last_odometer from live readings. Returns the new value."""
	if not vehicle:
		return 0

	value = get_last_odometer(vehicle, exclude=exclude)
	frappe.db.set_value("Vehicle", vehicle, "last_odometer", value, update_modified=False)
	return value
