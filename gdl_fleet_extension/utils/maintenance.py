# Copyright (c) 2026, GDL and contributors
"""
Phase 7 - preventive maintenance due engine.

ERPNext's Asset Maintenance Task carries a TIME interval (`periodicity`) and a
`next_due_date`. Nothing in ERPNext is distance-based, so this module supplies
the KM half and combines the two: a task is due when EITHER its date OR its
odometer threshold is reached, whichever comes first.

Every interval is read from GDL Fleet Settings at runtime. No service interval
is written into this file.
"""

import frappe
from frappe import _
from frappe.utils import add_months, cint, getdate, nowdate

# ERPNext periodicity option closest to a given number of months.
MONTHS_TO_PERIODICITY = {
	1: "Monthly",
	3: "Quarterly",
	6: "Half-yearly",
	12: "Yearly",
	24: "2 Yearly",
	36: "3 Yearly",
}


def get_settings():
	return frappe.get_single("GDL Fleet Settings")


def get_maintenance_rules(vehicle_type: str | None = None) -> list:
	"""Active rules from configuration, narrowed to a vehicle type.

	A rule with no vehicle_type applies to every vehicle.
	"""
	settings = get_settings()
	rules = []
	for row in settings.get("maintenance_rules") or []:
		if not row.is_active:
			continue
		if row.vehicle_type and vehicle_type and row.vehicle_type != vehicle_type:
			continue
		if row.vehicle_type and not vehicle_type:
			continue
		rules.append(row)
	return rules


def get_team_assignee(maintenance_team: str) -> str | None:
	"""ERPNext makes `assign_to` mandatory on every Asset Maintenance Task.

	Prefer the team's manager, otherwise its first member.
	"""
	if not maintenance_team:
		return None

	team = frappe.get_doc("Asset Maintenance Team", maintenance_team)

	candidates = [team.maintenance_manager]
	candidates += [m.team_member for m in team.get("maintenance_team_members") or []]

	for user in candidates:
		if not user:
			continue

		# A team can outlive the user account it names.
		enabled, email = (
			frappe.db.get_value("User", user, ["enabled", "email"]) or (None, None)
		)
		if not enabled:
			continue

		# erpnext's asset_maintenance.assign_tasks() resolves the member to
		# User.email and raises a ToDo against it, so that address must itself be
		# a User. It is not for Administrator, whose email is admin@example.com.
		if email and not frappe.db.exists("User", email):
			continue

		return user

	return None


def periodicity_for_months(months: int) -> str:
	"""Map a month interval onto the nearest standard periodicity option."""
	months = cint(months)
	if not months:
		return "Yearly"
	if months in MONTHS_TO_PERIODICITY:
		return MONTHS_TO_PERIODICITY[months]
	closest = min(MONTHS_TO_PERIODICITY, key=lambda m: abs(m - months))
	return MONTHS_TO_PERIODICITY[closest]


@frappe.whitelist()
def create_maintenance_plan(
	vehicle: str, start_date: str | None = None, maintenance_team: str | None = None
) -> str:
	"""Build the STANDARD Asset Maintenance plan for a vehicle from the rules.

	Requires the vehicle to be linked to an Asset, because Asset Maintenance is
	asset-scoped in ERPNext. Returns the Asset Maintenance name.
	"""
	frappe.has_permission("Asset Maintenance", "create", throw=True)

	vehicle_doc = frappe.get_doc("Vehicle", vehicle)
	if not vehicle_doc.get("asset"):
		frappe.throw(
			_(
				"Vehicle {0} has no linked Asset. Preventive maintenance uses the "
				"standard Asset Maintenance plan, so link an Asset first."
			).format(frappe.bold(vehicle)),
			title=_("Asset Required"),
		)

	rules = get_maintenance_rules(vehicle_doc.get("vehicle_type"))
	if not rules:
		frappe.throw(
			_("No active maintenance rules are configured in GDL Fleet Settings."),
			title=_("No Rules Configured"),
		)

	settings = get_settings()
	start_date = start_date or nowdate()
	current_odometer = cint(vehicle_doc.last_odometer)

	existing = frappe.db.exists("Asset Maintenance", {"asset_name": vehicle_doc.asset})
	if existing:
		plan = frappe.get_doc("Asset Maintenance", existing)
	else:
		plan = frappe.new_doc("Asset Maintenance")
		plan.asset_name = vehicle_doc.asset

	plan.vehicle = vehicle
	plan.company = vehicle_doc.company or frappe.defaults.get_user_default("Company")
	if maintenance_team:
		plan.maintenance_team = maintenance_team
	if not plan.maintenance_team:
		plan.maintenance_team = settings.get("default_maintenance_team") or frappe.db.get_value(
			"Asset Maintenance Team", {}, "name"
		)
	if not plan.maintenance_team:
		frappe.throw(
			_("No Asset Maintenance Team exists. Create one, or set a default in GDL Fleet Settings."),
			title=_("Maintenance Team Required"),
		)

	assignee = get_team_assignee(plan.maintenance_team)
	if not assignee:
		frappe.throw(
			_(
				"Asset Maintenance Team {0} has no manager or members. ERPNext requires "
				"every maintenance task to be assigned to a user."
			).format(frappe.bold(plan.maintenance_team)),
			title=_("No Assignee Available"),
		)

	existing_tasks = {t.maintenance_task: t for t in plan.get("asset_maintenance_tasks") or []}

	for rule in rules:
		task_name = rule.service_item
		row = existing_tasks.get(task_name)
		if not row:
			row = plan.append("asset_maintenance_tasks", {"maintenance_task": task_name})

		row.service_item = rule.service_item
		row.maintenance_type = rule.maintenance_type or "Preventive Maintenance"
		row.maintenance_status = row.maintenance_status or "Planned"
		# ERPNext requires an assignee on every task (asset_maintenance.py::validate)
		row.assign_to = row.assign_to or assignee
		row.start_date = row.start_date or getdate(start_date)
		row.periodicity = periodicity_for_months(rule.interval_months)
		row.interval_km = cint(rule.interval_km)

		if not row.next_due_date and cint(rule.interval_months):
			row.next_due_date = add_months(start_date, cint(rule.interval_months))
		if not row.next_due_odometer and cint(rule.interval_km):
			row.next_due_odometer = current_odometer + cint(rule.interval_km)

	plan.flags.ignore_permissions = True
	plan.save()
	return plan.name


@frappe.whitelist()
def get_due_maintenance(vehicle=None, include_upcoming=1) -> list[dict]:
	"""Tasks that are due or overdue, by DATE or by ODOMETER.

	`include_upcoming` also returns tasks inside the configured notice window, so
	the same call drives both the report and the alert.
	"""
	frappe.has_permission("Asset Maintenance", "read", throw=True)

	settings = get_settings()
	include_upcoming = cint(include_upcoming)
	notice_days = cint(settings.get("maintenance_due_notice_days"))
	notice_km = cint(settings.get("maintenance_due_notice_km"))
	today = getdate(nowdate())

	filters = {"docstatus": ("<", 2)}
	if vehicle:
		filters["vehicle"] = vehicle

	plans = frappe.get_all(
		"Asset Maintenance",
		filters=filters,
		fields=["name", "vehicle", "asset_name", "company"],
	)
	if not plans:
		return []

	odometers = {}
	results = []

	for plan in plans:
		if not plan.vehicle:
			continue
		if plan.vehicle not in odometers:
			odometers[plan.vehicle] = cint(
				frappe.db.get_value("Vehicle", plan.vehicle, "last_odometer")
			)
		current_km = odometers[plan.vehicle]

		tasks = frappe.get_all(
			"Asset Maintenance Task",
			filters={"parent": plan.name, "parenttype": "Asset Maintenance"},
			fields=[
				"name", "maintenance_task", "service_item", "maintenance_status",
				"next_due_date", "next_due_odometer", "interval_km", "periodicity",
			],
		)

		for task in tasks:
			if task.maintenance_status == "Cancelled":
				continue

			due_by_date = False
			due_by_km = False
			days_remaining = None
			km_remaining = None

			if task.next_due_date:
				days_remaining = (getdate(task.next_due_date) - today).days
				due_by_date = days_remaining <= (0 if not include_upcoming else notice_days)

			if task.next_due_odometer:
				km_remaining = cint(task.next_due_odometer) - current_km
				due_by_km = km_remaining <= (0 if not include_upcoming else notice_km)

			if not (due_by_date or due_by_km):
				continue

			overdue = (days_remaining is not None and days_remaining < 0) or (
				km_remaining is not None and km_remaining < 0
			)

			results.append(
				{
					"asset_maintenance": plan.name,
					"asset": plan.asset_name,
					"vehicle": plan.vehicle,
					"task": task.maintenance_task,
					"service_item": task.service_item,
					"current_odometer": current_km,
					"next_due_date": task.next_due_date,
					"next_due_odometer": task.next_due_odometer,
					"days_remaining": days_remaining,
					"km_remaining": km_remaining,
					"due_by_date": due_by_date,
					"due_by_km": due_by_km,
					"status": "Overdue" if overdue else "Due",
				}
			)

	results.sort(key=lambda r: (r["status"] != "Overdue", r["vehicle"]))
	return results


def update_task_after_service(
	asset_maintenance: str, task_name: str, completion_date, odometer: int
):
	"""Roll a task's next due date and odometer forward after a service."""
	plan = frappe.get_doc("Asset Maintenance", asset_maintenance)
	changed = False

	for row in plan.get("asset_maintenance_tasks") or []:
		if row.maintenance_task != task_name:
			continue

		row.last_completion_date = getdate(completion_date)
		if odometer:
			row.last_completion_odometer = cint(odometer)

		months = months_for_periodicity(row.periodicity)
		if months:
			row.next_due_date = add_months(completion_date, months)
		if cint(row.interval_km) and odometer:
			row.next_due_odometer = cint(odometer) + cint(row.interval_km)

		row.maintenance_status = "Planned"
		changed = True

	if changed:
		plan.flags.ignore_permissions = True
		plan.save()

	return changed


def months_for_periodicity(periodicity: str) -> int:
	reverse = {v: k for k, v in MONTHS_TO_PERIODICITY.items()}
	reverse.update({"Daily": 0, "Weekly": 0})
	return cint(reverse.get(periodicity))
