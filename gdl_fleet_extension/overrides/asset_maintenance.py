# Copyright (c) 2026, GDL and contributors
"""
Phase 7 - GDL rules layered on the STANDARD Asset maintenance DocTypes.

doc_events only: the standard controllers run untouched and these add the fleet
behaviour on top. Nothing here posts a GL entry or moves stock - Asset Repair
already does both through ERPNext.
"""

import frappe

from erpnext.assets.doctype.asset_maintenance_log.asset_maintenance_log import (
	AssetMaintenanceLog,
)
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
	set_next_due_from_rules(doc)
	validate_log_odometer(doc)


def set_next_due_from_rules(doc):
	"""Next service date / KM for a service with no maintenance plan behind it.

	Document §2.1.1.4: "Track the next service date or odometer based on the
	periodic services selected."

	Until now this only ran for a service raised from an ERPNext Asset
	Maintenance PLAN - sync_next_due_onto_log below. GDL has no plans and
	cannot have any: a plan needs an Asset, and none of the 14 vehicles is
	linked to one, which is why Asset Maintenance came off the menu. So every
	GDL service record was left with a blank next due, and the Service Due
	report had nothing to list at all.

	The schedule comes from GDL's own 12 Maintenance Rules instead, matched to
	the Service Types actually chosen on this visit. Where a visit covers
	several items the EARLIEST wins - the vehicle is next needed in the
	workshop when the first item falls due, not the last.
	"""
	if doc.get("asset_maintenance") and doc.get("task"):
		return		# a plan owns the schedule; leave it alone
	if doc.get("maintenance_status") != "Completed" or not doc.get("vehicle"):
		return

	from frappe.utils import add_months, getdate

	from gdl_fleet_extension.utils.maintenance import get_maintenance_rules

	vehicle_type = frappe.db.get_value("Vehicle", doc.vehicle, "vehicle_type")
	rules = {r.service_item: r for r in get_maintenance_rules(vehicle_type)}

	next_date, next_km = None, None
	for row in doc.get("service_items") or []:
		rule = rules.get(row.get("service_item"))
		if not rule:
			continue

		if cint(rule.interval_months) and doc.get("completion_date"):
			due = add_months(getdate(doc.completion_date), cint(rule.interval_months))
			next_date = due if not next_date or getdate(due) < getdate(next_date) else next_date

		if cint(rule.interval_km) and cint(doc.get("odometer")):
			due_km = cint(doc.odometer) + cint(rule.interval_km)
			next_km = due_km if not next_km or due_km < next_km else next_km

	doc.next_due_date = next_date
	doc.next_due_odometer = next_km or 0


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


# ---------------------------------------------------------------------------
# The standalone service record
# ---------------------------------------------------------------------------
class GDLAssetMaintenanceLog(AssetMaintenanceLog):
	"""Lets a service be recorded without a maintenance plan behind it.

	ERPNext's Asset Maintenance Log is built as a child of an Asset Maintenance
	plan: on_submit calls update_maintenance_task(), which does

	    frappe.get_doc("Asset Maintenance Task", self.task)

	with no check that a task exists. GDL records services as they happen - a
	driver takes the vehicle in, it is serviced, the visit is written down -
	and there is no plan or task behind that. Submitting such a record died on
	"Asset Maintenance Task None not found", so a standalone service could be
	saved and never submitted.

	Blueprint 2.1.1.4 asks for a service record against the vehicle and its
	odometer. It says nothing about maintenance plans, and 0 of GDL's vehicles
	are linked to an Asset.

	When a plan IS behind the log - a preventive service raised from a
	schedule - ERPNext's own behaviour runs untouched, so nothing is lost.
	"""

	def update_maintenance_task(self):
		if not (self.get("task") and self.get("asset_maintenance")):
			# A service with no plan behind it. Nothing to roll forward.
			return
		super().update_maintenance_task()


# ---------------------------------------------------------------------------
# What a vehicle brings with it, when one is picked on a service record
# ---------------------------------------------------------------------------
@frappe.whitelist()
def vehicle_defaults(vehicle: str | None = None):
	"""Everything a service record can take from the vehicle itself.

	GDL: "In asset maintance when i select vechile need fetch all deatils
	automatily fill like location and all."

	Deliberately a server call rather than `fetch_from` on each field.
	fetch_from locks a field read-only and re-asserts the source value on every
	save, and two of these must stay editable: the service LOCATION is where
	the vehicle was serviced, which is often not the site it belongs to, and
	the ODOMETER is the reading at service, which is the whole point of the
	record. These are starting values, not bindings.

	The driver is the one assigned on the day, not a field on the vehicle -
	a Temporary or Relief assignment outranks the Primary one, which is why
	this goes through get_active_driver rather than reading a column.
	"""
	if not vehicle:
		return {}

	frappe.has_permission("Vehicle", "read", throw=True)

	values = frappe.db.get_value(
		"Vehicle", vehicle,
		["cost_center", "project", "last_odometer"], as_dict=True) or {}

	from gdl_fleet_extension.gdl_fleet.doctype.driver_assignment.driver_assignment import (
		get_active_driver,
	)

	# No "location": it is bound to vehicle.site with fetch_from on the field
	# itself, which fills it and holds it read-only. Setting it here as well
	# would be a second source for one value.
	return {
		"cost_center": values.get("cost_center"),
		"project": values.get("project"),
		"odometer": values.get("last_odometer"),
		"driver": get_active_driver(vehicle),
	}
