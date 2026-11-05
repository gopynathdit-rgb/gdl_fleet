# Copyright (c) 2026, GDL and contributors
"""
Phase 3 - register the STANDARD ERPNext Vehicle DocType as an Accounting Dimension.

This uses ERPNext's own mechanism end to end:

    Accounting Dimension (document_type = "Vehicle")
        -> erpnext...accounting_dimension.make_dimension_in_accounting_doctypes()
        -> a Custom Field `vehicle` on every DocType listed in the
           `accounting_dimension_doctypes` hook (52 from erpnext + 5 from hrms)
        -> Budget.budget_against gains "Vehicle" via a Property Setter

Because the dimension creates the `vehicle` field itself, this app must NOT define
its own `vehicle` Custom Field on any of those DocTypes - doing so would collide.
See gdl_fleet_extension.setup.accounting_dimension.DIMENSION_SUPPLIED_DOCTYPES.

No GL code, no parallel cost ledger, no change to ERPNext core.
"""

import frappe
from frappe import _

VEHICLE_DIMENSION = "Vehicle"
VEHICLE_FIELDNAME = "vehicle"


def get_dimension_doctypes() -> list[str]:
	"""The authoritative list, straight from the hook - never hard-coded here."""
	return frappe.get_hooks("accounting_dimension_doctypes") or []


def vehicle_dimension_exists() -> bool:
	return bool(
		frappe.db.exists("Accounting Dimension", {"document_type": VEHICLE_DIMENSION})
	)


def setup_vehicle_dimension(force_sync: bool = False):
	"""Idempotent. Creates the dimension once, then ensures every field is present.

	ERPNext enqueues the field creation on a background worker. On a bench with no
	worker running that job would never execute, so the sync is also run inline -
	the standard function is itself idempotent (it skips DocTypes that already have
	the field), so running it twice is harmless.
	"""
	from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
		make_dimension_in_accounting_doctypes,
	)

	created = False

	if not vehicle_dimension_exists():
		dimension = frappe.get_doc(
			{
				"doctype": "Accounting Dimension",
				"document_type": VEHICLE_DIMENSION,
				"label": VEHICLE_DIMENSION,
				"fieldname": VEHICLE_FIELDNAME,
			}
		)
		dimension.flags.ignore_permissions = True
		dimension.insert()
		created = True
	else:
		dimension = frappe.get_doc(
			"Accounting Dimension", {"document_type": VEHICLE_DIMENSION}
		)

	if created or force_sync or missing_dimension_doctypes():
		make_dimension_in_accounting_doctypes(doc=dimension)
		frappe.clear_cache()

	return dimension.name


def missing_dimension_doctypes() -> list[str]:
	"""DocTypes that should carry the dimension field but do not (yet)."""
	doctypes = get_dimension_doctypes()
	if not doctypes:
		return []

	present = set(
		frappe.get_all(
			"Custom Field",
			filters={"fieldname": VEHICLE_FIELDNAME, "dt": ("in", doctypes)},
			pluck="dt",
		)
	)
	return sorted(set(doctypes) - present)


def verify_vehicle_dimension() -> dict:
	"""Read-only health check used by tests and by `bench execute`."""
	doctypes = get_dimension_doctypes()
	missing = missing_dimension_doctypes()

	budget_options = frappe.db.get_value(
		"Property Setter", "Budget-budget_against-options", "value"
	)

	return {
		"dimension_exists": vehicle_dimension_exists(),
		"expected_doctypes": len(doctypes),
		"fields_present": len(doctypes) - len(missing),
		"missing": missing,
		"budget_against_has_vehicle": bool(
			budget_options and VEHICLE_DIMENSION in budget_options.split("\n")
		),
		"duplicate_fields": find_duplicate_vehicle_fields(),
	}


def find_duplicate_vehicle_fields() -> list[str]:
	"""A `vehicle` Custom Field owned by this app on a dimension DocType is a bug.

	The dimension supplies those fields; anything this app adds on top would be a
	duplicate. Fields on NON-dimension DocTypes are legitimate and ignored here.
	"""
	doctypes = set(get_dimension_doctypes())
	if not doctypes:
		return []

	rows = frappe.get_all(
		"Custom Field",
		filters={"fieldname": VEHICLE_FIELDNAME, "dt": ("in", list(doctypes))},
		fields=["name", "dt", "module"],
	)

	by_doctype = {}
	for row in rows:
		by_doctype.setdefault(row.dt, []).append(row)

	return sorted(dt for dt, fields in by_doctype.items() if len(fields) > 1)
