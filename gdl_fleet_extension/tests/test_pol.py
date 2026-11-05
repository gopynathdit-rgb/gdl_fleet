# Copyright (c) 2026, GDL and contributors
"""
POL Abstract - Fleet Mgmt.docx 4.10 and the customer's POL.xlsx workbook.

The two workbook sheets are reproduced exactly, because they are the
specification. Of particular note, BG-1-A3812 carries a hand-typed performance
of 9 and 2223 / 247 is exactly 9 - which is what confirms the consumption
formula is supplied + PREVIOUS - PRESENT rather than the other way round.
"""

from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase

from gdl_fleet_extension.tests.fleet_settings_guard import FleetSettingsGuard
from frappe.utils import add_days, flt, nowdate

from gdl_fleet_extension.gdl_fleet.doctype.pol_abstract.pol_abstract import get_carry_forward
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
from gdl_fleet_extension.utils.pol import (
	compute_abstract,
	fuel_book_balance,
	line_amount,
	performance_per_litre,
	quantize,
	total_fuel_consumed,
	total_km,
	total_litres,
	to_decimal,
)

# ---------------------------------------------------------------------------
# The workbook, verbatim
# ---------------------------------------------------------------------------
SHEET_A2397 = {
	"vehicle": "BG-1-A2397",
	# Amounts are TYPED on this sheet, not formulas. Row 1 reads 4413.04 where
	# 41.81 x 105.55 is 4413.0455, so the approved total is 16339.43 and not
	# the 16339.44 a recomputation would give.
	"entries": [
		{"supply_memo_no": "25743", "litres": "41.81", "rate": "105.55", "amount_stcbl": "4413.04"},
		{"supply_memo_no": "39883", "litres": "58",    "rate": "104.38", "amount_stcbl": "6054.04"},
		{"supply_memo_no": "64535", "litres": "55",    "rate": "106.77", "amount_stcbl": "5872.35"},
	],
	"opening_km": 227953,
	"closing_km": 229032,
	"previous_tank_balance": 40,
	"present_tank_balance": 60,
	"recoupment_bod": 15000,
	"recoupment_stcbl": 20000,
	"expected": {
		"total_fuel_supplied": Decimal("154.81"),
		"total_amount_stcbl": Decimal("16339.43"),
		"total_km": Decimal("1079"),
		"total_fuel_consumed": Decimal("134.81"),
		"fuel_book_balance_stcbl": Decimal("3660.57"),
		"fuel_book_balance_bod": Decimal("15000.00"),
	},
}

SHEET_A3812 = {
	"vehicle": "BG-1-A3812",
	# Amounts here ARE formulas (=F6*E6), so they are left to compute.
	"entries": [
		{"supply_memo_no": "13622", "litres": "30", "rate": "104.24"},
		{"supply_memo_no": "2296",  "litres": "63", "rate": "96.91"},
		{"supply_memo_no": "19350", "litres": "56", "rate": "98.31"},
		{"supply_memo_no": "13277", "litres": "50", "rate": "98.31"},
		{"supply_memo_no": "36498", "litres": "53", "rate": "104.50"},
	],
	"opening_km": 13458,
	"closing_km": 15681,
	"previous_tank_balance": 30,
	"present_tank_balance": 35,
	"recoupment_bod": 0,
	"recoupment_stcbl": 30000,
	"expected": {
		"total_fuel_supplied": Decimal("252"),
		"total_amount_stcbl": Decimal("25191.89"),
		"total_km": Decimal("2223"),
		"total_fuel_consumed": Decimal("247"),
		"fuel_book_balance_stcbl": Decimal("4808.11"),
		"fuel_book_balance_bod": Decimal("0.00"),
	},
}


def fuel_supplier(provider):
	"""The Supplier record GDL Fleet Settings names for this provider.

	The supplier is now the routing key - it decides whether a line is claimed
	from BOD or STCBL - so a fixture has to name one.
	"""
	name = frappe.db.get_single_value(
		"GDL Fleet Settings", f"pol_{provider.lower()}_supplier")
	if name and frappe.db.exists("Supplier", name):
		return name
	return None


def sheet_entries(sheet):
	"""Entry rows with STCBL amounts defaulted where the sheet used a formula."""
	rows = []
	for row in sheet["entries"]:
		row = dict(row)
		if "amount_stcbl" not in row:
			row["amount_stcbl"] = line_amount(row["litres"], row["rate"])
		rows.append(row)
	return rows


# ===========================================================================
# 1. The calculation layer, with no document involved
# ===========================================================================
class TestPOLCalculation(IntegrationTestCase):
	def compute(self, sheet):
		return compute_abstract(
			entries=sheet_entries(sheet),
			opening_km=sheet["opening_km"],
			closing_km=sheet["closing_km"],
			previous_tank_balance=sheet["previous_tank_balance"],
			present_tank_balance=sheet["present_tank_balance"],
			recoupment_bod=sheet["recoupment_bod"],
			recoupment_stcbl=sheet["recoupment_stcbl"],
			performance_precision=None,
		)

	# --- workbook sheet 1 ---------------------------------------------------
	def test_bg_1_a2397_matches_the_workbook(self):
		result = self.compute(SHEET_A2397)
		for field, expected in SHEET_A2397["expected"].items():
			self.assertEqual(result[field], expected, f"{field} differs from the workbook")

	def test_bg_1_a2397_performance(self):
		result = self.compute(SHEET_A2397)
		# Workbook cell D32 caches 8.003857280617165
		self.assertAlmostEqual(float(result["performance_per_litre"]), 1079 / 134.81, places=9)
		self.assertTrue(str(result["performance_per_litre"]).startswith("8.003857"))

	# --- workbook sheet 2 ---------------------------------------------------
	def test_bg_1_a3812_matches_the_workbook(self):
		result = self.compute(SHEET_A3812)
		for field, expected in SHEET_A3812["expected"].items():
			self.assertEqual(result[field], expected, f"{field} differs from the workbook")

	def test_bg_1_a3812_performance_is_exactly_nine(self):
		"""The sheet holds a hand-typed 9, and 2223 / 247 is exactly 9.

		This is the evidence that consumption is supplied + previous - present.
		The inverted formula would give 257 litres and 8.6498 km/l.
		"""
		result = self.compute(SHEET_A3812)
		self.assertEqual(result["performance_per_litre"], Decimal("9"))

	def test_inverted_consumption_formula_is_not_used(self):
		"""Guards the one calculation the whole abstract turns on."""
		supplied, previous, present = Decimal("154.81"), Decimal("40"), Decimal("60")
		self.assertEqual(total_fuel_consumed(supplied, previous, present), Decimal("134.81"))
		self.assertNotEqual(total_fuel_consumed(supplied, previous, present), Decimal("174.81"))

	def test_performance_uses_consumed_not_supplied(self):
		result = self.compute(SHEET_A3812)
		supplied_based = Decimal("2223") / Decimal("252")
		self.assertNotEqual(result["performance_per_litre"], supplied_based)

	# --- primitives ---------------------------------------------------------
	def test_total_litres_is_summed_never_entered(self):
		self.assertEqual(total_litres(sheet_entries(SHEET_A2397)), Decimal("154.81"))

	def test_total_km_is_closing_less_opening(self):
		self.assertEqual(total_km(227953, 229032), Decimal("1079"))

	def test_line_amount_rounds_half_up(self):
		self.assertEqual(line_amount("41.81", "105.55"), Decimal("4413.05"))

	def test_decimal_is_used_not_float(self):
		"""0.1 + 0.2 must be 0.3 here, which it is not in binary floating point."""
		rows = [{"litres": "0.1", "supplier": fuel_supplier("STCBL"),
			}, {"litres": "0.2", "supplier": fuel_supplier("STCBL"),
			}]
		self.assertEqual(total_litres(rows), Decimal("0.3"))

	def test_performance_is_none_when_consumption_is_zero(self):
		self.assertIsNone(performance_per_litre(100, 0))

	def test_performance_is_none_when_consumption_is_negative(self):
		self.assertIsNone(performance_per_litre(100, -5))

	def test_blank_bod_amount_is_not_fabricated(self):
		"""Both sheets leave Amount (BOD) empty, so the balance is the recoupment."""
		self.assertEqual(fuel_book_balance(15000, None), Decimal("15000.00"))

	def test_to_decimal_handles_blanks(self):
		for blank in (None, "", "not a number"):
			self.assertEqual(to_decimal(blank), Decimal("0"))

	def test_quantize_is_half_up(self):
		self.assertEqual(quantize("2.345", 2), Decimal("2.35"))


# ===========================================================================
# 2. The document
# ===========================================================================
class TestPOLAbstract(FleetSettingsGuard, IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(last_odometer=227953)
		self.vehicle.insert()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def make_abstract(self, sheet=None, submit=False, **kwargs):
		sheet = sheet or SHEET_A2397
		values = {
			"doctype": "POL Abstract",
			"vehicle": self.vehicle.name,
			"abstract_date": nowdate(),
			"period_from": add_days(nowdate(), -60),
			"period_to": nowdate(),
			"distance_basis": "KM",
			"opening_km": sheet["opening_km"],
			"closing_km": sheet["closing_km"],
			"previous_tank_balance": sheet["previous_tank_balance"],
			"present_tank_balance": sheet["present_tank_balance"],
			"recoupment_bod": sheet["recoupment_bod"],
			"recoupment_stcbl": sheet["recoupment_stcbl"],
			"supplier_bill_attachment": "/files/test-supplier-bill.pdf",
			"entries": [
				{
					"supply_memo_no": row["supply_memo_no"],
					"date": add_days(nowdate(), -30),
					"litres": float(row["litres"]),
					"rate": float(row["rate"]),
					# Both workbook sheets are STCBL claims - the BOD amount
					# column is empty on each. The row now carries ONE amount
					# and the supplier says which claim it lands in.
					"supplier": fuel_supplier("STCBL"),
					**({"total_amount": float(row["amount_stcbl"])} if "amount_stcbl" in row else {}),
				}
				for row in sheet["entries"]
			],
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert()
		if submit:
			doc.submit()
		return doc

	# --- the workbook, through the document ---------------------------------
	def test_abstract_reproduces_sheet_bg_1_a2397(self):
		doc = self.make_abstract(SHEET_A2397)
		self.assertEqual(flt(doc.total_fuel_supplied, 2), 154.81)
		self.assertEqual(flt(doc.total_amount_stcbl, 2), 16339.43)
		self.assertEqual(flt(doc.total_km, 2), 1079)
		self.assertEqual(flt(doc.total_fuel_consumed, 2), 134.81)
		self.assertEqual(flt(doc.fuel_book_balance_stcbl, 2), 3660.57)
		self.assertEqual(flt(doc.fuel_book_balance_bod, 2), 15000)
		self.assertAlmostEqual(doc.performance_per_litre, 1079 / 134.81, places=6)

	def test_abstract_reproduces_sheet_bg_1_a3812(self):
		doc = self.make_abstract(SHEET_A3812)
		self.assertEqual(flt(doc.total_fuel_supplied, 2), 252)
		self.assertEqual(flt(doc.total_amount_stcbl, 2), 25191.89)
		self.assertEqual(flt(doc.total_km, 2), 2223)
		self.assertEqual(flt(doc.total_fuel_consumed, 2), 247)
		self.assertEqual(flt(doc.fuel_book_balance_stcbl, 2), 4808.11)
		self.assertEqual(doc.performance_per_litre, 9.0)

	def test_performance_is_stored_at_full_accuracy_not_rounded_to_nine(self):
		"""The workbook's displayed 9 must not become a stored literal."""
		doc = self.make_abstract(SHEET_A2397)
		self.assertNotEqual(doc.performance_per_litre, 8.0)
		self.assertGreater(doc.performance_per_litre, 8.0038)
		self.assertLess(doc.performance_per_litre, 8.0039)

	# --- amount defaulting and override -------------------------------------
	def test_stcbl_amount_defaults_to_litres_times_rate(self):
		doc = self.make_abstract(SHEET_A3812)
		self.assertEqual(flt(doc.entries[0].amount_stcbl, 2), 3127.20)
		self.assertFalse(doc.entries[0].amount_overridden)

	def test_manual_stcbl_amount_is_preserved_not_recomputed(self):
		"""41.81 x 105.55 is 4413.0455; the customer's sheet says 4413.04."""
		doc = self.make_abstract(SHEET_A2397)
		self.assertEqual(flt(doc.entries[0].amount_stcbl, 2), 4413.04)
		self.assertTrue(doc.entries[0].amount_overridden)

	def test_override_flows_into_the_book_balance(self):
		doc = self.make_abstract(SHEET_A2397)
		self.assertEqual(flt(doc.fuel_book_balance_stcbl, 2), 3660.57)
		self.assertNotEqual(flt(doc.fuel_book_balance_stcbl, 2), 3660.56)

	def test_a_bod_supplier_routes_the_amount_to_bod(self):
		"""The amount follows the supplier. Nobody types which column."""
		doc = self.make_abstract(SHEET_A3812)
		doc.entries[0].supplier = fuel_supplier("BOD")
		doc.entries[0].total_amount = 1000
		doc.save()
		self.assertEqual(flt(doc.entries[0].amount_bod, 2), 1000)
		self.assertEqual(flt(doc.entries[0].amount_stcbl, 2), 0)
		self.assertEqual(flt(doc.total_amount_bod, 2), 1000)

	def test_bod_book_balance_deducts_a_bod_line(self):
		doc = self.make_abstract(SHEET_A2397)
		doc.entries[0].supplier = fuel_supplier("BOD")
		doc.entries[0].total_amount = 2500
		doc.save()
		self.assertEqual(flt(doc.fuel_book_balance_bod, 2), 12500)

	def test_a_supplier_that_is_neither_provider_is_refused(self):
		"""A fuel line credited to neither provider is unclaimable."""
		doc = self.make_abstract(SHEET_A2397)
		other = frappe.db.get_value("Supplier", {"name": ("not in",
			[fuel_supplier("BOD"), fuel_supplier("STCBL")])}, "name")
		if not other:
			self.skipTest("no third supplier on this site")
		doc.entries[0].supplier = other
		self.assertRaises(frappe.ValidationError, doc.save)

	def test_no_bod_line_leaves_the_bod_recoupment_intact(self):
		doc = self.make_abstract(SHEET_A2397)
		self.assertEqual(flt(doc.total_amount_bod, 2), 0)
		self.assertEqual(flt(doc.fuel_book_balance_bod, 2), 15000)

	# --- validations --------------------------------------------------------
	def test_closing_km_below_opening_is_rejected(self):
		self.assertRaises(
			frappe.ValidationError,
			self.make_abstract, SHEET_A2397, opening_km=229032, closing_km=227953,
		)

	def test_equal_opening_and_closing_km_is_allowed(self):
		doc = self.make_abstract(SHEET_A2397, opening_km=5000, closing_km=5000)
		self.assertEqual(flt(doc.total_km), 0)

	def test_negative_previous_tank_balance_is_rejected(self):
		self.assertRaises(
			frappe.ValidationError, self.make_abstract, SHEET_A2397, previous_tank_balance=-1
		)

	def test_negative_present_tank_balance_is_rejected(self):
		self.assertRaises(
			frappe.ValidationError, self.make_abstract, SHEET_A2397, present_tank_balance=-1
		)

	def test_negative_consumption_is_rejected(self):
		"""Present balance larger than supplied plus previous is impossible."""
		self.assertRaises(
			frappe.ValidationError, self.make_abstract, SHEET_A2397, present_tank_balance=5000
		)

	def test_zero_litres_is_rejected(self):
		sheet = dict(SHEET_A2397, entries=[{"supply_memo_no": "1", "litres": "0", "rate": "100", "supplier": fuel_supplier("STCBL"),
			}])
		self.assertRaises(frappe.ValidationError, self.make_abstract, sheet)

	def test_negative_litres_is_rejected(self):
		sheet = dict(SHEET_A2397, entries=[{"supply_memo_no": "1", "litres": "-5", "rate": "100", "supplier": fuel_supplier("STCBL"),
			}])
		self.assertRaises(frappe.ValidationError, self.make_abstract, sheet)

	def test_negative_rate_is_rejected(self):
		sheet = dict(SHEET_A2397, entries=[{"supply_memo_no": "1", "litres": "5", "rate": "-100", "supplier": fuel_supplier("STCBL"),
			}])
		self.assertRaises(frappe.ValidationError, self.make_abstract, sheet)

	def test_abstract_without_entries_is_rejected(self):
		self.assertRaises(frappe.ValidationError, self.make_abstract, SHEET_A2397, entries=[])

	def test_period_to_before_period_from_is_rejected(self):
		self.assertRaises(
			frappe.ValidationError, self.make_abstract, SHEET_A2397,
			period_from=nowdate(), period_to=add_days(nowdate(), -10),
		)

	def test_zero_consumption_leaves_performance_blank(self):
		"""Supplied exactly offset by the tank movement - not a zero measurement."""
		sheet = dict(
			SHEET_A2397,
			entries=[{"supply_memo_no": "1", "litres": "10", "rate": "100", "supplier": fuel_supplier("STCBL"),
			}],
			previous_tank_balance=0, present_tank_balance=10,
		)
		doc = self.make_abstract(sheet)
		self.assertEqual(flt(doc.total_fuel_consumed), 0)
		self.assertIsNone(doc.performance_per_litre)

	# --- duplicate protection ----------------------------------------------
	def test_duplicate_supply_memo_within_one_abstract_is_rejected(self):
		sheet = dict(SHEET_A2397, entries=[
			{"supply_memo_no": "SAME", "litres": "10", "rate": "100", "supplier": fuel_supplier("STCBL"),
			},
			{"supply_memo_no": "SAME", "litres": "20", "rate": "100", "supplier": fuel_supplier("STCBL"),
			},
		])
		self.assertRaises(frappe.ValidationError, self.make_abstract, sheet)

	def test_duplicate_supply_memo_across_abstracts_is_rejected(self):
		memo = f"MEMO-{frappe.generate_hash(length=6)}"
		sheet = dict(SHEET_A2397, entries=[{"supply_memo_no": memo, "litres": "100", "rate": "100", "supplier": fuel_supplier("STCBL"),
			}])
		first = self.make_abstract(sheet)
		self.assertTrue(first.name)
		self.assertRaises(frappe.ValidationError, self.make_abstract, sheet)

	def test_memo_uniqueness_is_configurable(self):
		frappe.db.set_single_value("GDL Fleet Settings", "pol_enforce_unique_supply_memo", 0)
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
		try:
			sheet = dict(SHEET_A2397, entries=[
				{"supply_memo_no": "DUP", "litres": "10", "rate": "100", "supplier": fuel_supplier("STCBL"),
			},
				{"supply_memo_no": "DUP", "litres": "20", "rate": "100", "supplier": fuel_supplier("STCBL"),
			},
			])
			doc = self.make_abstract(sheet)
			self.assertEqual(len(doc.entries), 2)
		finally:
			frappe.db.set_single_value("GDL Fleet Settings", "pol_enforce_unique_supply_memo", 1)
			frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	# --- distance basis -----------------------------------------------------
	def test_hours_basis_is_supported(self):
		doc = self.make_abstract(SHEET_A2397, distance_basis="Hours",
		                         opening_km=1200, closing_km=1500)
		self.assertEqual(doc.distance_basis, "Hours")
		self.assertEqual(flt(doc.total_km), 300)

	def test_default_basis_is_km(self):
		doc = self.make_abstract(SHEET_A2397)
		self.assertEqual(doc.distance_basis, "KM")

	# --- lifecycle ----------------------------------------------------------
	def test_submit_records_the_approver(self):
		doc = self.make_abstract(SHEET_A2397, submit=True)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.status, "Approved")
		self.assertTrue(doc.approved_by)
		self.assertTrue(doc.submitted_by)

	def test_cancel_sets_cancelled(self):
		doc = self.make_abstract(SHEET_A2397, submit=True)
		doc.cancel()
		self.assertEqual(frappe.db.get_value("POL Abstract", doc.name, "status"), "Cancelled")

	def test_draft_starts_as_draft(self):
		self.assertEqual(self.make_abstract(SHEET_A2397).status, "Draft")

	def test_pol_posts_no_accounting_entries(self):
		"""POL abstracts fuel; it never becomes a second fuel transaction."""
		doc = self.make_abstract(SHEET_A2397, submit=True)
		self.assertFalse(
			frappe.db.exists("GL Entry", {"voucher_type": "POL Abstract", "voucher_no": doc.name})
		)


# ===========================================================================
# 4. Carry-forward
# ===========================================================================
class TestPOLCarryForward(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(last_odometer=10000)
		self.vehicle.insert()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def make(self, opening, closing, previous_tank, present_tank, submit=True, **kwargs):
		values = {
			"doctype": "POL Abstract",
			"vehicle": self.vehicle.name,
			"abstract_date": nowdate(),
			"period_from": add_days(nowdate(), -60),
			"period_to": add_days(nowdate(), -31),
			"opening_km": opening, "closing_km": closing,
			"previous_tank_balance": previous_tank, "present_tank_balance": present_tank,
			"recoupment_stcbl": 5000,
			"supplier_bill_attachment": "/files/test-supplier-bill.pdf",
			"entries": [{
				"supplier": fuel_supplier("STCBL"),
				"supply_memo_no": f"M-{frappe.generate_hash(length=6)}",
				"date": add_days(nowdate(), -45), "litres": 100, "rate": 100,
			}],
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def test_first_abstract_falls_back_to_the_vehicle_odometer(self):
		result = get_carry_forward(self.vehicle.name)
		self.assertEqual(flt(result["opening_km"]), 10000)
		self.assertEqual(result["source"], "Vehicle")

	def test_opening_km_carries_from_the_previous_closing(self):
		previous = self.make(10000, 11000, 20, 30)
		result = get_carry_forward(self.vehicle.name, nowdate())
		self.assertEqual(flt(result["opening_km"]), 11000)
		self.assertEqual(result["source"], previous.name)

	def test_tank_balance_carries_from_the_previous_present_balance(self):
		self.make(10000, 11000, 20, 30)
		result = get_carry_forward(self.vehicle.name, nowdate())
		self.assertEqual(flt(result["previous_tank_balance"]), 30)

	def test_carry_forward_can_be_switched_off(self):
		self.make(10000, 11000, 20, 30)
		frappe.db.set_single_value("GDL Fleet Settings", "pol_carry_forward_tank_balance", 0)
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
		try:
			result = get_carry_forward(self.vehicle.name, nowdate())
			self.assertIsNone(result["previous_tank_balance"])
		finally:
			frappe.db.set_single_value("GDL Fleet Settings", "pol_carry_forward_tank_balance", 1)
			frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def test_carried_value_can_be_overridden(self):
		"""GDL's own workbook note marks the tank balance 'manual (Assump)'."""
		self.make(10000, 11000, 20, 30)
		later = self.make(
			11000, 12000, 999, 40, submit=False,
			period_from=add_days(nowdate(), -30), period_to=nowdate(),
		)
		self.assertEqual(flt(later.previous_tank_balance), 999)


# ===========================================================================
# 5. Workflow and reports
# ===========================================================================
class TestPOLWorkflowAndReports(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(last_odometer=227953)
		self.vehicle.insert()

	def make_abstract(self, submit=False):
		doc = frappe.get_doc({
			"doctype": "POL Abstract",
			"vehicle": self.vehicle.name,
			"abstract_date": nowdate(),
			"period_from": add_days(nowdate(), -60),
			"period_to": nowdate(),
			"opening_km": 227953, "closing_km": 229032,
			"previous_tank_balance": 40, "present_tank_balance": 60,
			"recoupment_bod": 15000, "recoupment_stcbl": 20000,
			"supplier_bill_attachment": "/files/test-supplier-bill.pdf",
			"entries": [
				{"supplier": fuel_supplier("STCBL"), "supply_memo_no": f"{m}-{frappe.generate_hash(length=4)}",
				 "date": add_days(nowdate(), -30), "litres": l, "rate": r,
				 # The workbook's hand-typed amount: 41.81 x 105.55 is
				 # 4413.0455, but the approved sheet says 4413.04 and that is
				 # the figure that must survive.
				 "total_amount": a}
				for m, l, r, a in (
					("25743", 41.81, 105.55, 4413.04),
					("39883", 58, 104.38, 6054.04),
					("64535", 55, 106.77, 5872.35),
				)
			],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		if submit:
			doc.submit()
		return doc

	# --- workflow -----------------------------------------------------------
	def test_workflow_exists_and_is_active(self):
		self.assertTrue(frappe.db.get_value("Workflow", "GDL POL Approval", "is_active"))

	def test_workflow_is_bound_to_pol_abstract(self):
		self.assertEqual(
			frappe.db.get_value("Workflow", "GDL POL Approval", "document_type"), "POL Abstract"
		)

	def test_driver_submits_and_hr_approves(self):
		transitions = {
			(t.state, t.action): (t.next_state, t.allowed)
			for t in frappe.get_doc("Workflow", "GDL POL Approval").transitions
		}
		self.assertEqual(transitions[("Draft", "Submit for Approval")], ("Submitted", "Fleet Driver"))
		self.assertEqual(transitions[("Submitted", "Approve")], ("Approved", "Fleet HR Approver"))
		self.assertEqual(transitions[("Submitted", "Reject")], ("Rejected", "Fleet HR Approver"))

	def test_rejection_keeps_the_document_editable(self):
		"""frappe cannot return a submitted document to draft, so Rejected is docstatus 0."""
		states = {s.state: int(s.doc_status) for s in frappe.get_doc("Workflow", "GDL POL Approval").states}
		self.assertEqual(states["Rejected"], 0)
		self.assertEqual(states["Submitted"], 0)
		self.assertEqual(states["Approved"], 1)

	def test_approval_history_is_tracked(self):
		self.assertTrue(frappe.get_meta("POL Abstract").track_changes)

	# --- reports ------------------------------------------------------------
	def test_summary_register_reports_the_abstract(self):
		doc = self.make_abstract(submit=True)
		columns, data = frappe.get_attr(
			"gdl_fleet_extension.gdl_fleet.report.pol_summary_register.pol_summary_register.execute"
		)({"vehicle": self.vehicle.name})[:2]
		self.assertTrue(columns)
		row = next(r for r in data if r["name"] == doc.name)
		self.assertEqual(flt(row["total_fuel_consumed"], 2), 134.81)
		self.assertEqual(flt(row["total_km"], 2), 1079)

	def test_supplier_book_balance_shows_each_supply_line(self):
		doc = self.make_abstract(submit=True)
		data = frappe.get_attr(
			"gdl_fleet_extension.gdl_fleet.report.pol_supplier_and_book_balance."
			"pol_supplier_and_book_balance.execute"
		)({"vehicle": self.vehicle.name})[1]
		rows = [r for r in data if r["abstract"] == doc.name]
		self.assertEqual(len(rows), 3)

	def test_book_balance_is_not_repeated_across_lines(self):
		"""Repeating the abstract total on every line would multiply the column sum."""
		doc = self.make_abstract(submit=True)
		data = frappe.get_attr(
			"gdl_fleet_extension.gdl_fleet.report.pol_supplier_and_book_balance."
			"pol_supplier_and_book_balance.execute"
		)({"vehicle": self.vehicle.name})[1]
		rows = [r for r in data if r["abstract"] == doc.name]
		populated = [r for r in rows if r["book_balance_stcbl"] is not None]
		self.assertEqual(len(populated), 1)
		self.assertEqual(flt(populated[0]["book_balance_stcbl"], 2), 3660.57)

	def test_fuel_consumption_report_uses_the_pol_method(self):
		self.make_abstract(submit=True)
		data = frappe.get_attr(
			"gdl_fleet_extension.gdl_fleet.report.fuel_consumption_and_performance."
			"fuel_consumption_and_performance.execute"
		)({"vehicle": self.vehicle.name})[1]
		row = next(r for r in data if r["vehicle"] == self.vehicle.name)
		self.assertEqual(flt(row["total_fuel_consumed"], 2), 134.81)
		self.assertEqual(flt(row["total_fuel_supplied"], 2), 154.81)
		self.assertAlmostEqual(row["performance"], 1079 / 134.81, places=6)

	def test_fuel_consumption_report_exposes_the_tank_balances(self):
		self.make_abstract(submit=True)
		data = frappe.get_attr(
			"gdl_fleet_extension.gdl_fleet.report.fuel_consumption_and_performance."
			"fuel_consumption_and_performance.execute"
		)({"vehicle": self.vehicle.name})[1]
		row = next(r for r in data if r["vehicle"] == self.vehicle.name)
		self.assertEqual(flt(row["previous_tank_balance"], 2), 40)
		self.assertEqual(flt(row["present_tank_balance"], 2), 60)

	# --- print format -------------------------------------------------------
	def test_print_format_exists(self):
		self.assertTrue(frappe.db.exists("Print Format", "POL Abstract"))

	def test_printed_abstract_renders_the_workbook_figures(self):
		doc = self.make_abstract(submit=True)
		html = frappe.get_print("POL Abstract", doc.name, print_format="POL Abstract")
		self.assertIn("POL ABSTRACT", html)
		self.assertIn("154.81", html)
		self.assertIn("134.81", html)
		self.assertIn("1,079.00", html)
		self.assertIn("3,660.57", html)

	def test_printed_abstract_matches_gdl_s_own_form(self):
		"""The printout has to read as the same document as GDL's paper form.

		The layout follows GDL's form. Two units deliberately do not: the paper
		sheet reads "km/hr" against the odometer and "ltrs" against
		performance, and GDL asked for both to be corrected.
		"""
		doc = self.make_abstract(submit=True)
		html = frappe.get_print("POL Abstract", doc.name, print_format="POL Abstract")

		for heading in ("POL ABSTRACT", "Sl No", "Supply Memo No.", "HRS",
		                "Rate", "Amount", "(BOD)", "(STCBL)", "Total:"):
			self.assertIn(heading, html, f"{heading} is missing from the printout")

		for label in ("Total Fuel recoupment(BOD)", "Total Fuel recoupment(STCBL)",
		              "Opening Km", "Closing Km", "Total Km",
		              "Previous tank balance", "Present tank balance",
		              "Fuel book balance(BOD)", "Fuel book balance(STCBL)",
		              "Total fuel consumed", "Performance per litre",
		              "Submitted By:", "Approved by:"):
			self.assertIn(label, html, f"{label} is missing from the printout")

		self.assertIn("Nu/chh.", html, "the form labels the book balance Nu/chh.")

	def test_the_gdl_format_is_what_prints_by_default(self):
		"""Without this the Print button hands the user frappe's generic
		layout and GDL's own form is one dropdown away - which is how people
		conclude the work was never done."""
		self.assertEqual(
			frappe.db.get_value("DocType", "POL Abstract", "default_print_format"),
			"POL Abstract",
		)
		self.assertFalse(frappe.db.get_value("Print Format", "POL Abstract", "disabled"))

	def test_printed_abstract_uses_correct_units(self):
		"""The two units GDL asked to have corrected, and a guard that the
		wrong ones do not come back."""
		doc = self.make_abstract(submit=True)
		html = frappe.get_print("POL Abstract", doc.name, print_format="POL Abstract")
		self.assertIn("KM/L", html, "performance should read KM/L")
		self.assertNotIn("km/hr", html, "the odometer must not be labelled km/hr")
		# "ltrs" is still right for the tank balances and fuel consumed
		self.assertIn("ltrs", html)

	def test_printed_abstract_reproduces_the_workbook_figures(self):
		"""The numbers on the page are the blueprint's own."""
		doc = self.make_abstract(submit=True)
		html = frappe.get_print("POL Abstract", doc.name, print_format="POL Abstract")
		for figure in ("4,413.04", "6,054.04", "5,872.35", "16,339.43",
		               "154.81", "1,079.00", "134.81", "3,660.57", "15,000.00"):
			self.assertIn(figure, html, f"{figure} is not on the printed abstract")

	def test_printed_abstract_has_one_amount_column(self):
		"""One money column, as on the form. The old sheet carried Amount (BOD)
		and Amount (STCBL) side by side and one was always empty."""
		doc = self.make_abstract(submit=True)
		html = frappe.get_print("POL Abstract", doc.name, print_format="POL Abstract")
		header = html.split("<thead>")[1].split("</thead>")[0]
		self.assertNotIn("(BOD)", header, "the line table still splits amount by provider")
		self.assertNotIn("(STCBL)", header)
		self.assertEqual(header.count("Amount"), 1, "there should be exactly one Amount column")

	def test_the_printed_line_table_shows_only_the_money(self):
		"""GDL asked for the line table to carry the amount and nothing else -
		no provider columns, no supplier."""
		doc = self.make_abstract(submit=True)
		html = frappe.get_print("POL Abstract", doc.name, print_format="POL Abstract")
		header = html.split("<thead>")[1].split("</thead>")[0]
		self.assertNotIn("Supplier", header)
		self.assertEqual(
			[" ".join(c.replace("<br>", " ").split())
			 for c in __import__("re").findall(r"<th[^>]*>(.*?)</th>", header, 16)],
			["Sl No", "Supply Memo No.", "Date", "HRS Liters", "Rate (Nu)", "Amount (Nu)"],
		)

	def test_the_printed_total_is_the_sum_of_both_providers(self):
		"""Collapsing two columns into one must not lose a provider's money."""
		doc = self.make_abstract(submit=True)
		html = frappe.get_print("POL Abstract", doc.name, print_format="POL Abstract")
		total = (doc.total_amount_bod or 0) + (doc.total_amount_stcbl or 0)
		self.assertIn("{:,.2f}".format(total), html)


# ===========================================================================
# 6. Nothing standard was disturbed
# ===========================================================================
class TestPOLSafety(IntegrationTestCase):
	def test_fleet_fuel_entry_is_retired(self):
		"""The final document names only POL Abstract + POL Entry for POL."""
		self.assertFalse(frappe.db.exists("DocType", "Fleet Fuel Entry"))

	def test_pol_entry_captures_the_documented_fuel_detail(self):
		"""Fuel Type, Odometer and Driver moved onto the POL entry row."""
		fields = {f.fieldname for f in frappe.get_meta("POL Entry").fields}
		for required in ("fuel_type", "odometer", "driver", "litres", "rate",
		                 "supplier", "supply_memo_no", "date"):
			self.assertIn(required, fields, f"POL Entry is missing {required}")

	def test_pol_entry_no_longer_links_a_fuel_entry(self):
		fields = {f.fieldname for f in frappe.get_meta("POL Entry").fields}
		self.assertNotIn("fleet_fuel_entry", fields)

	def test_vehicle_log_is_untouched_by_pol(self):
		fields = {f.fieldname for f in frappe.get_meta("Vehicle Log").fields}
		self.assertNotIn("pol_abstract", fields)

	def test_pol_adds_no_scheduler_job(self):
		"""POL is driven by the documents, never by a timer.

		The app registers exactly one scheduled job - the CR4 insurance
		purchasing sweep - and nothing in POL may add another.
		"""
		daily = frappe.get_hooks("scheduler_events", app_name="gdl_fleet_extension").get("daily", [])
		self.assertEqual(len(daily), 1, f"an extra scheduled job appeared: {daily}")
		self.assertNotIn("pol", daily[0].lower())
