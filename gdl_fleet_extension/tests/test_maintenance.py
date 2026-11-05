# Copyright (c) 2026, GDL and contributors
"""Phase 7 - preventive and corrective vehicle maintenance on standard ERPNext Assets."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, cint, flt, getdate, nowdate

from gdl_fleet_extension.tests import fleet_fixtures as fx
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
from gdl_fleet_extension.utils.maintenance import (
	create_maintenance_plan,
	get_due_maintenance,
	get_maintenance_rules,
	periodicity_for_months,
)


class TestVehicleMaintenance(IntegrationTestCase):
	def setUp(self):
		if not fx.company_exists():
			self.skipTest(f"{fx.COMPANY} not on this site")
		self.team = fx.make_maintenance_team()
		self.clear_settings_cache()
		self._rules_snapshot = self.snapshot_rules()

	def tearDown(self):
		# frappe's IntegrationTestCase rolls back once per CLASS, not per test, so
		# a test that edits GDL Fleet Settings would otherwise leak its change into
		# every test that runs after it alphabetically. Restore what we changed.
		if self.snapshot_rules() != self._rules_snapshot:
			self.restore_rules(self._rules_snapshot)
		self.clear_settings_cache()

	@staticmethod
	def clear_settings_cache():
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	@staticmethod
	def snapshot_rules():
		settings = frappe.get_single("GDL Fleet Settings")
		return [
			(r.service_item, cint(r.interval_km), cint(r.interval_months), cint(r.is_active))
			for r in settings.get("maintenance_rules") or []
		]

	@classmethod
	def restore_rules(cls, snapshot):
		settings = frappe.get_single("GDL Fleet Settings")
		settings.set("maintenance_rules", [])
		for service_item, interval_km, interval_months, is_active in snapshot:
			settings.append(
				"maintenance_rules",
				{
					"service_item": service_item,
					"interval_km": interval_km,
					"interval_months": interval_months,
					"is_active": is_active,
					"maintenance_type": "Preventive Maintenance",
				},
			)
		settings.flags.ignore_permissions = True
		settings.save()
		cls.clear_settings_cache()

	def make_vehicle_with_asset(self, last_odometer=10000, **kwargs):
		asset = fx.make_asset()
		vehicle = new_vehicle(company=fx.COMPANY, last_odometer=last_odometer, **kwargs)
		vehicle.asset = asset.name
		vehicle.insert()
		return vehicle, asset

	# --- configuration is data, not code -------------------------------------
	def test_intervals_are_configuration(self):
		rules = {r.service_item: r for r in get_maintenance_rules()}
		self.assertEqual(cint(rules["Engine Oil"].interval_km), 7500)
		self.assertEqual(cint(rules["Engine Oil"].interval_months), 6)
		self.assertEqual(cint(rules["Fuel Filter"].interval_km), 10000)
		self.assertEqual(cint(rules["Brake Fluid"].interval_km), 40000)
		self.assertEqual(cint(rules["Gear Oil"].interval_months), 24)
		self.assertEqual(cint(rules["Tyre Replacement / Rotation"].interval_km), 20000)

	def test_rules_match_the_twelve_items_in_section_4_4(self):
		"""The bare "Tyre" rule of the earlier scope is superseded, not carried."""
		items = {r.service_item for r in get_maintenance_rules()}
		self.assertEqual(len(items), 12)
		self.assertNotIn("Tyre", items)
		self.assertIn("Tyre Replacement / Rotation", items)

	def test_rules_can_be_changed_without_code(self):
		settings = frappe.get_single("GDL Fleet Settings")
		row = next(r for r in settings.maintenance_rules if r.service_item == "Engine Oil")
		row.interval_km = 9000
		settings.flags.ignore_permissions = True
		settings.save()

		rules = {r.service_item: r for r in get_maintenance_rules()}
		self.assertEqual(cint(rules["Engine Oil"].interval_km), 9000)

	def test_new_rule_can_be_added(self):
		if not frappe.db.exists("Vehicle Service Item", "_Test Air Filter"):
			frappe.get_doc(
				{"doctype": "Vehicle Service Item", "service_item": "_Test Air Filter"}
			).insert()

		settings = frappe.get_single("GDL Fleet Settings")
		settings.append(
			"maintenance_rules",
			{"service_item": "_Test Air Filter", "interval_km": 15000, "interval_months": 12,
			 "is_active": 1},
		)
		settings.flags.ignore_permissions = True
		settings.save()

		self.assertIn("_Test Air Filter", {r.service_item for r in get_maintenance_rules()})

	def test_inactive_rule_is_ignored(self):
		settings = frappe.get_single("GDL Fleet Settings")
		row = next(r for r in settings.maintenance_rules if r.service_item == "Gear Oil")
		row.is_active = 0
		settings.flags.ignore_permissions = True
		settings.save()

		self.assertNotIn("Gear Oil", {r.service_item for r in get_maintenance_rules()})

	def test_month_interval_maps_to_standard_periodicity(self):
		self.assertEqual(periodicity_for_months(6), "Half-yearly")
		self.assertEqual(periodicity_for_months(12), "Yearly")
		self.assertEqual(periodicity_for_months(24), "2 Yearly")

	# --- preventive plan on standard Asset Maintenance ------------------------
	def test_preventive_plan_uses_standard_asset_maintenance(self):
		vehicle, asset = self.make_vehicle_with_asset(last_odometer=10000)
		plan_name = create_maintenance_plan(vehicle.name, maintenance_team=self.team)

		plan = frappe.get_doc("Asset Maintenance", plan_name)
		self.assertEqual(plan.doctype, "Asset Maintenance")
		self.assertEqual(plan.asset_name, asset.name)
		self.assertEqual(plan.vehicle, vehicle.name)
		self.assertTrue(len(plan.asset_maintenance_tasks) >= 5)

	def test_plan_sets_both_km_and_date_due(self):
		vehicle, _asset = self.make_vehicle_with_asset(last_odometer=10000)
		plan = frappe.get_doc("Asset Maintenance", create_maintenance_plan(vehicle.name, maintenance_team=self.team))

		oil = next(t for t in plan.asset_maintenance_tasks if t.maintenance_task == "Engine Oil")
		self.assertEqual(cint(oil.interval_km), 7500)
		self.assertEqual(cint(oil.next_due_odometer), 17500)   # 10000 + 7500
		self.assertEqual(oil.periodicity, "Half-yearly")
		self.assertEqual(getdate(oil.next_due_date), getdate(add_months(nowdate(), 6)))

	def test_plan_requires_an_asset(self):
		vehicle = new_vehicle(company=fx.COMPANY)
		vehicle.insert()
		self.assertRaises(frappe.ValidationError, create_maintenance_plan, vehicle.name, None, self.team)

	def test_vehicle_creation_not_blocked_without_asset(self):
		"""Asset stays optional - Finance may not have created them yet."""
		vehicle = new_vehicle(company=fx.COMPANY)
		vehicle.insert()
		self.assertTrue(vehicle.name)
		self.assertFalse(vehicle.asset)

	def test_no_duplicate_maintenance_doctype(self):
		for name in ("Fleet Maintenance", "GDL Maintenance", "Vehicle Maintenance"):
			self.assertFalse(frappe.db.exists("DocType", name), f"{name} should not exist")

	def test_maintenance_schedule_not_used(self):
		"""Customer-facing Maintenance Schedule must stay out of the fleet flow."""
		self.assertIsNone(frappe.get_meta("Maintenance Schedule").get_field("vehicle"))

	# --- due detection --------------------------------------------------------
	def test_km_based_due(self):
		vehicle, _asset = self.make_vehicle_with_asset(last_odometer=10000)
		create_maintenance_plan(vehicle.name, maintenance_team=self.team)

		# drive past the 17,500 km oil-change threshold
		vehicle.db_set("last_odometer", 18000)

		due = get_due_maintenance(vehicle.name)
		oil = next(d for d in due if d["task"] == "Engine Oil")
		self.assertTrue(oil["due_by_km"])
		self.assertEqual(oil["status"], "Overdue")
		self.assertEqual(oil["km_remaining"], -500)

	def test_km_due_within_notice_window(self):
		vehicle, _asset = self.make_vehicle_with_asset(last_odometer=10000)
		create_maintenance_plan(vehicle.name, maintenance_team=self.team)
		vehicle.db_set("last_odometer", 17200)  # 300 km short, notice window is 500

		due = get_due_maintenance(vehicle.name)
		oil = next(d for d in due if d["task"] == "Engine Oil")
		self.assertTrue(oil["due_by_km"])
		self.assertEqual(oil["status"], "Due")

	def test_not_due_outside_the_window(self):
		vehicle, _asset = self.make_vehicle_with_asset(last_odometer=10000)
		create_maintenance_plan(vehicle.name, maintenance_team=self.team)

		due = get_due_maintenance(vehicle.name)
		self.assertEqual([d for d in due if d["task"] == "Engine Oil"], [])

	def test_date_based_due(self):
		vehicle, _asset = self.make_vehicle_with_asset(last_odometer=10000)
		plan = frappe.get_doc("Asset Maintenance", create_maintenance_plan(vehicle.name, maintenance_team=self.team))

		for row in plan.asset_maintenance_tasks:
			if row.maintenance_task == "Brake Fluid":
				row.next_due_date = add_days(nowdate(), -5)
				row.next_due_odometer = 0
		plan.flags.ignore_permissions = True
		plan.save()

		due = get_due_maintenance(vehicle.name)
		brake = next(d for d in due if d["task"] == "Brake Fluid")
		self.assertTrue(brake["due_by_date"])
		self.assertEqual(brake["status"], "Overdue")

	def test_whichever_comes_first_wins(self):
		"""A task due on distance only must still be reported."""
		vehicle, _asset = self.make_vehicle_with_asset(last_odometer=10000)
		plan = frappe.get_doc("Asset Maintenance", create_maintenance_plan(vehicle.name, maintenance_team=self.team))
		for row in plan.asset_maintenance_tasks:
			if row.maintenance_task == "Engine Oil":
				row.next_due_date = add_days(nowdate(), 900)  # far away in time
		plan.flags.ignore_permissions = True
		plan.save()
		vehicle.db_set("last_odometer", 20000)

		oil = next(d for d in get_due_maintenance(vehicle.name) if d["task"] == "Engine Oil")
		self.assertTrue(oil["due_by_km"])
		self.assertFalse(oil["due_by_date"])

	# --- completing a service -------------------------------------------------
	def make_log(self, vehicle, plan_name, task_label, odometer, **kwargs):
		plan = frappe.get_doc("Asset Maintenance", plan_name)
		task = next(t for t in plan.asset_maintenance_tasks if t.maintenance_task == task_label)

		values = {
			"doctype": "Asset Maintenance Log",
			"asset_maintenance": plan_name,
			"asset_name": plan.asset_name,
			"task": task.name,
			"task_name": task_label,
			"maintenance_type": task.maintenance_type,
			"periodicity": task.periodicity,
			"due_date": task.next_due_date,
			"completion_date": nowdate(),
			"maintenance_status": "Completed",
			"odometer": odometer,
			"actions_performed": "Serviced",
		}
		values.update(kwargs)
		log = frappe.get_doc(values)
		log.insert()
		log.submit()
		return log

	def test_service_rolls_next_due_forward(self):
		vehicle, _asset = self.make_vehicle_with_asset(last_odometer=10000)
		plan_name = create_maintenance_plan(vehicle.name, maintenance_team=self.team)
		vehicle.db_set("last_odometer", 17500)

		log = self.make_log(vehicle, plan_name, "Engine Oil", 17500)

		plan = frappe.get_doc("Asset Maintenance", plan_name)
		oil = next(t for t in plan.asset_maintenance_tasks if t.maintenance_task == "Engine Oil")
		self.assertEqual(cint(oil.next_due_odometer), 25000)  # 17500 + 7500
		self.assertEqual(getdate(oil.next_due_date), getdate(add_months(nowdate(), 6)))
		self.assertEqual(cint(oil.last_completion_odometer), 17500)

		log.reload()
		self.assertEqual(cint(log.next_due_odometer), 25000)

	def test_log_vehicle_derived_from_asset(self):
		vehicle, _asset = self.make_vehicle_with_asset(last_odometer=10000)
		plan_name = create_maintenance_plan(vehicle.name, maintenance_team=self.team)
		log = self.make_log(vehicle, plan_name, "Engine Oil", 12000)
		self.assertEqual(log.vehicle, vehicle.name)

	def test_log_costs(self):
		vehicle, _asset = self.make_vehicle_with_asset(last_odometer=10000)
		plan_name = create_maintenance_plan(vehicle.name, maintenance_team=self.team)
		log = self.make_log(
			vehicle, plan_name, "Engine Oil", 12000, labour_cost=1500, parts_cost=3500
		)
		self.assertEqual(flt(log.total_cost), 5000.0)

	def test_log_cost_center_and_project(self):
		cost_center = frappe.db.get_value(
			"Cost Center", {"company": fx.COMPANY, "is_group": 0}, "name"
		)
		vehicle, _asset = self.make_vehicle_with_asset(last_odometer=10000)
		plan_name = create_maintenance_plan(vehicle.name, maintenance_team=self.team)
		log = self.make_log(vehicle, plan_name, "Engine Oil", 12000, cost_center=cost_center)
		self.assertEqual(log.cost_center, cost_center)

	def test_log_advances_vehicle_odometer(self):
		vehicle, _asset = self.make_vehicle_with_asset(last_odometer=10000)
		plan_name = create_maintenance_plan(vehicle.name, maintenance_team=self.team)
		self.make_log(vehicle, plan_name, "Engine Oil", 16000)
		self.assertEqual(
			cint(frappe.db.get_value("Vehicle", vehicle.name, "last_odometer")), 16000
		)

	def test_log_rejects_backwards_odometer(self):
		vehicle, _asset = self.make_vehicle_with_asset(last_odometer=20000)
		plan_name = create_maintenance_plan(vehicle.name, maintenance_team=self.team)
		plan = frappe.get_doc("Asset Maintenance", plan_name)
		task = next(t for t in plan.asset_maintenance_tasks if t.maintenance_task == "Engine Oil")

		log = frappe.get_doc({
			"doctype": "Asset Maintenance Log", "asset_maintenance": plan_name,
			"asset_name": plan.asset_name, "task": task.name, "task_name": "Engine Oil",
			"completion_date": nowdate(), "maintenance_status": "Completed", "odometer": 500,
		})
		self.assertRaises(frappe.ValidationError, log.insert)

	# --- corrective repair on standard Asset Repair ---------------------------
	def make_repair(self, vehicle, asset, **kwargs):
		values = {
			"doctype": "Asset Repair",
			"asset": asset.name,
			"company": fx.COMPANY,
			"failure_date": frappe.utils.now_datetime(),
			"repair_status": "Pending",
			"description": "Brake overhaul",
			"maintenance_category": "Corrective",
		}
		values.update(kwargs)
		repair = frappe.get_doc(values)
		repair.insert()
		return repair

	def test_corrective_repair_uses_standard_asset_repair(self):
		vehicle, asset = self.make_vehicle_with_asset(last_odometer=10000)
		repair = self.make_repair(vehicle, asset, repair_cost=8000, odometer=11000)
		self.assertEqual(repair.doctype, "Asset Repair")
		self.assertEqual(repair.vehicle, vehicle.name)
		self.assertEqual(repair.maintenance_category, "Corrective")

	def test_repair_vehicle_derived_from_asset(self):
		vehicle, asset = self.make_vehicle_with_asset(last_odometer=10000)
		repair = self.make_repair(vehicle, asset)
		self.assertEqual(repair.vehicle, vehicle.name)

	def test_repair_carries_standard_cost_and_downtime_fields(self):
		meta = frappe.get_meta("Asset Repair")
		for fieldname in ("repair_cost", "total_repair_cost", "downtime", "stock_items",
		                  "cost_center", "project", "capitalize_repair_cost"):
			self.assertTrue(meta.get_field(fieldname), f"standard field {fieldname} missing")

	def test_repair_fleet_fields_added(self):
		meta = frappe.get_meta("Asset Repair")
		for fieldname in ("maintenance_category", "service_item", "service_provider",
		                  "odometer", "labour_cost", "next_service_date",
		                  "next_service_odometer"):
			self.assertTrue(meta.get_field(fieldname), f"custom field {fieldname} missing")

	def test_repair_has_vehicle_accounting_dimension(self):
		"""Supplied by Phase 3, not re-declared here."""
		field = frappe.get_meta("Asset Repair").get_field("vehicle")
		self.assertEqual(field.options, "Vehicle")
		owners = frappe.get_all(
			"Custom Field", filters={"dt": "Asset Repair", "fieldname": "vehicle"},
			fields=["module"],
		)
		self.assertEqual(len(owners), 1, "vehicle must not be declared twice on Asset Repair")

	def test_repair_next_service_fields(self):
		vehicle, asset = self.make_vehicle_with_asset(last_odometer=10000)
		repair = self.make_repair(
			vehicle, asset, odometer=11000,
			next_service_date=add_months(nowdate(), 6), next_service_odometer=18500,
		)
		self.assertEqual(cint(repair.next_service_odometer), 18500)

	def test_repair_rejects_backwards_odometer(self):
		vehicle, asset = self.make_vehicle_with_asset(last_odometer=20000)
		repair = frappe.get_doc({
			"doctype": "Asset Repair", "asset": asset.name, "company": fx.COMPANY,
			"failure_date": frappe.utils.now_datetime(), "repair_status": "Pending",
			"description": "x", "odometer": 100,
		})
		self.assertRaises(frappe.ValidationError, repair.insert)

	# --- permissions ----------------------------------------------------------
	def test_settings_permissions(self):
		roles = {p.role for p in frappe.get_meta("GDL Fleet Settings").permissions}
		self.assertIn("Fleet Administrator", roles)
		writers = {p.role for p in frappe.get_meta("GDL Fleet Settings").permissions if p.write}
		self.assertNotIn("Fleet Manager", writers)

	# --- phases 1-6 still intact ---------------------------------------------
	def test_vehicle_and_log_still_work(self):
		vehicle, _asset = self.make_vehicle_with_asset(last_odometer=10000)
		employee = frappe.db.get_value("Employee", {}, "name")
		if not employee:
			self.skipTest("no Employee")

		log = frappe.get_doc({
			"doctype": "Vehicle Log", "license_plate": vehicle.name, "employee": employee,
			"date": nowdate(), "odometer": 10500, "usage_type": "Official", "place_to_travel": "Local",
		})
		log.insert()
		log.submit()
		self.assertEqual(cint(log.distance_travelled), 500)
