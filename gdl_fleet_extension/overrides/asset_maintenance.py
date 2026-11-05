# Copyright (c) 2026, GDL and contributors
"""
Phase 7 - GDL rules layered on the STANDARD Asset maintenance DocTypes.

doc_events only: the standard controllers run untouched and these add the fleet
behaviour on top. Nothing here posts a GL entry or moves stock - Asset Repair
already does both through ERPNext.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from gdl_fleet_extension.utils.maintenance import update_task_after_service
from gdl_fleet_extension.utils.odometer import get_last_odometer, recalculate_vehicle_odometer


# ----------------------------------------------------------------------
# Asset Maintenance Log - preventive service record
# ----------------------------------------------------------------------
def maintenance_log_validate(doc, method=None):
	set_vehicle_from_asset(doc)
	set_total_cost(doc)
	validate_log_odometer(doc)


def set_vehicle_from_asset(doc):
	if doc.get("vehicle") or not doc.get("asset_name"):
		return
	vehicle = frappe.db.get_value("Vehicle", {"asset": doc.asset_name}, "name")
	if vehicle:
		doc.vehicle = vehicle


def set_total_cost(doc):
	"""Section 4.4: parts cost is the sum of the maintenance items recorded."""
	rows = doc.get("service_items") or []
	if rows:
		doc.parts_cost = sum(flt(row.cost) for row in rows)
	doc.total_cost = flt(doc.get("labour_cost")) + flt(doc.get("parts_cost"))


def validate_log_odometer(doc):
	if not (doc.get("vehicle") and doc.get("odometer")):
		return

	if cint(doc.odometer) < 0:
		frappe.throw(_("Odometer cannot be negative."))

	previous = get_last_odometer(
		doc.vehicle,
		exclude=("Asset Maintenance Log", doc.name or ""),
		include_vehicle_current=True,
	)
	if cint(doc.odometer) < previous:
		frappe.throw(
			_("Odometer {0} is below the vehicle's latest valid reading of {1}.").format(
				cint(doc.odometer), previous
			),
			title=_("Odometer Moves Backwards"),
		)


def maintenance_log_on_submit(doc, method=None):
	"""Roll the task's next due date and KM forward, then refresh the odometer."""
	if doc.get("asset_maintenance") and doc.get("task"):
		task_name = doc.get("task_name") or frappe.db.get_value(
			"Asset Maintenance Task", doc.task, "maintenance_task"
		)
		if task_name and doc.maintenance_status == "Completed":
			update_task_after_service(
				doc.asset_maintenance, task_name, doc.completion_date, cint(doc.get("odometer"))
			)
			sync_next_due_onto_log(doc, task_name)

	if doc.get("vehicle") and doc.get("odometer"):
		recalculate_vehicle_odometer(doc.vehicle)


def sync_next_due_onto_log(doc, task_name):
	row = frappe.db.get_value(
		"Asset Maintenance Task",
		{"parent": doc.asset_maintenance, "maintenance_task": task_name},
		["next_due_date", "next_due_odometer"],
		as_dict=True,
	)
	if row:
		doc.db_set("next_due_date", row.next_due_date, update_modified=False)
		doc.db_set("next_due_odometer", row.next_due_odometer, update_modified=False)


def maintenance_log_on_cancel(doc, method=None):
	if doc.get("vehicle"):
		recalculate_vehicle_odometer(
			doc.vehicle, exclude=("Asset Maintenance Log", doc.name)
		)


# ----------------------------------------------------------------------
# Asset Repair - corrective maintenance
# ----------------------------------------------------------------------
def asset_repair_validate(doc, method=None):
	set_repair_vehicle(doc)
	validate_repair_odometer(doc)


def set_repair_vehicle(doc):
	"""`vehicle` is the Phase 3 Accounting Dimension field; default it from the Asset."""
	if doc.get("vehicle") or not doc.get("asset"):
		return
	vehicle = frappe.db.get_value("Vehicle", {"asset": doc.asset}, "name")
	if vehicle:
		doc.vehicle = vehicle


def validate_repair_odometer(doc):
	if not (doc.get("vehicle") and doc.get("odometer")):
		return

	if cint(doc.odometer) < 0:
		frappe.throw(_("Odometer cannot be negative."))

	previous = get_last_odometer(
		doc.vehicle, exclude=("Asset Repair", doc.name or ""), include_vehicle_current=True
	)
	if cint(doc.odometer) < previous:
		frappe.throw(
			_("Odometer {0} is below the vehicle's latest valid reading of {1}.").format(
				cint(doc.odometer), previous
			),
			title=_("Odometer Moves Backwards"),
		)


def asset_repair_on_submit(doc, method=None):
	if doc.get("vehicle") and doc.get("odometer"):
		recalculate_vehicle_odometer(doc.vehicle)


def asset_repair_on_cancel(doc, method=None):
	if doc.get("vehicle"):
		recalculate_vehicle_odometer(doc.vehicle, exclude=("Asset Repair", doc.name))


def maintenance_log_purchasing(doc, method=None):
	"""CR3: a completed, outsourced service may raise a purchase order.

	Attached to the existing maintenance hooks rather than a new one. The whole
	path is a no-op until GDL enables it in Fleet Settings.
	"""
	from gdl_fleet_extension.utils.fleet_purchase_automation import (
		process_maintenance_completion,
	)

	process_maintenance_completion(doc, method)
