# Copyright (c) 2026, GDL and contributors
"""Fleet Mgmt.docx 4.2 - date-effective Driver Assignment."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, nowdate

from gdl_fleet_extension.gdl_fleet.doctype.driver_assignment.driver_assignment import (
	get_active_driver,
	get_assignment_history,
	refresh_statuses,
)
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle


def make_driver(name_suffix, licence=None):
	full_name = f"_Test Driver {name_suffix}"
	existing = frappe.db.get_value("Driver", {"full_name": full_name}, "name")
	if existing:
		return existing
	doc = frappe.get_doc({
		"doctype": "Driver", "full_name": full_name, "status": "Active",
		"license_number": licence or f"DL-{name_suffix}",
	})
	doc.insert()
	return doc.name


class TestDriverAssignment(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle()
		self.vehicle.insert()
		self.driver_a = make_driver("A", "DL-AAA-111")
		self.driver_b = make_driver("B", "DL-BBB-222")

	def assign(self, driver, from_date, to_date=None, kind="Primary", submit=True):
		doc = frappe.get_doc({
			"doctype": "Driver Assignment", "vehicle": self.vehicle.name,
			"driver": driver, "assignment_type": kind,
			"from_date": from_date, "to_date": to_date,
		})
		doc.insert()
		if submit:
			doc.submit()
		return doc

	# --- basics ---------------------------------------------------------------
	def test_create_assignment(self):
		doc = self.assign(self.driver_a, add_days(nowdate(), -30))
		self.assertTrue(doc.name.startswith("DA-"))
		self.assertEqual(doc.status, "Active")
		self.assertEqual(doc.docstatus, 1)

	def test_licence_fetched_from_driver(self):
		doc = self.assign(self.driver_a, add_days(nowdate(), -10))
		self.assertEqual(doc.license_no, "DL-AAA-111")

	def test_licence_is_mandatory(self):
		"""The document marks License No. mandatory."""
		self.assertTrue(frappe.get_meta("Driver Assignment").get_field("license_no").reqd)

	def test_from_date_after_to_date_rejected(self):
		doc = frappe.get_doc({
			"doctype": "Driver Assignment", "vehicle": self.vehicle.name,
			"driver": self.driver_a, "assignment_type": "Primary",
			"from_date": add_days(nowdate(), 10), "to_date": add_days(nowdate(), 2),
		})
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_open_ended_assignment_allowed(self):
		doc = self.assign(self.driver_a, add_days(nowdate(), -5), to_date=None)
		self.assertIsNone(doc.to_date)
		self.assertEqual(doc.status, "Active")

	# --- the rule the document is most explicit about -------------------------
	def test_history_is_never_overwritten(self):
		first = self.assign(self.driver_a, add_days(nowdate(), -90),
		                    to_date=add_days(nowdate(), -31))
		second = self.assign(self.driver_b, add_days(nowdate(), -30))

		first.reload()
		self.assertTrue(frappe.db.exists("Driver Assignment", first.name))
		self.assertEqual(first.driver, self.driver_a, "the earlier record was altered")
		self.assertEqual(second.driver, self.driver_b)

		history = get_assignment_history(vehicle=self.vehicle.name)
		self.assertEqual(len(history), 2)

	def test_overlapping_primary_blocked(self):
		self.assign(self.driver_a, add_days(nowdate(), -30))
		clash = frappe.get_doc({
			"doctype": "Driver Assignment", "vehicle": self.vehicle.name,
			"driver": self.driver_b, "assignment_type": "Primary",
			"from_date": add_days(nowdate(), -10),
		})
		self.assertRaises(frappe.ValidationError, clash.insert)

	def test_sequential_primaries_allowed(self):
		self.assign(self.driver_a, add_days(nowdate(), -90),
		            to_date=add_days(nowdate(), -31))
		second = self.assign(self.driver_b, add_days(nowdate(), -30))
		self.assertEqual(second.status, "Active")

	def test_temporary_may_overlap_a_primary(self):
		"""That is the point of a temporary assignment."""
		self.assign(self.driver_a, add_days(nowdate(), -30))
		temp = self.assign(self.driver_b, add_days(nowdate(), -2),
		                   to_date=add_days(nowdate(), 2), kind="Temporary")
		self.assertEqual(temp.status, "Active")

	def test_relief_may_overlap_a_primary(self):
		self.assign(self.driver_a, add_days(nowdate(), -30))
		relief = self.assign(self.driver_b, add_days(nowdate(), -1),
		                     to_date=add_days(nowdate(), 1), kind="Relief")
		self.assertEqual(relief.status, "Active")

	def test_two_primaries_on_different_vehicles_allowed(self):
		other = new_vehicle()
		other.insert()
		self.assign(self.driver_a, add_days(nowdate(), -30))
		doc = frappe.get_doc({
			"doctype": "Driver Assignment", "vehicle": other.name,
			"driver": self.driver_a, "assignment_type": "Primary",
			"from_date": add_days(nowdate(), -30),
		})
		doc.insert()
		doc.submit()
		self.assertEqual(doc.status, "Active")

	# --- active driver lookup -------------------------------------------------
	def test_active_driver_fetched(self):
		self.assign(self.driver_a, add_days(nowdate(), -30))
		self.assertEqual(get_active_driver(self.vehicle.name), self.driver_a)

	def test_temporary_takes_precedence_today(self):
		self.assign(self.driver_a, add_days(nowdate(), -30))
		self.assign(self.driver_b, add_days(nowdate(), -1),
		            to_date=add_days(nowdate(), 1), kind="Temporary")
		self.assertEqual(get_active_driver(self.vehicle.name), self.driver_b)

	def test_active_driver_on_a_past_date(self):
		self.assign(self.driver_a, add_days(nowdate(), -90),
		            to_date=add_days(nowdate(), -31))
		self.assign(self.driver_b, add_days(nowdate(), -30))
		self.assertEqual(
			get_active_driver(self.vehicle.name, add_days(nowdate(), -60)), self.driver_a
		)
		self.assertEqual(get_active_driver(self.vehicle.name), self.driver_b)

	def test_no_driver_before_any_assignment(self):
		self.assign(self.driver_a, add_days(nowdate(), -10))
		self.assertIsNone(get_active_driver(self.vehicle.name, add_days(nowdate(), -60)))

	def test_cancelled_assignment_is_not_active(self):
		doc = self.assign(self.driver_a, add_days(nowdate(), -10))
		doc.cancel()
		self.assertIsNone(get_active_driver(self.vehicle.name))

	def test_vehicle_driver_field_follows_the_assignment(self):
		"""Vehicle.driver becomes derived, not the source of record."""
		self.assign(self.driver_a, add_days(nowdate(), -10))
		self.assertEqual(
			frappe.db.get_value("Vehicle", self.vehicle.name, "driver"), self.driver_a
		)

	# --- status ---------------------------------------------------------------
	def test_past_assignment_becomes_completed(self):
		doc = self.assign(self.driver_a, add_days(nowdate(), -90),
		                  to_date=add_days(nowdate(), -31))
		self.assertEqual(doc.status, "Completed")

	def test_refresh_statuses(self):
		doc = self.assign(self.driver_a, add_days(nowdate(), -10),
		                  to_date=add_days(nowdate(), 5))
		self.assertEqual(doc.status, "Active")
		frappe.db.set_value("Driver Assignment", doc.name, "to_date",
		                    add_days(nowdate(), -1), update_modified=False)
		refresh_statuses()
		self.assertEqual(
			frappe.db.get_value("Driver Assignment", doc.name, "status"), "Completed"
		)

	def test_cancellation_preserves_the_record(self):
		doc = self.assign(self.driver_a, add_days(nowdate(), -10))
		doc.cancel()
		doc.reload()
		self.assertEqual(doc.docstatus, 2)
		self.assertEqual(doc.status, "Cancelled")
		self.assertTrue(frappe.db.exists("Driver Assignment", doc.name))

	def test_history_report_data(self):
		self.assign(self.driver_a, add_days(nowdate(), -90),
		            to_date=add_days(nowdate(), -31))
		self.assign(self.driver_b, add_days(nowdate(), -30))
		rows = get_assignment_history(vehicle=self.vehicle.name)
		for key in ("vehicle", "driver", "license_no", "assignment_type",
		            "from_date", "to_date", "status"):
			self.assertIn(key, rows[0])
