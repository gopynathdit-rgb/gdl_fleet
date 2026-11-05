# Copyright (c) 2026, GDL and contributors
"""Phase 14 - every fleet report must run and return the right shape."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from gdl_fleet_extension.tests import fleet_fixtures as fx
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
from gdl_fleet_extension.utils.cost import get_vehicle_cost

FLEET_REPORTS = [
	"Fleet Register",
	"Vehicle Utilization",
	"Driver Assignment History",
	"Service History",
	"Service Due",
	"Insurance and Renewal Due",
	"Movement Request Status",
	"Movement Order Register",
	"Vehicle Availability",
	"Cost by Vehicle",
	"Fuel Consumption and Performance",
	"POL Summary Register",
	# Section 5 calls this "POL Supplier / Book Balance". A Script Report takes
	# its module folder from scrub(name), which leaves a slash intact and so
	# cannot be a package path; the workspace carries the customer's wording.
	"POL Supplier and Book Balance",
]

# Standard reports reused rather than rebuilt (V2 architecture).
REUSED_STANDARD_REPORTS = [
	"General Ledger",            # erpnext, dimension-aware
	"Budget Variance Report",    # erpnext, budget_against = Vehicle
	"Profitability Analysis",    # erpnext, based_on = Accounting Dimension
]


def run(report_name, filters=None):
	report = frappe.get_doc("Report", report_name)
	return report.execute_script_report(frappe._dict(filters or {}))


class TestFleetReports(IntegrationTestCase):
	def setUp(self):
		self.filters = {
			"from_date": add_days(nowdate(), -30),
			"to_date": add_days(nowdate(), 1),
		}

	# --- registration ---------------------------------------------------------
	def test_all_reports_exist(self):
		for name in FLEET_REPORTS:
			self.assertTrue(frappe.db.exists("Report", name), f"missing report {name}")
			self.assertEqual(frappe.db.get_value("Report", name, "module"), "GDL Fleet")

	def test_reports_are_standard_script_reports(self):
		for name in FLEET_REPORTS:
			row = frappe.db.get_value(
				"Report", name, ["report_type", "is_standard"], as_dict=True
			)
			self.assertEqual(row.report_type, "Script Report")
			self.assertEqual(row.is_standard, "Yes")

	def test_reports_are_role_restricted(self):
		for name in FLEET_REPORTS:
			roles = frappe.get_all("Has Role", filters={"parent": name}, pluck="role")
			self.assertIn("Fleet Manager", roles, f"{name} has no fleet role")

	def test_out_of_scope_reports_removed(self):
		"""These are not in Fleet Mgmt.docx section 5."""
		for name in ("Tyre Performance", "Accident and Incident", "Mileage Deviation",
		             "Site Vehicle Requirement", "Vehicle Expense"):
			self.assertFalse(frappe.db.exists("Report", name), f"{name} should be removed")

	def test_standard_reports_are_reused_not_duplicated(self):
		"""These must stay standard - rebuilding them would double the maintenance."""
		for name in REUSED_STANDARD_REPORTS:
			self.assertTrue(frappe.db.exists("Report", name), f"{name} is missing")
			self.assertNotEqual(
				frappe.db.get_value("Report", name, "module"), "GDL Fleet",
				f"{name} must remain a standard report",
			)

	# --- execution ------------------------------------------------------------
	def test_every_report_runs(self):
		for name in FLEET_REPORTS:
			with self.subTest(report=name):
				result = run(name, self.filters)
				self.assertTrue(result, f"{name} returned nothing")
				columns = result[0]
				self.assertTrue(columns, f"{name} returned no columns")
				for column in columns:
					self.assertIn("fieldname", column)
					self.assertIn("label", column)

	def test_reports_run_with_a_vehicle_filter(self):
		vehicle = new_vehicle()
		vehicle.insert()
		filters = dict(self.filters, vehicle=vehicle.name)
		for name in FLEET_REPORTS:
			with self.subTest(report=name):
				self.assertTrue(run(name, filters))

	def test_reports_run_with_a_site_filter(self):
		filters = dict(self.filters, site="Gedu")
		for name in FLEET_REPORTS:
			with self.subTest(report=name):
				self.assertTrue(run(name, filters))

	# --- content --------------------------------------------------------------
	def test_utilization_reports_the_vehicle(self):
		vehicle = new_vehicle()
		vehicle.insert()
		columns, data = run("Vehicle Utilization", self.filters)[:2]
		self.assertIn(vehicle.name, [r["vehicle"] for r in data])

	def test_cost_analysis_documents_what_it_includes(self):
		result = run("Cost by Vehicle", self.filters)
		self.assertGreaterEqual(len(result), 3, "no explanatory message returned")
		message = result[2]
		self.assertIn("General Ledger", message)
		self.assertIn("double counted", message)

	def test_cost_per_km_is_blank_without_distance(self):
		vehicle = new_vehicle()
		vehicle.insert()
		rows = get_vehicle_cost(
			self.filters["from_date"], self.filters["to_date"], vehicle=vehicle.name
		)
		row = rows[0]
		self.assertEqual(row["distance_km"], 0)
		self.assertIsNone(row["cost_per_km"], "cost per km must not be faked")

	def test_cost_comes_only_from_the_ledger(self):
		"""No parallel cost table may exist."""
		for name in ("Vehicle Cost", "Fleet Cost", "Vehicle Cost Entry"):
			self.assertFalse(frappe.db.exists("DocType", name))


class TestMaintenanceCostReportDates(IntegrationTestCase):
	"""Asset Repair dates with a Datetime, Asset Maintenance Log with a Date."""

	def setUp(self):
		if not fx.company_exists():
			self.skipTest(f"{fx.COMPANY} not on this site")

	def test_runs_with_both_date_types_present(self):
		asset = fx.make_asset()
		vehicle = new_vehicle(company=fx.COMPANY)
		vehicle.asset = asset.name
		vehicle.insert()

		repair = frappe.get_doc({
			"doctype": "Asset Repair", "asset": asset.name, "company": fx.COMPANY,
			"failure_date": frappe.utils.now_datetime(),
			"completion_date": frappe.utils.now_datetime(),
			# erpnext refuses to submit a repair that is still Pending
			"repair_status": "Completed",
			"description": "Mixed date check", "labour_cost": 1000,
		})
		repair.insert()
		repair.submit()

		team = fx.make_maintenance_team()
		from gdl_fleet_extension.utils.maintenance import create_maintenance_plan

		plan_name = create_maintenance_plan(vehicle.name, maintenance_team=team)
		plan = frappe.get_doc("Asset Maintenance", plan_name)
		task = plan.asset_maintenance_tasks[0]
		log = frappe.get_doc({
			"doctype": "Asset Maintenance Log", "asset_maintenance": plan_name,
			"asset_name": plan.asset_name, "task": task.name,
			"task_name": task.maintenance_task, "completion_date": nowdate(),
			"maintenance_status": "Completed", "odometer": 2500, "labour_cost": 500,
		})
		log.insert()
		log.submit()

		columns, data = run("Service History", {
			"from_date": add_days(nowdate(), -30), "to_date": add_days(nowdate(), 1),
		})[:2]
		self.assertTrue(columns)
		doctypes = {row["doctype"] for row in data}
		self.assertIn("Asset Repair", doctypes)
		self.assertIn("Asset Maintenance Log", doctypes)
