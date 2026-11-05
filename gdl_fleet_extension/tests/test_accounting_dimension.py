# Copyright (c) 2026, GDL and contributors
"""Phase 3 - Vehicle as a standard ERPNext Accounting Dimension."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, nowdate

from gdl_fleet_extension.setup.accounting_dimension import (
	VEHICLE_FIELDNAME,
	find_duplicate_vehicle_fields,
	get_dimension_doctypes,
	missing_dimension_doctypes,
	verify_vehicle_dimension,
)
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle

ACCOUNTING_COMPANY = "GDL (Demo)"


def get_accounting_company():
	if frappe.db.exists("Company", ACCOUNTING_COMPANY):
		return ACCOUNTING_COMPANY
	return None


def get_leaf_account(company, root_type):
	return frappe.db.get_value(
		"Account",
		{"company": company, "is_group": 0, "root_type": root_type, "disabled": 0},
		"name",
	)


class TestVehicleAccountingDimension(IntegrationTestCase):
	# --- the dimension itself ------------------------------------------------
	def test_dimension_exists(self):
		name = frappe.db.get_value(
			"Accounting Dimension", {"document_type": "Vehicle"}, ["name"]
		)
		self.assertTrue(name, "Vehicle Accounting Dimension was not created")

		dim = frappe.get_doc("Accounting Dimension", name)
		self.assertEqual(dim.document_type, "Vehicle")
		self.assertEqual(dim.fieldname, VEHICLE_FIELDNAME)
		self.assertFalse(dim.disabled)

	def test_dimension_uses_the_hook_list(self):
		"""The doctype list must come from ERPNext's hook, not a local copy."""
		doctypes = get_dimension_doctypes()
		self.assertGreater(len(doctypes), 50)
		# contributed by erpnext and by hrms respectively
		self.assertIn("GL Entry", doctypes)
		self.assertIn("Expense Claim", doctypes)

	def test_field_present_on_every_dimension_doctype(self):
		self.assertEqual(missing_dimension_doctypes(), [])

	def test_no_duplicate_vehicle_fields(self):
		"""This app must not add its own `vehicle` field where the dimension does."""
		self.assertEqual(find_duplicate_vehicle_fields(), [])

	def test_field_is_a_link_to_vehicle(self):
		for doctype in (
			"GL Entry",
			"Expense Claim",
			"Expense Claim Detail",
			"Purchase Invoice",
			"Purchase Invoice Item",
			"Stock Entry",
			"Stock Entry Detail",
			"Journal Entry Account",
			"Asset Repair",
			"Asset",
			"Material Request Item",
		):
			field = frappe.get_meta(doctype).get_field(VEHICLE_FIELDNAME)
			self.assertTrue(field, f"{doctype} has no `vehicle` field")
			self.assertEqual(field.fieldtype, "Link", f"{doctype}.vehicle is not a Link")
			self.assertEqual(field.options, "Vehicle", f"{doctype}.vehicle does not point at Vehicle")

	def test_budget_can_be_set_against_vehicle(self):
		"""Makes the standard Budget Variance Report work per vehicle."""
		options = frappe.db.get_value(
			"Property Setter", "Budget-budget_against-options", "value"
		)
		self.assertTrue(options, "Budget-budget_against-options Property Setter missing")
		self.assertIn("Vehicle", options.split("\n"))

	def test_verify_helper_reports_healthy(self):
		result = verify_vehicle_dimension()
		self.assertTrue(result["dimension_exists"])
		self.assertEqual(result["missing"], [])
		self.assertEqual(result["duplicate_fields"], [])
		self.assertTrue(result["budget_against_has_vehicle"])
		self.assertEqual(result["fields_present"], result["expected_doctypes"])

	# --- real posting --------------------------------------------------------
	def test_journal_entry_carries_vehicle_into_gl(self):
		company = get_accounting_company()
		if not company:
			self.skipTest(f"{ACCOUNTING_COMPANY} not on this site")

		debit_account = get_leaf_account(company, "Expense")
		credit_account = frappe.db.get_value(
			"Account", {"company": company, "is_group": 0, "account_type": "Cash"}, "name"
		)
		if not (debit_account and credit_account):
			self.skipTest("no usable accounts on this site")

		cost_center = frappe.db.get_value(
			"Cost Center", {"company": company, "is_group": 0}, "name"
		)
		vehicle = new_vehicle(company=company)
		vehicle.insert()

		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Journal Entry",
				"company": company,
				"posting_date": nowdate(),
				"accounts": [
					{
						"account": debit_account,
						"debit_in_account_currency": 500,
						"cost_center": cost_center,
						VEHICLE_FIELDNAME: vehicle.name,
					},
					{
						"account": credit_account,
						"credit_in_account_currency": 500,
						"cost_center": cost_center,
						VEHICLE_FIELDNAME: vehicle.name,
					},
				],
			}
		)
		je.insert()
		je.submit()

		# the dimension must reach the ledger, not just the voucher
		gl = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": je.name, "is_cancelled": 0},
			fields=["account", "debit", "credit", VEHICLE_FIELDNAME],
		)
		self.assertEqual(len(gl), 2)
		for row in gl:
			self.assertEqual(
				row.get(VEHICLE_FIELDNAME),
				vehicle.name,
				"GL Entry did not carry the Vehicle dimension",
			)

		# and it must be filterable - this is what every cost report relies on
		filtered = frappe.get_all(
			"GL Entry",
			filters={VEHICLE_FIELDNAME: vehicle.name, "is_cancelled": 0},
			fields=["debit", "credit"],
		)
		self.assertEqual(len(filtered), 2)
		self.assertEqual(flt(sum(r.debit for r in filtered)), 500.0)

	def test_expense_claim_accepts_vehicle(self):
		"""Expense Claim is contributed by hrms, not erpnext - check it separately."""
		meta = frappe.get_meta("Expense Claim")
		self.assertTrue(meta.get_field(VEHICLE_FIELDNAME))
		self.assertTrue(frappe.get_meta("Expense Claim Detail").get_field(VEHICLE_FIELDNAME))

	def test_asset_repair_accepts_vehicle(self):
		"""Asset Repair is already a dimension DocType, so Phase 7 needs no custom field."""
		field = frappe.get_meta("Asset Repair").get_field(VEHICLE_FIELDNAME)
		self.assertTrue(field)
		self.assertEqual(field.options, "Vehicle")

	def test_stock_entry_accepts_vehicle(self):
		for doctype in ("Stock Entry", "Stock Entry Detail"):
			self.assertTrue(frappe.get_meta(doctype).get_field(VEHICLE_FIELDNAME))

	# --- standard reports ----------------------------------------------------
	def test_standard_reports_are_dimension_aware(self):
		from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
			get_dimensions,
		)

		dimension_filters, _defaults = get_dimensions()
		fieldnames = [d.fieldname for d in dimension_filters]
		self.assertIn(VEHICLE_FIELDNAME, fieldnames)

		documents = [d.document_type for d in dimension_filters]
		self.assertIn("Vehicle", documents)

	def test_general_ledger_report_runs_with_vehicle_filter(self):
		company = get_accounting_company()
		if not company:
			self.skipTest(f"{ACCOUNTING_COMPANY} not on this site")

		from erpnext.accounts.report.general_ledger.general_ledger import execute

		vehicle = new_vehicle(company=company)
		vehicle.insert()

		columns, data = execute(
			frappe._dict(
				{
					"company": company,
					"from_date": frappe.utils.add_months(nowdate(), -1),
					"to_date": nowdate(),
					"group_by": "Group by Voucher (Consolidated)",
					# the standard report builds `vehicle in %(vehicle)s`, so a
					# dimension filter must be a list, not a scalar
					VEHICLE_FIELDNAME: [vehicle.name],
				}
			)
		)[:2]
		self.assertTrue(columns)
