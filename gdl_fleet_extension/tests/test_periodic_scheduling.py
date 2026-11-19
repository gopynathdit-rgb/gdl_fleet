# Copyright (c) 2026, GDL and contributors
"""Periodic maintenance scheduling without an ERPNext maintenance plan.

Document §2.1.1.4:
  "Track the next service date or odometer based on the periodic services
   selected."
  "The system should produce 'Service Due Soon' and 'Service Overdue' lists
   based on either date or odometer threshold."

Both were dead in practice. Next due was only computed for a service raised
from an Asset Maintenance PLAN, and the due list only read plans - while GDL
has none and cannot have any, because a plan needs an Asset and no vehicle is
linked to one. Every service record carried a blank next due and Service Due
returned nothing at all.

The schedule now comes from GDL's own Maintenance Rules, and the due list is
built from the service records.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, getdate, nowdate

from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
from gdl_fleet_extension.utils.maintenance import get_due_maintenance


def a_rule():
	"""A live rule with both a km and a month interval."""
	settings = frappe.get_single("GDL Fleet Settings")
	for row in settings.get("maintenance_rules") or []:
		if row.is_active and row.interval_km and row.interval_months and not row.vehicle_type:
			return row
	return None


class TestNextDueComesFromTheRules(IntegrationTestCase):
	def setUp(self):
		self.rule = a_rule()
		if not self.rule:
			self.skipTest("no maintenance rule with both intervals on this site")
		self.vehicle = new_vehicle(last_odometer=10000)
		self.vehicle.insert()

	def service(self, service_items, odometer=10000, submit=False, **kwargs):
		values = {
			"doctype": "Asset Maintenance Log",
			"vehicle": self.vehicle.name,
			"maintenance_status": "Completed",
			"completion_date": nowdate(),
			"odometer": odometer,
			"service_items": [{"service_item": s, "qty": 1, "cost": 100}
			                  for s in service_items],
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def test_a_service_records_its_own_next_due(self):
		doc = self.service([self.rule.service_item])
		self.assertEqual(
			getdate(doc.next_due_date),
			getdate(add_months(nowdate(), self.rule.interval_months)))
		self.assertEqual(doc.next_due_odometer, 10000 + self.rule.interval_km)

	def test_the_earliest_item_in_the_visit_wins(self):
		"""A visit covering several items is next needed when the FIRST falls
		due, not the last."""
		settings = frappe.get_single("GDL Fleet Settings")
		rules = [r for r in settings.get("maintenance_rules") or []
		         if r.is_active and r.interval_km and not r.vehicle_type]
		if len(rules) < 2:
			self.skipTest("need two rules")
		shortest = min(rules, key=lambda r: r.interval_km)
		longest = max(rules, key=lambda r: r.interval_km)
		if shortest.interval_km == longest.interval_km:
			self.skipTest("rules all share one interval")

		doc = self.service([longest.service_item, shortest.service_item])
		self.assertEqual(doc.next_due_odometer, 10000 + shortest.interval_km,
		                 "the later item set the schedule")

	def test_a_service_type_with_no_rule_schedules_nothing(self):
		doc = self.service([])
		self.assertIsNone(doc.next_due_date)
		self.assertEqual(doc.next_due_odometer, 0)

	def test_a_plan_still_owns_its_own_schedule(self):
		"""Where ERPNext's own machinery is in use it is not overridden."""
		import inspect

		from gdl_fleet_extension.overrides import asset_maintenance
		source = inspect.getsource(asset_maintenance.set_next_due_from_rules)
		self.assertIn('doc.get("asset_maintenance") and doc.get("task")', source)


class TestTheDueAndOverdueLists(IntegrationTestCase):
	def setUp(self):
		self.rule = a_rule()
		if not self.rule:
			self.skipTest("no maintenance rule with both intervals on this site")
		self.vehicle = new_vehicle(last_odometer=10000)
		self.vehicle.insert()

	def submitted_service(self, next_due_date=None, next_due_odometer=None):
		doc = frappe.get_doc({
			"doctype": "Asset Maintenance Log",
			"vehicle": self.vehicle.name,
			"maintenance_status": "Completed",
			"completion_date": nowdate(),
			"odometer": 10000,
			"service_items": [{"service_item": self.rule.service_item,
			                   "qty": 1, "cost": 100}],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		if next_due_date is not None:
			doc.db_set("next_due_date", next_due_date, update_modified=False)
		if next_due_odometer is not None:
			doc.db_set("next_due_odometer", next_due_odometer, update_modified=False)
		return doc

	def rows(self):
		return [r for r in get_due_maintenance()
		        if r["vehicle"] == self.vehicle.name]

	def test_a_service_far_from_due_is_not_listed(self):
		self.submitted_service(next_due_date=add_days(nowdate(), 365),
		                       next_due_odometer=99999)
		self.assertEqual(self.rows(), [])

	def test_due_soon_by_date_is_listed(self):
		"""Inside the configured notice window."""
		self.submitted_service(next_due_date=add_days(nowdate(), 3),
		                       next_due_odometer=99999)
		rows = self.rows()
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["status"], "Due")
		self.assertTrue(rows[0]["due_by_date"])

	def test_overdue_by_date_is_listed_as_overdue(self):
		self.submitted_service(next_due_date=add_days(nowdate(), -5),
		                       next_due_odometer=99999)
		rows = self.rows()
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["status"], "Overdue")
		self.assertEqual(rows[0]["days_remaining"], -5)

	def test_due_by_odometer_alone_is_listed(self):
		"""Either threshold - the document says "date or odometer"."""
		self.submitted_service(next_due_date=add_days(nowdate(), 365),
		                       next_due_odometer=10100)
		rows = self.rows()
		self.assertEqual(len(rows), 1, "a vehicle close on distance was missed")
		self.assertTrue(rows[0]["due_by_km"])

	def test_overdue_by_odometer_is_overdue(self):
		self.submitted_service(next_due_date=add_days(nowdate(), 365),
		                       next_due_odometer=9000)
		rows = self.rows()
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["status"], "Overdue")

	def test_only_the_latest_service_speaks_for_a_vehicle(self):
		"""An older service is superseded; it must not raise a stale alert."""
		self.submitted_service(next_due_date=add_days(nowdate(), -30),
		                       next_due_odometer=99999)
		self.submitted_service(next_due_date=add_days(nowdate(), 365),
		                       next_due_odometer=99999)
		self.assertEqual(self.rows(), [],
		                 "a superseded service is still being reported as due")

	def test_the_report_runs_on_this(self):
		from frappe.desk.query_report import run

		self.submitted_service(next_due_date=add_days(nowdate(), -1),
		                       next_due_odometer=99999)
		result = run("Service Due", filters={})
		self.assertTrue(result["columns"])
		self.assertTrue(any(self.vehicle.name in str(row) for row in result["result"]),
		                "the vehicle is due but the report does not show it")
