# Copyright (c) 2026, GDL and contributors
"""Raising a maintenance plan against a vehicle.

GDL started using ERPNext's Asset Maintenance for periodic servicing and hit
two refusals in a row:

    "Value missing for Asset Maintenance Log: Vehicle"
    "Row #1: Please assign task to a member."

and asked for the plan on the fleet menu: "need this menu in under Vehicle
Service and Maintenance", "i done need assign some one in line item just
select maintance team only".
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle


def a_team():
	return frappe.db.get_value("Asset Maintenance Team", {}, "name")


class TestAPlanCanBeRaised(IntegrationTestCase):
	def setUp(self):
		self.team = a_team()
		if not self.team:
			self.skipTest("no Asset Maintenance Team on this site")
		# A plan is named after its Asset, so one Asset carries only one -
		# picking an existing Asset skipped every test on a site whose assets
		# already have plans, which is how this file first passed vacuously.
		self.asset = self.make_asset()
		self.vehicle = new_vehicle(last_odometer=1000)
		self.vehicle.insert()

	def make_asset(self):
		"""An Asset of this run's own, so the plan has somewhere to live."""
		template = frappe.get_all(
			"Asset", filters={"docstatus": 1},
			fields=["item_code", "asset_category", "company", "location",
			        "purchase_date", "available_for_use_date"], limit=1)
		if not template:
			self.skipTest("no Asset on this site to copy the shape from")

		values = template[0]
		asset = frappe.get_doc({
			"doctype": "Asset",
			"asset_name": f"GDL Test Asset {frappe.generate_hash(length=6)}",
			"item_code": values.item_code,
			"asset_category": values.asset_category,
			"company": values.company,
			"location": values.location,
			"purchase_date": values.purchase_date,
			"available_for_use_date": values.available_for_use_date,
			"gross_purchase_amount": 100000,
			"purchase_amount": 100000,
			"net_purchase_amount": 100000,
			"calculate_depreciation": 0,
			"is_existing_asset": 1,
		})
		asset.flags.ignore_permissions = True
		asset.insert()
		asset.submit()
		return asset.name

	def plan(self, tasks=None, **kwargs):
		values = {
			"doctype": "Asset Maintenance",
			"asset_name": self.asset,
			"vehicle": self.vehicle.name,
			"company": frappe.db.get_value("Asset", self.asset, "company"),
			"maintenance_team": self.team,
			"asset_maintenance_tasks": tasks if tasks is not None else [{
				"maintenance_task": "Engine Oil",
				"maintenance_status": "Planned",
				"start_date": nowdate(),
				"periodicity": "Half-yearly",
			}],
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc

	def test_a_plan_saves_without_naming_anyone_on_the_line(self):
		"""GDL select the team and nothing else."""
		plan = self.plan()
		self.assertTrue(plan.name)

	def test_the_task_is_assigned_to_the_team(self):
		"""ERPNext refuses a task with no assignee, and the assignee is who
		its reminders reach - so the team answers for it rather than the rule
		being switched off."""
		plan = self.plan()
		assignee = plan.asset_maintenance_tasks[0].assign_to
		self.assertTrue(assignee, "nobody was assigned, so the reminder has no one to reach")
		team = frappe.get_doc("Asset Maintenance Team", self.team)
		members = {m.team_member for m in team.maintenance_team_members}
		self.assertIn(assignee, members | {team.maintenance_manager})

	def test_a_person_named_on_the_line_is_left_alone(self):
		"""Filling a blank is a convenience, not an override."""
		team = frappe.get_doc("Asset Maintenance Team", self.team)
		chosen = [m.team_member for m in team.maintenance_team_members][-1]
		plan = self.plan(tasks=[{
			"maintenance_task": "Engine Oil", "maintenance_status": "Planned",
			"start_date": nowdate(), "periodicity": "Half-yearly",
			"assign_to": chosen,
		}])
		self.assertEqual(plan.asset_maintenance_tasks[0].assign_to, chosen)

	def test_administrator_is_not_chosen_when_a_real_member_exists(self):
		"""frappe resolves Administrator to its email and then cannot find a
		User by that name - "Could not find Allocated To: ...". """
		team = frappe.get_doc("Asset Maintenance Team", self.team)
		others = [m.team_member for m in team.maintenance_team_members
		          if m.team_member != "Administrator"]
		if not others:
			self.skipTest("the team has only Administrator")
		self.assertNotEqual(self.plan().asset_maintenance_tasks[0].assign_to,
		                    "Administrator")

	def test_the_log_it_creates_carries_the_vehicle(self):
		"""`vehicle` is mandatory on a service record, and ERPNext's
		sync_maintenance_tasks creates logs without one. The plan knows it."""
		plan = self.plan()
		logs = frappe.get_all("Asset Maintenance Log",
		                      filters={"asset_maintenance": plan.name},
		                      fields=["name", "vehicle"])
		self.assertTrue(logs, "the plan created no log at all")
		for log in logs:
			self.assertEqual(log.vehicle, self.vehicle.name,
			                 "the log has no vehicle, so it joins no history")


class TestThePlanFillsTheLogItRaises(IntegrationTestCase):
	"""GDL: "asset maintance log created but some details need update
	automatily update cost center and need which one is planed like engine oil
	or air filter like that."

	ERPNext creates one log per scheduled task carrying little more than the
	task's name - no dimensions, and no sign on the form of WHICH service was
	planned.
	"""

	def setUp(self):
		self.team = a_team()
		if not self.team:
			self.skipTest("no Asset Maintenance Team on this site")
		self.vehicle = new_vehicle(last_odometer=1000)
		self.vehicle.insert()
		self.cost_center = frappe.db.get_value("Cost Center", {"is_group": 0}, "name")
		if self.cost_center:
			frappe.db.set_value("Vehicle", self.vehicle.name, "cost_center",
			                    self.cost_center, update_modified=False)

	def logs_from_a_plan(self, tasks):
		asset = TestAPlanCanBeRaised.make_asset(self)
		plan = frappe.get_doc({
			"doctype": "Asset Maintenance",
			"asset_name": asset,
			"vehicle": self.vehicle.name,
			"company": frappe.db.get_value("Asset", asset, "company"),
			"maintenance_team": self.team,
			"asset_maintenance_tasks": tasks,
		})
		plan.flags.ignore_permissions = True
		plan.insert()
		return [frappe.get_doc("Asset Maintenance Log", n) for n in frappe.get_all(
			"Asset Maintenance Log", filters={"asset_maintenance": plan.name},
			pluck="name")]

	def a_task(self, service):
		return {"maintenance_task": service, "maintenance_status": "Planned",
		        "start_date": nowdate(), "periodicity": "Half-yearly"}

	def test_the_log_says_which_service_is_planned(self):
		service = frappe.db.get_value("Vehicle Service Item", {}, "name")
		if not service:
			self.skipTest("no Vehicle Service Item on this site")
		logs = self.logs_from_a_plan([self.a_task(service)])
		self.assertTrue(logs, "the plan raised no log")
		listed = [r.service_item for log in logs for r in log.service_items]
		self.assertIn(service, listed,
		              "the log does not say which service was planned")

	def test_each_task_gets_its_own_service(self):
		"""Two tasks must not both read as the first one."""
		services = frappe.get_all("Vehicle Service Item", pluck="name", limit=2)
		if len(services) < 2:
			self.skipTest("need two service types")
		logs = self.logs_from_a_plan([self.a_task(s) for s in services])
		listed = {r.service_item for log in logs for r in log.service_items}
		self.assertEqual(listed, set(services))

	def test_the_cost_centre_comes_from_the_vehicle(self):
		service = frappe.db.get_value("Vehicle Service Item", {}, "name")
		if not (service and self.cost_center):
			self.skipTest("no service type or cost centre on this site")
		logs = self.logs_from_a_plan([self.a_task(service)])
		self.assertEqual(logs[0].cost_center, self.cost_center)

	def test_nothing_already_entered_is_overwritten(self):
		"""Filling a blank is a convenience, not an override."""
		service = frappe.db.get_value("Vehicle Service Item", {}, "name")
		if not service:
			self.skipTest("no Vehicle Service Item on this site")
		logs = self.logs_from_a_plan([self.a_task(service)])
		log = logs[0]
		log.cost_center = None
		other = frappe.db.get_value(
			"Cost Center", {"is_group": 0, "name": ("!=", self.cost_center)}, "name")
		if other:
			log.cost_center = other
			log.flags.ignore_permissions = True
			log.save()
			self.assertEqual(log.cost_center, other,
			                 "a cost centre someone chose was overwritten")
		self.assertEqual(len(log.service_items), 1,
		                 "re-saving added a second service row")


class TestThePlanIsReachable(IntegrationTestCase):
	def test_it_is_on_the_maintenance_card(self):
		workspace = frappe.get_doc("Workspace", "GDL Fleet")
		card = None
		for link in workspace.links:
			if link.type == "Card Break":
				card = link.label
			elif link.link_to == "Asset Maintenance":
				self.assertEqual(card, "Vehicle Service and Maintenance")
				return
		self.fail("Asset Maintenance is not on the workspace")

	def test_the_people_who_service_the_fleet_can_open_it(self):
		"""A menu entry nobody may open is not a menu entry -
		desktop.get_links() filters on permission alone."""
		roles = {p.role for p in frappe.get_meta("Asset Maintenance").permissions if p.read}
		for role in ("Fleet Maintenance User", "Fleet Administrator"):
			self.assertIn(role, roles)
