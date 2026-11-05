# Copyright (c) 2026, GDL and contributors
"""
GDL validation layered on the STANDARD ERPNext Vehicle via doc_events.

The standard controller (erpnext.setup.doctype.vehicle.vehicle.Vehicle) still runs
first and is untouched; this only adds GDL rules on top.
"""

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import cint, getdate, nowdate

VEHICLE_ID_SERIES = "GDL-VEH-.#####"


def validate(doc, method=None):
	set_vehicle_id(doc)
	validate_vehicle_id_unchanged(doc)
	validate_vehicle_id(doc)
	validate_manufacturing_year(doc)
	validate_site_is_leaf(doc)
	validate_asset_link(doc)
	validate_opening_odometer(doc)
	validate_documents(doc)


# ---------------------------------------------------------------------------
# Vehicle ID
# ---------------------------------------------------------------------------
def set_vehicle_id(doc):
	if not doc.get("gdl_vehicle_id"):
		doc.gdl_vehicle_id = make_autoname(VEHICLE_ID_SERIES)


def validate_vehicle_id_unchanged(doc):
	"""The Vehicle ID must be stable once it has a value.

	We cannot use the framework's `set_only_once`, because that also blocks the
	null -> value backfill needed for Vehicles that existed before this app was
	installed. So immutability is enforced only when a value was already stored.
	"""
	if doc.is_new():
		return

	previous = frappe.db.get_value("Vehicle", doc.name, "gdl_vehicle_id")
	if previous and previous != doc.gdl_vehicle_id:
		frappe.throw(
			_("Vehicle ID cannot be changed once set (current value: {0}).").format(frappe.bold(previous)),
			title=_("Vehicle ID is Immutable"),
		)


def validate_vehicle_id(doc):
	"""Uniqueness is enforced by the unique index too; this gives a clear message."""
	existing = frappe.db.get_value(
		"Vehicle",
		{"gdl_vehicle_id": doc.gdl_vehicle_id, "name": ("!=", doc.name)},
		"name",
	)
	if existing:
		frappe.throw(
			_("Vehicle ID {0} is already used by Vehicle {1}").format(
				frappe.bold(doc.gdl_vehicle_id), frappe.bold(existing)
			),
			title=_("Duplicate Vehicle ID"),
		)


def validate_manufacturing_year(doc):
	year = cint(doc.get("manufacturing_year"))
	if not year:
		return

	current_year = getdate(nowdate()).year
	if year < 1950 or year > current_year + 1:
		frappe.throw(
			_("Manufacturing Year {0} is not valid. Expected a year between 1950 and {1}.").format(
				year, current_year + 1
			)
		)


# ---------------------------------------------------------------------------
# Site (standard Location)
# ---------------------------------------------------------------------------
def validate_site_is_leaf(doc):
	if not doc.get("site"):
		return

	if frappe.db.get_value("Location", doc.site, "is_group"):
		frappe.throw(
			_("Site {0} is a group Location. Please select a specific site, not a group.").format(
				frappe.bold(doc.site)
			)
		)


# ---------------------------------------------------------------------------
# Asset linkage (Path A - GDL-owned vehicles)
# ---------------------------------------------------------------------------
def validate_asset_link(doc):
	if not doc.get("asset"):
		return

	other = frappe.db.get_value(
		"Vehicle", {"asset": doc.asset, "name": ("!=", doc.name)}, "name"
	)
	if other:
		frappe.throw(
			_("Asset {0} is already linked to Vehicle {1}. An Asset can belong to one Vehicle only.").format(
				frappe.bold(doc.asset), frappe.bold(other)
			)
		)

	if doc.get("company"):
		asset_company = frappe.db.get_value("Asset", doc.asset, "company")
		if asset_company and asset_company != doc.company:
			frappe.throw(
				_("Asset {0} belongs to Company {1} but this Vehicle belongs to {2}.").format(
					frappe.bold(doc.asset), frappe.bold(asset_company), frappe.bold(doc.company)
				)
			)


# ---------------------------------------------------------------------------
# Odometer
# ---------------------------------------------------------------------------
def validate_opening_odometer(doc):
	# On a new vehicle the current reading IS the opening reading unless stated
	# otherwise. Without this, cancelling every Vehicle Log would drop the
	# vehicle's odometer to zero instead of back to where it started.
	if doc.is_new() and not doc.get("opening_odometer") and cint(doc.last_odometer):
		doc.opening_odometer = cint(doc.last_odometer)

	opening = cint(doc.get("opening_odometer"))
	if not opening:
		return

	if opening > cint(doc.last_odometer):
		frappe.throw(
			_("Opening Odometer ({0}) cannot be greater than Current Odometer ({1}).").format(
				opening, cint(doc.last_odometer)
			)
		)


# ---------------------------------------------------------------------------
# Documents child table
# ---------------------------------------------------------------------------
def validate_documents(doc):
	notice_days = 30
	today = getdate(nowdate())

	for row in doc.get("documents") or []:
		if row.issue_date and row.expiry_date and getdate(row.expiry_date) < getdate(row.issue_date):
			frappe.throw(
				_("Row #{0}: Expiry Date cannot be before Issue Date for document {1}.").format(
					row.idx, row.document_type
				)
			)

		if not row.expiry_date:
			row.status = "Not Applicable"
		elif getdate(row.expiry_date) < today:
			row.status = "Expired"
		elif (getdate(row.expiry_date) - today).days <= notice_days:
			row.status = "Expiring Soon"
		else:
			row.status = "Valid"
