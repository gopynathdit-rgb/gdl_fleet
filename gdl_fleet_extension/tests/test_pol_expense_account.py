# Copyright (c) 2026, GDL and contributors
"""
The fuel expense account, per company.

A live claim failed with ERPNext's own message: "Row 1: The Expense Account
5000 - Expenses - G does not belong to the company GDL (Demo)". Two faults sat
behind it. The configured account was a GROUP account, which nothing can post
to. And it belonged to company GDL while the abstract's vehicle belonged to
GDL (Demo) - GDL runs both, 14 vehicles in one and 10 in the other, so a single
global account was always going to be wrong for one of them.

The claim is raised in the company that owns the VEHICLE, so the account has to
be that company's. These tests hold both halves of that.
"""

import frappe
from frappe.tests import IntegrationTestCase

from gdl_fleet_extension.gdl_fleet.doctype.gdl_fleet_settings.gdl_fleet_settings import (
	check_expense_account,
)
from gdl_fleet_extension.gdl_fleet.doctype.pol_abstract.pol_abstract import (
	get_fuel_expense_account,
)

COMPANY = "GDL (Demo)"


def an_account(company, is_group=0, root_type="Expense"):
	return frappe.db.get_value(
		"Account",
		{"company": company, "is_group": is_group, "root_type": root_type, "disabled": 0},
		"name",
	)


class TestExpenseAccountChecks(IntegrationTestCase):
	"""What may and may not be used as a fuel account."""

	def test_a_group_account_is_refused(self):
		"""The original fault. ERPNext cannot post to a group account at all."""
		group = an_account(COMPANY, is_group=1)
		self.assertRaises(frappe.ValidationError, check_expense_account, group, COMPANY)

	def test_another_companys_account_is_refused(self):
		"""The second fault, and the one the error message named."""
		other = an_account("GDL")
		if not other:
			self.skipTest("the second company is not on this site")
		self.assertRaises(frappe.ValidationError, check_expense_account, other, COMPANY)

	def test_an_income_account_is_refused(self):
		income = an_account(COMPANY, root_type="Income")
		if not income:
			self.skipTest("no income ledger on this company")
		self.assertRaises(frappe.ValidationError, check_expense_account, income, COMPANY)

	def test_the_companys_own_expense_ledger_is_accepted(self):
		check_expense_account(an_account(COMPANY), COMPANY)

	def test_nothing_configured_is_not_an_error_here(self):
		"""An empty setting is handled where the claim is raised, with a message
		that can name the company. This check only judges an account it is given."""
		check_expense_account(None, COMPANY)


class TestPerCompanyResolution(IntegrationTestCase):
	"""Each company gets its own account."""

	def setUp(self):
		self.settings = frappe.get_single("GDL Fleet Settings")
		self.rows = [(r.company, r.expense_account) for r in self.settings.pol_fuel_accounts]
		self.fallback = self.settings.pol_fuel_expense_account

	def tearDown(self):
		doc = frappe.get_single("GDL Fleet Settings")
		doc.set("pol_fuel_accounts", [])
		for company, account in self.rows:
			doc.append("pol_fuel_accounts", {"company": company, "expense_account": account})
		doc.pol_fuel_expense_account = self.fallback
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def configure(self, rows=None, fallback=None):
		doc = frappe.get_single("GDL Fleet Settings")
		doc.set("pol_fuel_accounts", [])
		for company, account in rows or []:
			doc.append("pol_fuel_accounts", {"company": company, "expense_account": account})
		doc.pol_fuel_expense_account = fallback
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def test_the_row_for_the_company_is_used(self):
		account = an_account(COMPANY)
		self.configure(rows=[(COMPANY, account)])
		self.assertEqual(get_fuel_expense_account(COMPANY), account)

	def test_each_company_gets_its_own(self):
		"""The point of the whole change."""
		mine, theirs = an_account(COMPANY), an_account("GDL")
		if not theirs:
			self.skipTest("the second company is not on this site")
		self.configure(rows=[(COMPANY, mine), ("GDL", theirs)])
		self.assertEqual(get_fuel_expense_account(COMPANY), mine)
		self.assertEqual(get_fuel_expense_account("GDL"), theirs)
		self.assertNotEqual(mine, theirs)

	def test_the_fallback_serves_a_company_with_no_row(self):
		account = an_account(COMPANY)
		self.configure(rows=[], fallback=account)
		self.assertEqual(get_fuel_expense_account(COMPANY), account)

	def test_a_fallback_from_another_company_is_refused(self):
		"""Exactly the live failure, caught before ERPNext sees it."""
		theirs = an_account("GDL")
		if not theirs:
			self.skipTest("the second company is not on this site")
		self.configure(rows=[], fallback=theirs)
		with self.assertRaises(frappe.ValidationError) as caught:
			get_fuel_expense_account(COMPANY)
		message = frappe.utils.strip_html(str(caught.exception))
		self.assertIn(COMPANY, message, "the message must name the company that needs a row")
		self.assertIn("GDL Fleet Settings", message, "and say where to fix it")

	def test_nothing_configured_names_the_company(self):
		self.configure(rows=[], fallback=None)
		with self.assertRaises(frappe.ValidationError) as caught:
			get_fuel_expense_account(COMPANY)
		self.assertIn(COMPANY, frappe.utils.strip_html(str(caught.exception)))

	def test_a_vehicle_with_no_company_is_refused_clearly(self):
		self.assertRaises(frappe.ValidationError, get_fuel_expense_account, None)


class TestSettingsRefuseBadRows(IntegrationTestCase):
	"""The complaint belongs next to the field that caused it."""

	def setUp(self):
		self.settings = frappe.get_single("GDL Fleet Settings")
		self.rows = [(r.company, r.expense_account) for r in self.settings.pol_fuel_accounts]

	def tearDown(self):
		doc = frappe.get_single("GDL Fleet Settings")
		doc.set("pol_fuel_accounts", [])
		for company, account in self.rows:
			doc.append("pol_fuel_accounts", {"company": company, "expense_account": account})
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def save_with(self, rows):
		doc = frappe.get_single("GDL Fleet Settings")
		doc.set("pol_fuel_accounts", [])
		for company, account in rows:
			doc.append("pol_fuel_accounts", {"company": company, "expense_account": account})
		doc.flags.ignore_permissions = True
		doc.save()

	def test_a_row_pairing_the_wrong_company_is_refused_on_save(self):
		theirs = an_account("GDL")
		if not theirs:
			self.skipTest("the second company is not on this site")
		self.assertRaises(frappe.ValidationError, self.save_with, [(COMPANY, theirs)])

	def test_a_group_account_row_is_refused_on_save(self):
		group = an_account(COMPANY, is_group=1)
		self.assertRaises(frappe.ValidationError, self.save_with, [(COMPANY, group)])

	def test_one_company_cannot_appear_twice(self):
		account = an_account(COMPANY)
		self.assertRaises(
			frappe.ValidationError, self.save_with, [(COMPANY, account), (COMPANY, account)])

	def test_a_correct_row_saves(self):
		self.save_with([(COMPANY, an_account(COMPANY))])
		doc = frappe.get_single("GDL Fleet Settings")
		self.assertEqual(len(doc.pol_fuel_accounts), 1)


class TestThisSiteIsConfigured(IntegrationTestCase):
	"""Reads what the site actually holds, and sets nothing."""

	def test_every_company_that_owns_a_vehicle_can_post_fuel(self):
		companies = {c for c in frappe.get_all("Vehicle", pluck="company") if c}
		self.assertTrue(companies, "no vehicle carries a company")
		for company in companies:
			with self.subTest(company=company):
				account = get_fuel_expense_account(company)
				row = frappe.db.get_value(
					"Account", account, ["company", "is_group", "root_type"], as_dict=True)
				self.assertEqual(row.company, company)
				self.assertFalse(row.is_group, "nothing can be posted to a group account")
				self.assertEqual(row.root_type, "Expense")
