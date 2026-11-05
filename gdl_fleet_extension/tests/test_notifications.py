# Copyright (c) 2026, GDL and contributors
"""Phase 15 - alerts as standard frappe Notifications, with no scheduler job."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import cint

from gdl_fleet_extension.setup.notifications import GDL_PREFIX, notification_status

EXPECTED = {
	"Renewal Due (First Reminder)": ("Renewal Register", "Days Before", "expiry_date"),
	"Renewal Due (Second Reminder)": ("Renewal Register", "Days Before", "expiry_date"),
	"Renewal Due (Third Reminder)": ("Renewal Register", "Days Before", "expiry_date"),
	"Renewal Due (Final Reminder)": ("Renewal Register", "Days Before", "expiry_date"),
	"Renewal Expired": ("Renewal Register", "Days After", "expiry_date"),
	"Driving Licence Expiry": ("Driver", "Days Before", "expiry_date"),
	"Maintenance Due": ("Asset Maintenance Log", "Days Before", "due_date"),
	"Maintenance Overdue": ("Asset Maintenance Log", "Days After", "due_date"),
	"Movement Request Pending Review": ("Movement Order Request", "Value Change", None),
	"Movement Request Accepted": ("Movement Order Request", "Value Change", None),
	"Movement Request Rejected": ("Movement Order Request", "Value Change", None),
	"Movement Order Pending Approval": ("Movement Order", "Value Change", None),
}

# Client answer, 3 Nov 2026: the ladder is 14 days, 3 days and the expiry day.
# The two spare rungs ship switched off, so these two alerts are either absent
# (a fresh site never created them) or present and disabled (an existing site
# had them before the answer arrived). Both are correct; neither is required.
OPTIONAL_RUNGS = (
	"Renewal Due (Third Reminder)",
	"Renewal Due (Final Reminder)",
)

REQUIRED = {k: v for k, v in EXPECTED.items() if k not in OPTIONAL_RUNGS}


def live_notifications():
	"""The alerts that exist on this site and are switched on."""
	return {
		label for label in EXPECTED
		if frappe.db.get_value("Notification", f"{GDL_PREFIX} {label}", "enabled")
	}


class TestFleetNotifications(IntegrationTestCase):
	def test_out_of_scope_notifications_removed(self):
		for label in ("Mileage Deviation Raised", "Spare Part Approval Pending",
		              "Accident Reported", "Accident Pending Action"):
			self.assertFalse(
				frappe.db.exists("Notification", f"{GDL_PREFIX} {label}"),
				f"{label} is not in the final scope",
			)

	def test_all_notifications_exist_and_are_enabled(self):
		for label, (doctype, event, date_field) in REQUIRED.items():
			name = f"{GDL_PREFIX} {label}"
			self.assertTrue(frappe.db.exists("Notification", name), f"missing {name}")

			row = frappe.db.get_value(
				"Notification", name,
				["document_type", "event", "date_changed", "enabled"], as_dict=True,
			)
			self.assertEqual(row.document_type, doctype, f"{label} document type")
			self.assertEqual(row.event, event, f"{label} event")
			self.assertTrue(row.enabled, f"{label} is disabled")
			if date_field:
				self.assertEqual(row.date_changed, date_field, f"{label} date field")

	def test_the_alerts_do_not_rely_on_a_scheduler_job_of_our_own(self):
		"""Renewal and maintenance alerts are frappe Notifications.

		frappe's own trigger_daily_alerts drives them, so this app adds no job
		for them. The one job it does register is the insurance purchasing
		sweep from CR4, which exists because a policy expires on a date whether
		or not anyone opens the record.
		"""
		daily = frappe.get_hooks("scheduler_events", app_name="gdl_fleet_extension").get("daily", [])
		self.assertEqual(
			len(daily), 1,
			f"expected exactly one scheduled job, found: {daily}")
		self.assertIn("daily_fleet_purchasing", daily[0])

		for job in daily:
			self.assertNotIn("notification", job.lower(),
			                 "alerts must stay with frappe's own trigger_daily_alerts")

	def test_frappe_runs_the_date_based_alerts(self):
		daily = frappe.get_hooks("scheduler_events", app_name="frappe").get("daily", [])
		self.assertIn(
			"frappe.email.doctype.notification.notification.trigger_daily_alerts", daily
		)

	def test_date_based_alerts_have_a_lead_time(self):
		for label, (_doctype, event, _date_field) in EXPECTED.items():
			if event not in ("Days Before", "Days After"):
				continue
			days = frappe.db.get_value(
				"Notification", f"{GDL_PREFIX} {label}", "days_in_advance"
			)
			self.assertTrue(cint(days) > 0, f"{label} has no lead time")

	def test_renewal_alerts_skip_renewed_records(self):
		for label in ("Renewal Due (First Reminder)", "Renewal Due (Final Reminder)"):
			condition = frappe.db.get_value(
				"Notification", f"{GDL_PREFIX} {label}", "condition"
			)
			self.assertIn("Renewed", condition, f"{label} would alert on a renewed record")

	def test_renewal_ladder_is_configured_and_descending(self):
		"""Escalating reminders, with the days coming from settings.

		Only the rungs GDL has switched ON are read. A rung set to 0 means
		"do not remind me then", and its alert is disabled rather than firing
		zero days in advance.
		"""
		days = [
			cint(frappe.db.get_value("Notification", f"{GDL_PREFIX} {label}", "days_in_advance"))
			for label in ("Renewal Due (First Reminder)", "Renewal Due (Second Reminder)",
			              "Renewal Due (Third Reminder)", "Renewal Due (Final Reminder)")
			if label in live_notifications()
		]
		self.assertTrue(days, "every renewal reminder is switched off")
		self.assertEqual(days, sorted(days, reverse=True), f"ladder is not descending: {days}")
		self.assertTrue(all(d > 0 for d in days), f"a live rung has no lead time: {days}")

	def test_the_ladder_matches_the_settings(self):
		"""The number in GDL Fleet Settings is the number the alert fires on."""
		pairs = [
			("renewal_notice_days", "Renewal Due (First Reminder)"),
			("renewal_second_reminder_days", "Renewal Due (Second Reminder)"),
			("renewal_third_reminder_days", "Renewal Due (Third Reminder)"),
			("renewal_final_reminder_days", "Renewal Due (Final Reminder)"),
		]
		live = live_notifications()
		for fieldname, label in pairs:
			configured = cint(frappe.db.get_single_value("GDL Fleet Settings", fieldname))
			if configured <= 0:
				self.assertNotIn(label, live, f"{label} is on but {fieldname} is 0")
				continue
			self.assertIn(label, live, f"{fieldname} is {configured} but {label} is off")
			self.assertEqual(
				cint(frappe.db.get_value("Notification", f"{GDL_PREFIX} {label}",
				                         "days_in_advance")),
				configured,
				f"{label} does not fire on the day {fieldname} asks for",
			)

	def test_recipients_are_roles_or_document_fields(self):
		"""No user is hard-coded into an alert."""
		for label in EXPECTED:
			rows = frappe.get_all(
				"Notification Recipient",
				filters={"parent": f"{GDL_PREFIX} {label}"},
				fields=["receiver_by_role", "receiver_by_document_field"],
			)
			self.assertTrue(rows, f"{label} has no recipients")
			for row in rows:
				self.assertTrue(
					row.receiver_by_role or row.receiver_by_document_field,
					f"{label} has a recipient that is neither a role nor a document field",
				)

	def test_no_duplicate_notifications(self):
		names = [r["name"] for r in notification_status()]
		self.assertEqual(len(names), len(set(names)))
		self.assertGreaterEqual(len(names), len(REQUIRED))
		self.assertLessEqual(len(names), len(EXPECTED))

	def test_creation_is_idempotent(self):
		from gdl_fleet_extension.setup.notifications import create_notifications

		result = create_notifications()
		self.assertEqual(result["created"], [])
		self.assertEqual(len(result["already_present"]), len(live_notifications()))

	def test_alert_documents_still_have_their_date_fields(self):
		"""A renamed field would silently stop an alert firing."""
		for label, (doctype, event, date_field) in EXPECTED.items():
			if not date_field:
				continue
			self.assertTrue(
				frappe.get_meta(doctype).get_field(date_field),
				f"{doctype}.{date_field} is missing - {label} would never fire",
			)
