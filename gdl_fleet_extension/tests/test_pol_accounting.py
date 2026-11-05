# Copyright (c) 2026, GDL and contributors
"""
POL fuel claim -> Purchase Invoice, per provider.

Final document, POL Management: "the fuel invoice and payment are made based on
the detailed amount claimed from each provider" (BOD and STCBL).

The abstract approves; the invoice accounts. Fuel must reach the ledger once.
"""

import frappe
from frappe.tests import IntegrationTestCase

from gdl_fleet_extension.tests.fleet_settings_guard import FleetSettingsGuard
from frappe.utils import add_days, flt, nowdate

from gdl_fleet_extension.gdl_fleet.doctype.pol_abstract.pol_abstract import (
	get_claim_status,
	make_fuel_invoice,
)
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
from gdl_fleet_extension.tests.test_pol import fuel_supplier

COMPANY = "GDL (Demo)"


def get_expense_account():
	return frappe.db.get_value(
		"Account", {"company": COMPANY, "is_group": 0, "root_type": "Expense"}, "name"
	)


class TestPOLFuelClaim(FleetSettingsGuard, IntegrationTestCase):
	def setUp(self):
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
		for supplier in ("BOD", "STCBL"):
			if not frappe.db.exists("Supplier", supplier):
				frappe.get_doc({"doctype": "Supplier", "supplier_name": supplier,
				                "supplier_group": "All Supplier Groups"}).insert(ignore_permissions=True)
		self.account = get_expense_account()
		self.set("pol_bod_supplier", "BOD")
		self.set("pol_stcbl_supplier", "STCBL")
		self.set("pol_fuel_expense_account", self.account)

	def set(self, field, value):
		frappe.db.set_single_value("GDL Fleet Settings", field, value)
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def make_abstract(self, bod=0.0, stcbl=1200.0, submit=True):
		vehicle = new_vehicle(company=COMPANY, last_odometer=10000, min_mileage=0)
		vehicle.insert()
		doc = frappe.get_doc({
			"doctype": "POL Abstract", "vehicle": vehicle.name,
			"abstract_date": nowdate(), "period_from": add_days(nowdate(), -30),
			"period_to": nowdate(), "opening_km": 10000, "closing_km": 10800,
			"previous_tank_balance": 0, "present_tank_balance": 0,
			"recoupment_bod": 50000, "recoupment_stcbl": 50000,
			"supplier_bill_attachment": "/files/test-supplier-bill.pdf",
			# One row per provider. A fill comes from BOD or from STCBL, never
			# from both, so the abstract carries a line for each - which is
			# what the supplier-routed amount now expresses.
			"entries": [
				row for row in (
					{
						"supplier": fuel_supplier("BOD"),
						"supply_memo_no": f"B-{frappe.generate_hash(length=6)}",
						"date": nowdate(), "litres": 100, "rate": 12,
						"total_amount": bod,
					} if bod else None,
					{
						"supplier": fuel_supplier("STCBL"),
						"supply_memo_no": f"S-{frappe.generate_hash(length=6)}",
						"date": nowdate(), "litres": 100, "rate": 12,
						"total_amount": stcbl,
					} if stcbl else None,
				) if row
			],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		if submit:
			doc.submit()
		return doc

	# --- the claim ------------------------------------------------------
	def test_claim_creates_a_purchase_invoice_for_the_provider(self):
		doc = self.make_abstract(stcbl=1200)
		name = make_fuel_invoice(doc.name, "STCBL")
		pi = frappe.get_doc("Purchase Invoice", name)
		self.assertEqual(pi.supplier, "STCBL")
		self.assertEqual(flt(pi.grand_total), 1200)
		self.assertEqual(pi.docstatus, 0, "the claim is a draft for Accounts to check")

	def test_invoice_carries_the_abstract_reference(self):
		"""The invoice points at the abstract, not the other way round - a link
		held on the abstract would make the invoice impossible to cancel."""
		doc = self.make_abstract(stcbl=1200)
		name = make_fuel_invoice(doc.name, "STCBL")
		self.assertEqual(frappe.db.get_value("Purchase Invoice", name, "pol_abstract"), doc.name)
		self.assertEqual(get_claim_status(doc.name)["STCBL"]["invoice"], name)

	def test_the_abstract_holds_no_link_that_blocks_cancellation(self):
		fields = {f.fieldname for f in frappe.get_meta("POL Abstract").fields}
		self.assertNotIn("purchase_invoice_bod", fields)
		self.assertNotIn("purchase_invoice_stcbl", fields)

	def test_each_provider_gets_its_own_invoice(self):
		doc = self.make_abstract(bod=800, stcbl=1200)
		bod = make_fuel_invoice(doc.name, "BOD")
		stcbl = make_fuel_invoice(doc.name, "STCBL")
		self.assertNotEqual(bod, stcbl)
		self.assertEqual(frappe.db.get_value("Purchase Invoice", bod, "supplier"), "BOD")
		self.assertEqual(flt(frappe.db.get_value("Purchase Invoice", bod, "grand_total")), 800)
		self.assertEqual(flt(frappe.db.get_value("Purchase Invoice", stcbl, "grand_total")), 1200)

	def test_cannot_claim_the_same_provider_twice(self):
		doc = self.make_abstract(stcbl=1200)
		make_fuel_invoice(doc.name, "STCBL")
		self.assertRaises(frappe.ValidationError, make_fuel_invoice, doc.name, "STCBL")

	def test_cannot_claim_a_zero_amount(self):
		doc = self.make_abstract(bod=0, stcbl=1200)
		self.assertRaises(frappe.ValidationError, make_fuel_invoice, doc.name, "BOD")

	def test_cannot_claim_before_approval(self):
		doc = self.make_abstract(stcbl=1200, submit=False)
		self.assertRaises(frappe.ValidationError, make_fuel_invoice, doc.name, "STCBL")

	def test_unknown_provider_is_rejected(self):
		doc = self.make_abstract(stcbl=1200)
		self.assertRaises(frappe.ValidationError, make_fuel_invoice, doc.name, "SHELL")

	def test_missing_supplier_configuration_is_refused(self):
		"""The abstract is raised while the configuration is sound, and the
		setting is cleared afterwards - which is how this actually happens:
		somebody empties the field long after the claim was entered.

		Order matters now that the supplier routes the amount. Clearing the
		setting first would leave the fixture with no supplier to name.
		"""
		doc = self.make_abstract(stcbl=1200)
		self.set("pol_stcbl_supplier", None)
		try:
			self.assertRaises(frappe.ValidationError, make_fuel_invoice, doc.name, "STCBL")
		finally:
			self.set("pol_stcbl_supplier", "STCBL")

	def test_missing_expense_account_is_refused(self):
		"""Both places have to be empty.

		The account is resolved per company: the table is consulted first and
		the single field is only a fallback, so clearing the field alone leaves
		the claim perfectly able to find an account."""
		rows = self.clear_fuel_accounts()
		self.set("pol_fuel_expense_account", None)
		try:
			doc = self.make_abstract(stcbl=1200)
			self.assertRaises(frappe.ValidationError, make_fuel_invoice, doc.name, "STCBL")
		finally:
			self.restore_fuel_accounts(rows)
			self.set("pol_fuel_expense_account", self.account)

	def clear_fuel_accounts(self):
		doc = frappe.get_single("GDL Fleet Settings")
		rows = [(r.company, r.expense_account) for r in doc.pol_fuel_accounts]
		doc.set("pol_fuel_accounts", [])
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
		return rows

	def restore_fuel_accounts(self, rows):
		doc = frappe.get_single("GDL Fleet Settings")
		doc.set("pol_fuel_accounts", [])
		for company, account in rows:
			doc.append("pol_fuel_accounts", {"company": company, "expense_account": account})
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	# --- accounting -----------------------------------------------------
	def test_the_abstract_itself_still_posts_nothing(self):
		"""Fuel must reach the ledger once, through the invoice."""
		doc = self.make_abstract(stcbl=1200)
		self.assertFalse(frappe.db.exists(
			"GL Entry", {"voucher_type": "POL Abstract", "voucher_no": doc.name}))

	def test_submitting_the_claim_posts_to_the_ledger_once(self):
		doc = self.make_abstract(stcbl=1200)
		name = make_fuel_invoice(doc.name, "STCBL")
		pi = frappe.get_doc("Purchase Invoice", name)
		pi.flags.ignore_permissions = True
		pi.submit()

		rows = frappe.get_all("GL Entry", filters={"voucher_no": name, "is_cancelled": 0},
		                      fields=["account", "debit", "credit"])
		self.assertTrue(rows)
		self.assertEqual(flt(sum(r.debit for r in rows)), flt(sum(r.credit for r in rows)),
		                 "the claim must balance")
		self.assertEqual(flt(sum(r.debit for r in rows)), 1200)

	def test_claim_status_drives_the_buttons(self):
		doc = self.make_abstract(bod=800, stcbl=1200)
		status = get_claim_status(doc.name)
		self.assertTrue(status["BOD"]["claimable"])
		self.assertTrue(status["STCBL"]["claimable"])

		make_fuel_invoice(doc.name, "BOD")
		status = get_claim_status(doc.name)
		self.assertFalse(status["BOD"]["claimable"])
		self.assertTrue(status["STCBL"]["claimable"])

	def test_a_wrong_claim_can_be_cancelled(self):
		"""Accounts must be able to reverse a claim raised in error."""
		doc = self.make_abstract(stcbl=1200)
		name = make_fuel_invoice(doc.name, "STCBL")
		pi = frappe.get_doc("Purchase Invoice", name)
		pi.flags.ignore_permissions = True
		pi.submit()
		pi.cancel()
		self.assertEqual(frappe.db.get_value("Purchase Invoice", name, "docstatus"), 2)

	def test_a_cancelled_claim_can_be_raised_again(self):
		doc = self.make_abstract(stcbl=1200)
		name = make_fuel_invoice(doc.name, "STCBL")
		pi = frappe.get_doc("Purchase Invoice", name)
		pi.flags.ignore_permissions = True
		pi.submit()
		pi.cancel()

		again = make_fuel_invoice(doc.name, "STCBL")
		self.assertNotEqual(again, name)

	def test_auto_claim_is_off_by_default(self):
		self.assertFalse(frappe.db.get_single_value("GDL Fleet Settings", "pol_invoice_on_approval"))

	def test_auto_claim_raises_both_on_approval(self):
		self.set("pol_invoice_on_approval", 1)
		try:
			doc = self.make_abstract(bod=800, stcbl=1200)
			status = get_claim_status(doc.name)
			self.assertTrue(status["BOD"]["invoice"])
			self.assertTrue(status["STCBL"]["invoice"])
		finally:
			self.set("pol_invoice_on_approval", 0)
