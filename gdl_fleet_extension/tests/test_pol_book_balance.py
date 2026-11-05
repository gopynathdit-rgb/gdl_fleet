# Copyright (c) 2026, GDL and contributors
"""
The fuel coupon's running to-date amount.

Business Blueprint, POL Management:
    "There is a provision to maintain the fuel coupon from two different fuel
    provider - BOD and STCBL where to to-date amount should be maintained."

A coupon book is not emptied and reissued each period. Whatever is left
unspent belongs to the next period, so

    closing = opening + recouped - spent

and that closing figure is the next abstract's opening. These tests pin the
arithmetic, the carry forward, and - most importantly - the cases where it
must NOT carry: an unapproved abstract, a different vehicle, the setting off.
"""

from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from gdl_fleet_extension.gdl_fleet.doctype.pol_abstract.pol_abstract import (
	get_book_balance_carry_forward,
	get_vehicle_book_balance,
)
from gdl_fleet_extension.tests.fleet_settings_guard import FleetSettingsGuard
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
from gdl_fleet_extension.utils.pol import fuel_book_balance
from gdl_fleet_extension.tests.test_pol import fuel_supplier


class TestBookBalanceArithmetic(IntegrationTestCase):
	def test_closing_is_opening_plus_recouped_minus_spent(self):
		self.assertEqual(fuel_book_balance(5000, 3000, 2, 1200), Decimal("3200.00"))

	def test_no_opening_is_the_old_behaviour(self):
		"""Every abstract already on file was calculated this way, so its
		recorded closing balance must not change."""
		self.assertEqual(fuel_book_balance(5000, 3000, 2), Decimal("2000.00"))
		self.assertEqual(fuel_book_balance(5000, 3000, 2, 0), Decimal("2000.00"))

	def test_a_blank_amount_deducts_nothing(self):
		"""Both workbook sheets leave the BOD amount empty."""
		self.assertEqual(fuel_book_balance(5000, None, 2, 500), Decimal("5500.00"))

	def test_overspending_gives_a_negative_balance(self):
		"""Spending more than the coupon holds is a real situation and must
		show as a debt, not be floored at zero."""
		self.assertEqual(fuel_book_balance(1000, 4000, 2, 500), Decimal("-2500.00"))


class TestCarryForward(FleetSettingsGuard, IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.vehicle = new_vehicle(last_odometer=10000)
		self.vehicle.insert()
		self.other = new_vehicle(last_odometer=10000)
		self.other.insert()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def make_abstract(self, recoupment_stcbl, spend, days_ago, vehicle=None, submit=True):
		"""One abstract with a single STCBL line of the given value."""
		start = add_days(nowdate(), -days_ago)
		doc = frappe.get_doc({
			"doctype": "POL Abstract",
			"vehicle": (vehicle or self.vehicle).name,
			"abstract_date": start,
			"period_from": start,
			"period_to": add_days(start, 20),
			"distance_basis": "KM",
			"opening_km": 10000,
			"closing_km": 10500,
			"previous_tank_balance": 0,
			"present_tank_balance": 0,
			"recoupment_bod": 0,
			"recoupment_stcbl": recoupment_stcbl,
			"supplier_bill_attachment": "/files/test-supplier-bill.pdf",
			"deviation_reason": "Test fixture - mileage not under test here.",
			"entries": [{
				# The supplier is the routing key now - it decides whether the
				# amount lands in the BOD claim or the STCBL one.
				"supplier": fuel_supplier("STCBL"),
				"supply_memo_no": f"BB-{days_ago}-{int(spend)}",
				"date": add_days(start, 1),
				"litres": 50, "rate": spend / 50 if spend else 0,
				"total_amount": spend,
			}],
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		if submit:
			doc.submit()
		return doc

	# --- the running balance ------------------------------------------------
	def test_the_first_abstract_opens_at_zero(self):
		first = self.make_abstract(recoupment_stcbl=10000, spend=4000, days_ago=60)
		self.assertEqual(flt(first.opening_book_balance_stcbl), 0.0)
		self.assertEqual(flt(first.fuel_book_balance_stcbl), 6000.0)

	def test_the_unspent_balance_opens_the_next_period(self):
		self.make_abstract(recoupment_stcbl=10000, spend=4000, days_ago=60)
		second = self.make_abstract(recoupment_stcbl=5000, spend=3000, days_ago=30)
		self.assertEqual(flt(second.opening_book_balance_stcbl), 6000.0)
		# 6000 brought in + 5000 recouped - 3000 spent
		self.assertEqual(flt(second.fuel_book_balance_stcbl), 8000.0)

	def test_the_balance_accumulates_across_three_periods(self):
		self.make_abstract(recoupment_stcbl=10000, spend=4000, days_ago=90)
		self.make_abstract(recoupment_stcbl=5000, spend=3000, days_ago=60)
		third = self.make_abstract(recoupment_stcbl=2000, spend=1000, days_ago=30)
		self.assertEqual(flt(third.opening_book_balance_stcbl), 8000.0)
		self.assertEqual(flt(third.fuel_book_balance_stcbl), 9000.0)

	def test_the_to_date_amount_is_readable_for_a_vehicle(self):
		self.make_abstract(recoupment_stcbl=10000, spend=4000, days_ago=60)
		balance = get_vehicle_book_balance(self.vehicle.name)
		self.assertEqual(balance["stcbl"], 6000.0)

	# --- where it must NOT carry -------------------------------------------
	def test_a_draft_abstract_does_not_move_the_balance(self):
		"""An unapproved claim is not an agreed balance."""
		self.make_abstract(recoupment_stcbl=10000, spend=4000, days_ago=60, submit=False)
		carry = get_book_balance_carry_forward(self.vehicle.name)
		self.assertEqual(carry["stcbl"], 0.0)
		self.assertIsNone(carry["source"])

	def test_another_vehicle_has_its_own_coupon_book(self):
		self.make_abstract(recoupment_stcbl=10000, spend=4000, days_ago=60)
		carry = get_book_balance_carry_forward(self.other.name)
		self.assertEqual(carry["stcbl"], 0.0)

	def test_a_vehicle_with_no_history_opens_at_zero(self):
		carry = get_book_balance_carry_forward(self.other.name)
		self.assertEqual(carry, {"bod": 0.0, "stcbl": 0.0, "source": None})

	def test_no_vehicle_yet_is_not_an_error(self):
		"""The form calculates before a vehicle is chosen."""
		self.assertEqual(get_book_balance_carry_forward(None)["stcbl"], 0.0)

	def test_switching_the_carry_forward_off_restores_the_old_behaviour(self):
		self.make_abstract(recoupment_stcbl=10000, spend=4000, days_ago=60)
		settings = frappe.get_single("GDL Fleet Settings")
		settings.pol_carry_forward_book_balance = 0
		settings.flags.ignore_permissions = True
		settings.save()
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

		second = self.make_abstract(recoupment_stcbl=5000, spend=3000, days_ago=30)
		self.assertEqual(flt(second.opening_book_balance_stcbl), 0.0)
		self.assertEqual(flt(second.fuel_book_balance_stcbl), 2000.0)

	def test_the_opening_balance_cannot_be_typed_over(self):
		"""Read-only on the form, and recomputed on every save - otherwise the
		running total drifts away from the abstract it came from."""
		self.assertTrue(
			frappe.get_meta("POL Abstract").get_field("opening_book_balance_stcbl").read_only
		)
		self.make_abstract(recoupment_stcbl=10000, spend=4000, days_ago=60)
		second = self.make_abstract(recoupment_stcbl=5000, spend=3000, days_ago=30, submit=False)
		second.opening_book_balance_stcbl = 999999
		second.save()
		self.assertEqual(flt(second.opening_book_balance_stcbl), 6000.0)

	def test_an_earlier_period_does_not_read_a_later_one(self):
		"""Abstracts are not always entered in order."""
		self.make_abstract(recoupment_stcbl=10000, spend=4000, days_ago=30)
		earlier = self.make_abstract(recoupment_stcbl=5000, spend=1000, days_ago=90)
		self.assertEqual(flt(earlier.opening_book_balance_stcbl), 0.0)
