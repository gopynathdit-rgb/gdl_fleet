# Copyright (c) 2026, GDL and contributors
"""
The simplified POL Abstract.

GDL asked for three things: a form without fields that do nothing, rows that
can be filled without opening each one, and the supplier's bill on the record
before anyone approves it.

The first is the one worth a test. POL Entry carried its own recoupment fields
that fed no calculation - the fuel book balance has always been worked out from
the ABSTRACT's recoupment - and a live abstract was found carrying 2,000 in a
row where it counted for nothing. The fields are hidden rather than dropped so
the figures already recorded survive, but nothing may start reading them.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from gdl_fleet_extension.tests.fleet_settings_guard import FleetSettingsGuard
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
from gdl_fleet_extension.tests.test_pol import fuel_supplier

GRID_COLUMN_LIMIT = 10


class TestPOLEntryGrid(IntegrationTestCase):
	"""Requirement 2: every field a driver fills is visible in the grid."""

	def setUp(self):
		self.meta = frappe.get_meta("POL Entry")

	def in_grid(self):
		return [f for f in self.meta.fields if f.in_list_view]

	def test_every_operational_field_is_in_the_grid(self):
		"""If one of these is missing the driver has to open the row to reach it.

		GDL asked for ONE amount per line instead of two: the supplier already
		says which provider a fill belongs to, so saying it again in a second
		money column was duplication - and allowed a row credited to both or
		to neither.
		"""
		shown = {f.fieldname for f in self.in_grid()}
		for fieldname in ("supply_memo_no", "date", "supplier", "litres",
		                  "rate", "odometer", "total_amount"):
			self.assertIn(fieldname, shown, f"{fieldname} is not visible in the grid")

	def test_the_grid_fits_within_the_column_budget(self):
		"""Frappe silently drops columns past 10, so this is not cosmetic."""
		used = sum(f.columns or 0 for f in self.in_grid())
		self.assertLessEqual(used, GRID_COLUMN_LIMIT,
		                     f"the grid asks for {used} columns and frappe allows {GRID_COLUMN_LIMIT}")

	def test_calculated_fields_are_not_in_the_grid(self):
		"""Space is scarce; a field the user cannot type into does not earn a column."""
		shown = {f.fieldname for f in self.in_grid()}
		for fieldname in ("amount_overridden", "amount_bod", "amount_stcbl"):
			self.assertNotIn(fieldname, shown)

	def test_the_provider_columns_are_derived_not_typed(self):
		"""amount_bod and amount_stcbl still drive the claim, the book balance
		and every POL report - they are just no longer entered by hand."""
		meta = frappe.get_meta("POL Entry")
		for fieldname in ("amount_bod", "amount_stcbl"):
			field = meta.get_field(fieldname)
			self.assertIsNotNone(field, f"{fieldname} must not be deleted")
			self.assertTrue(field.hidden, f"{fieldname} should be hidden")
			self.assertTrue(field.read_only, f"{fieldname} should be read-only")


class TestRowRecoupmentIsRetired(IntegrationTestCase):
	"""Requirement 1: the fields that did nothing are out of the way."""

	def test_row_recoupment_is_hidden(self):
		meta = frappe.get_meta("POL Entry")
		for fieldname in ("recoupment_bod", "recoupment_stcbl"):
			self.assertTrue(meta.get_field(fieldname).hidden,
			                f"POL Entry.{fieldname} feeds no calculation and must not be offered")

	def test_the_fields_still_exist_so_recorded_figures_survive(self):
		meta = frappe.get_meta("POL Entry")
		for fieldname in ("recoupment_bod", "recoupment_stcbl"):
			self.assertIsNotNone(meta.get_field(fieldname),
			                     "hidden, not deleted - abstracts already carry values here")

	def test_the_abstract_keeps_its_own_recoupment_visible(self):
		"""These are the figures the book balance is actually worked out from."""
		meta = frappe.get_meta("POL Abstract")
		for fieldname in ("recoupment_bod", "recoupment_stcbl"):
			self.assertFalse(meta.get_field(fieldname).hidden)

	def test_the_book_balance_ignores_the_row_values(self):
		"""The point of the whole change, proved rather than asserted."""
		doc = make_abstract(stcbl=1000, recoupment_bod=5000, recoupment_stcbl=5000)
		baseline = doc.fuel_book_balance_stcbl

		doc.entries[0].recoupment_stcbl = 99999
		doc.entries[0].recoupment_bod = 99999
		doc.save()
		self.assertEqual(doc.fuel_book_balance_stcbl, baseline,
		                 "a figure typed on the row changed the balance - it must not")

	def test_the_abstract_recoupment_does_move_the_balance(self):
		"""The other half: the parent's value is the one that counts."""
		doc = make_abstract(stcbl=1000, recoupment_bod=5000, recoupment_stcbl=5000)
		baseline = doc.fuel_book_balance_stcbl
		doc.recoupment_stcbl = 6000
		doc.save()
		self.assertNotEqual(doc.fuel_book_balance_stcbl, baseline)


class TestSupplierBillAttachment(FleetSettingsGuard, IntegrationTestCase):
	"""Requirement 3: no approval without the supplier's bill."""

	def setUp(self):
		frappe.db.set_single_value("GDL Fleet Settings", "pol_abstract_requires_attachment", 1)
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def test_the_field_exists_on_the_abstract(self):
		field = frappe.get_meta("POL Abstract").get_field("supplier_bill_attachment")
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Attach")

	def test_a_draft_needs_no_attachment(self):
		"""The driver builds the abstract before the bill is to hand."""
		doc = make_abstract(stcbl=1000)
		self.assertEqual(doc.status, "Draft")

	def test_sending_for_approval_without_the_bill_is_refused(self):
		doc = make_abstract(stcbl=1000)
		doc.status = "Submitted"
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_sending_for_approval_with_the_bill_is_allowed(self):
		doc = make_abstract(stcbl=1000)
		doc.supplier_bill_attachment = "/files/bod-october.pdf"
		doc.status = "Submitted"
		doc.save()
		self.assertEqual(doc.status, "Submitted")

	def test_approval_without_the_bill_is_refused(self):
		"""Belt and braces: a programmatic submit bypasses the workflow."""
		doc = make_abstract(stcbl=1000)
		self.assertRaises(frappe.ValidationError, doc.submit)

	def test_approval_with_the_bill_goes_through(self):
		doc = make_abstract(stcbl=1000)
		doc.supplier_bill_attachment = "/files/bod-october.pdf"
		doc.save()
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_the_requirement_can_be_switched_off(self):
		"""GDL may not have scans for every depot on day one."""
		frappe.db.set_single_value("GDL Fleet Settings", "pol_abstract_requires_attachment", 0)
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
		doc = make_abstract(stcbl=1000)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)


class TestTheRuleIsLiveOnThisSite(IntegrationTestCase):
	"""Deliberately sets nothing.

	A Check default in the DocType JSON applies only when the single is first
	created. GDL Fleet Settings already existed, so the new field arrived as 0
	and the rule sat there doing nothing while the whole suite went green -
	exactly how maintenance_bill_requires_attachment came to be found at 0.
	The other class here sets the flag in setUp, so it could never catch that.
	This one reads what the site actually holds.
	"""

	def test_the_supplier_bill_requirement_is_switched_on(self):
		self.assertTrue(
			frappe.db.get_single_value("GDL Fleet Settings", "pol_abstract_requires_attachment"),
			"the rule is off on this site - patches/v1_3/require_pol_bill_attachment did not run",
		)


def make_abstract(stcbl=1000.0, recoupment_bod=50000, recoupment_stcbl=50000):
	vehicle = new_vehicle(company="GDL (Demo)", last_odometer=10000, min_mileage=0)
	vehicle.insert()
	doc = frappe.get_doc({
		"doctype": "POL Abstract", "vehicle": vehicle.name,
		"abstract_date": nowdate(), "period_from": add_days(nowdate(), -30),
		"period_to": nowdate(), "opening_km": 10000, "closing_km": 10800,
		"previous_tank_balance": 0, "present_tank_balance": 0,
		"recoupment_bod": recoupment_bod, "recoupment_stcbl": recoupment_stcbl,
		"entries": [{
			"supplier": fuel_supplier("STCBL"),
			"supply_memo_no": f"M-{frappe.generate_hash(length=6)}",
			"date": nowdate(), "litres": 100, "rate": 12, "amount_stcbl": stcbl,
		}],
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc


class TestProviderAmountsAreDerived(IntegrationTestCase):
	"""GDL asked for the provider split to disappear from the screen.

	It has not disappeared from the system: the book balance for each provider
	and the Purchase Invoice raised against each are both worked out from these
	figures. They are hidden and derived, never typed.
	"""

	HIDDEN_ON_THE_ABSTRACT = ("total_amount_bod", "total_amount_stcbl",
	                          "previous_tank_balance", "present_tank_balance")
	HIDDEN_ON_THE_LINE = ("amount_bod", "amount_stcbl")

	def test_the_abstract_hides_them(self):
		meta = frappe.get_meta("POL Abstract")
		for fieldname in self.HIDDEN_ON_THE_ABSTRACT:
			field = meta.get_field(fieldname)
			self.assertIsNotNone(field, f"{fieldname} must not be deleted")
			self.assertTrue(field.hidden, f"{fieldname} is still on screen")

	def test_the_line_hides_them(self):
		meta = frappe.get_meta("POL Entry")
		for fieldname in self.HIDDEN_ON_THE_LINE:
			field = meta.get_field(fieldname)
			self.assertIsNotNone(field, f"{fieldname} must not be deleted")
			self.assertTrue(field.hidden)
			self.assertTrue(field.read_only)

	def test_the_provider_totals_are_read_only(self):
		"""Derived from the lines. Typing one would let the book balance drift
		away from the fills it is supposed to summarise."""
		meta = frappe.get_meta("POL Abstract")
		for fieldname in ("total_amount_bod", "total_amount_stcbl"):
			self.assertTrue(meta.get_field(fieldname).read_only)

	def test_the_book_balance_still_reads_them(self):
		"""Hidden is not gone. If this breaks, the claim breaks with it."""
		import inspect
		from gdl_fleet_extension.utils import pol
		source = inspect.getsource(pol.compute_abstract)
		self.assertIn("total_amount_bod", source)
		self.assertIn("total_amount_stcbl", source)
