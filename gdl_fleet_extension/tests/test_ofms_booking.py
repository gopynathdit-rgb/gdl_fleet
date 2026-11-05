# Copyright (c) 2026, GDL and contributors
"""
OFMS online booking rules on Movement Order Request.

Final document, GAP item 1: "Online booking / requisition (OFMS): with
lead-time rules & allocation priority".

GDL directed that this extends Movement Order Request rather than the older
Vehicle Request DocType, so there is one request process rather than two.
"""

import frappe
from frappe.tests import IntegrationTestCase

from gdl_fleet_extension.tests.fleet_settings_guard import FleetSettingsGuard
from frappe.utils import add_days, add_to_date, flt, nowdate

from gdl_fleet_extension.tests.test_movement_order_request import new_booking


class TestBookingLeadTime(FleetSettingsGuard, IntegrationTestCase):
	def setUp(self):
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def tearDown(self):
		frappe.db.set_single_value("GDL Fleet Settings", "booking_lead_time_hours", 24)
		frappe.db.set_single_value("GDL Fleet Settings", "booking_lead_time_action", "Require Reason")
		frappe.db.set_single_value("GDL Fleet Settings", "emergency_bypasses_lead_time", 1)
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def book(self, days_ahead=3, **kwargs):
		doc = new_booking(required_date=add_days(nowdate(), days_ahead), **kwargs)
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc

	def setting(self, field, value):
		frappe.db.set_single_value("GDL Fleet Settings", field, value)
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	# --- lead time measurement ------------------------------------------
	def test_lead_time_is_recorded(self):
		doc = self.book(days_ahead=3)
		self.assertGreater(flt(doc.lead_time_hours), 48)

	def test_ample_notice_needs_no_reason(self):
		doc = self.book(days_ahead=7)
		self.assertIsNone(doc.lead_time_waiver_reason)

	# --- short notice ----------------------------------------------------
	def test_short_notice_requires_a_reason(self):
		self.assertRaises(frappe.ValidationError, self.book, 0)

	def test_short_notice_passes_with_a_reason(self):
		doc = self.book(0, lead_time_waiver_reason="Minister's delegation arrived unannounced")
		self.assertLess(flt(doc.lead_time_hours), 24)

	def test_emergency_bypasses_the_lead_time(self):
		doc = self.book(0, priority="Emergency")
		self.assertEqual(doc.priority, "Emergency")

	def test_emergency_bypass_can_be_switched_off(self):
		self.setting("emergency_bypasses_lead_time", 0)
		self.assertRaises(frappe.ValidationError, self.book, 0, priority="Emergency")

	def test_block_action_refuses_outright(self):
		self.setting("booking_lead_time_action", "Block")
		self.assertRaises(frappe.ValidationError, self.book, 0,
		                  lead_time_waiver_reason="Still not allowed under Block")

	def test_warn_action_lets_it_through(self):
		self.setting("booking_lead_time_action", "Warn")
		doc = self.book(0)
		self.assertLess(flt(doc.lead_time_hours), 24)

	def test_lead_time_hours_is_configurable(self):
		"""Booking two days out always clears a one-hour rule.

		Deliberately NOT booked for today: the fixture departs at 08:00, so a
		same-day booking made in the afternoon has negative notice and the
		result would depend on the time of day the suite happens to run.
		"""
		self.setting("booking_lead_time_hours", 1)
		doc = self.book(2)
		self.assertTrue(doc.name)
		self.assertGreater(flt(doc.lead_time_hours), 1)

	def test_zero_lead_time_disables_the_rule(self):
		self.setting("booking_lead_time_hours", 0)
		doc = self.book(0)
		self.assertTrue(doc.name)


class TestAllocationPriority(IntegrationTestCase):
	def book(self, days_ahead=3, **kwargs):
		doc = new_booking(required_date=add_days(nowdate(), days_ahead), **kwargs)
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc

	def test_emergency_outranks_critical_outranks_routine(self):
		emergency = self.book(5, priority="Emergency")
		critical = self.book(5, priority="Critical Business")
		routine = self.book(5, priority="Routine")
		self.assertLess(emergency.allocation_priority, critical.allocation_priority)
		self.assertLess(critical.allocation_priority, routine.allocation_priority)

	def test_more_notice_wins_a_tie(self):
		early = self.book(10, priority="Routine")
		late = self.book(2, priority="Routine")
		self.assertLess(early.allocation_priority, late.allocation_priority,
		                "of two equal requests the one booked further ahead is served first")

	def test_priority_dominates_notice(self):
		"""An emergency booked at the last minute still beats a routine booked early."""
		emergency = self.book(0, priority="Emergency")
		routine = self.book(14, priority="Routine")
		self.assertLess(emergency.allocation_priority, routine.allocation_priority)

	def test_priority_is_always_set(self):
		self.assertIsNotNone(self.book(3).allocation_priority)


class TestOfmsUsesOneRequestProcess(IntegrationTestCase):
	def test_booking_rules_live_on_movement_order_request(self):
		fields = {f.fieldname for f in frappe.get_meta("Movement Order Request").fields}
		for f in ("lead_time_hours", "lead_time_waiver_reason", "allocation_priority"):
			self.assertIn(f, fields)

	def test_no_second_request_doctype_was_created(self):
		"""GDL directed that OFMS extends the existing request, not a new form."""
		for name in ("OFMS Request", "Vehicle Booking", "Online Vehicle Request"):
			self.assertFalse(frappe.db.exists("DocType", name))
