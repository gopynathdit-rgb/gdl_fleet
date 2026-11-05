# Copyright (c) 2026, GDL and contributors
"""
Phase 15 - alerts as STANDARD frappe Notification records.

frappe already runs `trigger_daily_alerts` and `trigger_offset_alerts` from its
own hooks, so every date-based alert here is configuration, not a scheduler job.
This app registers NO scheduler_events at all.

Notification types used:
    Days Before   a date field on the document (expiries, service due dates)
    Days After    a date that has passed (overdue)
    Value Change  a workflow state moving (approvals, assignment)
    Submit        a document being submitted (incident raised)

Lead times come from GDL Fleet Settings so GDL can retune them without a deploy.
"""

import frappe
from frappe.utils import cint

GDL_PREFIX = "GDL Fleet:"


def _notification(
	name, document_type, event, subject, message,
	date_changed=None, days_in_advance=None, value_changed=None,
	condition=None, recipients=None, channel="Email",
):
	return {
		"name": f"{GDL_PREFIX} {name}",
		"document_type": document_type,
		"event": event,
		"subject": subject,
		"message": message,
		"date_changed": date_changed,
		"days_in_advance": days_in_advance,
		"value_changed": value_changed,
		"condition": condition,
		"recipients": recipients or [],
		"channel": channel,
	}


def rung(value, fallback):
	"""A rung of the reminder ladder, or None when GDL has switched it off.

	`cint(value) or fallback` cannot express "off": zero is exactly what a
	user types to silence a reminder, and it would be read as "unset" and
	replaced by the fallback. So an unset field takes the fallback and an
	explicit 0 means off.
	"""
	if value in (None, ""):
		return fallback or None
	days = cint(value)
	return days if days > 0 else None


def get_notification_definitions():
	settings = frappe.get_single("GDL Fleet Settings")
	first = rung(settings.get("renewal_notice_days"), 14)
	second = rung(settings.get("renewal_second_reminder_days"), 3)
	third = rung(settings.get("renewal_third_reminder_days"), 0)
	final = rung(settings.get("renewal_final_reminder_days"), 0)
	maintenance_notice = cint(settings.get("maintenance_due_notice_days")) or 14
	# OBS-002: a driving licence is not an insurance policy. It takes longer to
	# replace, and tying it to the renewal ladder meant changing the insurance
	# reminder silently changed the licence one. It now has its own rung.
	licence_notice = rung(settings.get("licence_expiry_notice_days"), 30)

	fleet_admin = [{"receiver_by_role": "Fleet Administrator"}]
	fleet_manager = [{"receiver_by_role": "Fleet Manager"}]
	maintenance_user = [{"receiver_by_role": "Fleet Maintenance User"}]

	not_disposed = "doc.vehicle_status != 'Disposed'"

	return [
		# --- renewal register (section 4.6) ------------------------------------
		# One notification per rung of the configured ladder. The document quotes
		# 14 days in section 3 and the 4.6 heading, 30 in the 4.6 trigger detail
		# and 30/15/7 in section 5, so every value is configuration.
		_notification(
			"Renewal Due (First Reminder)", "Renewal Register", "Days Before",
			"{{ doc.renewal_type }} for {{ doc.vehicle }} expires on {{ doc.expiry_date }}",
			"**{{ doc.renewal_type }}** for vehicle **{{ doc.vehicle }}** "
			"(certificate {{ doc.certificate_no }}, {{ doc.provider }}) expires on "
			"{{ doc.expiry_date }}.",
			date_changed="expiry_date", days_in_advance=first,
			condition="doc.renewal_status not in ('Renewed', 'Expired')",
			recipients=fleet_admin,
		),
		_notification(
			"Renewal Due (Second Reminder)", "Renewal Register", "Days Before",
			"Reminder: {{ doc.renewal_type }} for {{ doc.vehicle }} expires {{ doc.expiry_date }}",
			"{{ doc.renewal_type }} for {{ doc.vehicle }} expires on {{ doc.expiry_date }}.",
			date_changed="expiry_date", days_in_advance=second,
			condition="doc.renewal_status not in ('Renewed', 'Expired')",
			recipients=fleet_admin,
		),
		_notification(
			"Renewal Due (Third Reminder)", "Renewal Register", "Days Before",
			"Urgent: {{ doc.renewal_type }} for {{ doc.vehicle }} expires {{ doc.expiry_date }}",
			"{{ doc.renewal_type }} for {{ doc.vehicle }} expires on {{ doc.expiry_date }}.",
			date_changed="expiry_date", days_in_advance=third,
			condition="doc.renewal_status not in ('Renewed', 'Expired')",
			recipients=fleet_admin + fleet_manager,
		),
		_notification(
			"Renewal Due (Final Reminder)", "Renewal Register", "Days Before",
			"Final notice: {{ doc.renewal_type }} for {{ doc.vehicle }} expires {{ doc.expiry_date }}",
			"{{ doc.renewal_type }} for {{ doc.vehicle }} expires on {{ doc.expiry_date }}. "
			"Renew it now to keep the vehicle on the road.",
			date_changed="expiry_date", days_in_advance=final,
			condition="doc.renewal_status not in ('Renewed', 'Expired')",
			recipients=fleet_admin + fleet_manager,
		),
		_notification(
			"Renewal Expired", "Renewal Register", "Days After",
			"{{ doc.renewal_type }} for {{ doc.vehicle }} has EXPIRED",
			"{{ doc.renewal_type }} for vehicle {{ doc.vehicle }} expired on "
			"{{ doc.expiry_date }} and has not been renewed.",
			date_changed="expiry_date", days_in_advance=1,
			condition="doc.renewal_status not in ('Renewed',)",
			recipients=fleet_admin + fleet_manager,
		),
		_notification(
			"Driving Licence Expiry", "Driver", "Days Before",
			"Driving licence for {{ doc.full_name }} expires on {{ doc.expiry_date }}",
			"The driving licence for **{{ doc.full_name }}** expires on "
			"{{ doc.expiry_date }} (licence {{ doc.license_number }}).",
			date_changed="expiry_date", days_in_advance=licence_notice,
			condition="doc.status == 'Active'", recipients=fleet_manager,
		),
		# --- maintenance ------------------------------------------------------
		_notification(
			"Maintenance Due", "Asset Maintenance Log", "Days Before",
			"Maintenance due for {{ doc.vehicle }}",
			"**{{ doc.task_name }}** is due on {{ doc.due_date }} for vehicle "
			"{{ doc.vehicle }}.",
			date_changed="due_date", days_in_advance=maintenance_notice,
			condition="doc.maintenance_status != 'Completed'", recipients=maintenance_user,
		),
		_notification(
			"Maintenance Overdue", "Asset Maintenance Log", "Days After",
			"Maintenance OVERDUE for {{ doc.vehicle }}",
			"**{{ doc.task_name }}** was due on {{ doc.due_date }} for vehicle "
			"{{ doc.vehicle }} and is still outstanding.",
			date_changed="due_date", days_in_advance=1,
			condition="doc.maintenance_status != 'Completed'", recipients=fleet_manager,
		),
		# --- booking ----------------------------------------------------------
		_notification(
			"Movement Request Pending Review", "Movement Order Request", "Value Change",
			"Movement request {{ doc.name }} is awaiting review",
			"{{ doc.requester }} has requested a {{ doc.vehicle_type }} for "
			"{{ doc.required_date }} ({{ doc.pickup_location }} to {{ doc.destination }}).",
			value_changed="workflow_state",
			condition="doc.workflow_state == 'Pending Review'",
			recipients=[{"receiver_by_role": "Fleet Reviewer"}], channel="System Notification",
		),
		_notification(
			"Movement Request Accepted", "Movement Order Request", "Value Change",
			"Movement request {{ doc.name }} was accepted",
			"Vehicle **{{ doc.vehicle }}** and driver {{ doc.driver }} have been assigned "
			"for {{ doc.required_date }} {{ doc.required_from_time }}.",
			value_changed="workflow_state", condition="doc.workflow_state == 'Accepted'",
			recipients=[{"receiver_by_document_field": "requester"}],
		),
		_notification(
			"Movement Request Rejected", "Movement Order Request", "Value Change",
			"Movement request {{ doc.name }} was not accepted",
			"Your vehicle request for {{ doc.required_date }} was not approved.",
			value_changed="workflow_state", condition="doc.workflow_state == 'Rejected'",
			recipients=[{"receiver_by_document_field": "requester"}],
		),
		_notification(
			"Movement Order Pending Approval", "Movement Order", "Value Change",
			"Movement Order {{ doc.name }} is awaiting approval",
			"Vehicle {{ doc.vehicle }} with driver {{ doc.driver }} is requested for "
			"{{ doc.departure_datetime }} to {{ doc.destination }}.",
			value_changed="workflow_state",
			condition="doc.workflow_state == 'Pending Approval'",
			recipients=[{"receiver_by_role": "Fleet Approver"}],
			channel="System Notification",
		),
	]


def create_notifications():
	"""Idempotent. Creates missing notifications; never overwrites GDL's edits.

	The one thing that IS kept in sync on an existing record is the day count,
	because that number is the setting - changing "remind me 14 days before"
	in GDL Fleet Settings has to reach the alert, or the setting is a lie.
	Subject, message and recipients are left exactly as GDL has them.
	"""
	created, skipped, retuned, switched_off = [], [], [], []

	wanted = get_notification_definitions()

	# A reminder whose rung is set to 0 is off. Its definition is dropped here,
	# and an alert created by an earlier release is disabled rather than
	# deleted - GDL may switch the rung back on tomorrow.
	live = []
	for spec in wanted:
		if spec.get("event") == "Days Before" and spec.get("days_in_advance") is None:
			name = spec["name"]
			if frappe.db.exists("Notification", name) and frappe.db.get_value(
				"Notification", name, "enabled"
			):
				frappe.db.set_value("Notification", name, "enabled", 0, update_modified=False)
				switched_off.append(name)
			continue
		live.append(spec)

	for spec in live:
		name = spec.pop("name")
		if frappe.db.exists("Notification", name):
			current = frappe.db.get_value(
				"Notification", name, ["days_in_advance", "enabled"], as_dict=True
			)
			if spec.get("days_in_advance") is not None and \
			   cint(current.days_in_advance) != cint(spec["days_in_advance"]):
				frappe.db.set_value("Notification", name, "days_in_advance",
				                    spec["days_in_advance"], update_modified=False)
				retuned.append(f"{name} -> {spec['days_in_advance']}d")
			if not current.enabled:
				frappe.db.set_value("Notification", name, "enabled", 1, update_modified=False)
			# Groups the alert under Fleet in the Notification list. Earlier
			# releases left this blank, so backfill it without touching
			# anything else GDL may have tuned on the record.
			if not frappe.db.get_value("Notification", name, "module"):
				frappe.db.set_value("Notification", name, "module", "GDL Fleet",
				                    update_modified=False)
			skipped.append(name)
			continue

		recipients = spec.pop("recipients")
		doc = frappe.get_doc(
			{
				"doctype": "Notification",
				"name": name,
				"module": "GDL Fleet",
				"enabled": 1,
				"is_standard": 0,
				"send_system_notification": 1 if spec.get("channel") == "System Notification" else 0,
				**{k: v for k, v in spec.items() if v is not None},
			}
		)
		for recipient in recipients:
			doc.append("recipients", recipient)

		doc.flags.ignore_permissions = True
		doc.insert()
		created.append(name)

	return {
		"created": created,
		"already_present": skipped,
		"day_count_synced": retuned,
		"switched_off": switched_off,
	}


@frappe.whitelist()
def notification_status() -> list[dict]:
	return frappe.get_all(
		"Notification",
		filters={"name": ("like", f"{GDL_PREFIX}%")},
		fields=["name", "document_type", "event", "date_changed", "days_in_advance",
		        "channel", "enabled"],
		order_by="name",
	)
