# Copyright (c) 2026, GDL and contributors
"""
Fleet Mgmt.docx section 4.5 - Insurance and Annual Renewal Register.

The document requires renewal history to be retained rather than prior policy
records being replaced. Each renewal is its own submitted record and chains to
the one it supersedes through `previous_renewal`; the superseded record is
marked Renewed but never edited away.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, date_diff, getdate, nowdate


class RenewalRegister(Document):
	def validate(self):
		self.validate_dates()
		self.validate_previous_renewal()
		self.set_status()

	def on_submit(self):
		self.mark_previous_as_renewed()
		self.sync_vehicle_convenience_fields()

	def on_cancel(self):
		self.db_set("renewal_status", "Expired" if self.is_expired() else "Valid")

	# ------------------------------------------------------------------
	def validate_dates(self):
		if self.effective_from and getdate(self.expiry_date) < getdate(self.effective_from):
			frappe.throw(
				_("Expiry Date cannot be before Effective From."),
				title=_("Invalid Validity Period"),
			)

	def validate_previous_renewal(self):
		if not self.previous_renewal:
			return

		previous = frappe.db.get_value(
			"Renewal Register", self.previous_renewal,
			["vehicle", "renewal_type", "expiry_date"], as_dict=True,
		)
		if not previous:
			return

		if previous.vehicle != self.vehicle:
			frappe.throw(
				_("The previous renewal belongs to vehicle {0}, not {1}.").format(
					frappe.bold(previous.vehicle), frappe.bold(self.vehicle)
				)
			)
		if previous.renewal_type != self.renewal_type:
			frappe.throw(
				_("The previous renewal is a {0} record, not {1}.").format(
					frappe.bold(previous.renewal_type), frappe.bold(self.renewal_type)
				)
			)

	def is_expired(self):
		return getdate(self.expiry_date) < getdate(nowdate())

	def set_status(self):
		"""Valid / Due Soon / Expired, with the notice window from configuration."""
		if self.renewal_status == "Renewed":
			return

		notice_days = get_primary_notice_days()
		self.days_to_expiry = date_diff(getdate(self.expiry_date), getdate(nowdate()))

		if self.days_to_expiry < 0:
			self.renewal_status = "Expired"
		elif self.days_to_expiry <= notice_days:
			self.renewal_status = "Due Soon"
		else:
			self.renewal_status = "Valid"

	def mark_previous_as_renewed(self):
		"""Close the superseded record without editing its own particulars."""
		if not self.previous_renewal:
			return
		frappe.db.set_value(
			"Renewal Register", self.previous_renewal, "renewal_status", "Renewed",
			update_modified=False,
		)

	def sync_vehicle_convenience_fields(self):
		"""Keep the Vehicle's current insurance display in step with the register."""
		if self.renewal_type != "Insurance" or not self.vehicle:
			return

		latest = get_current_renewal(self.vehicle, "Insurance")
		if latest and latest.get("name") == self.name:
			frappe.db.set_value(
				"Vehicle", self.vehicle,
				{
					"insurance_company": self.provider,
					"policy_no": self.certificate_no,
					"start_date": self.effective_from,
					"end_date": self.expiry_date,
				},
				update_modified=False,
			)


# ----------------------------------------------------------------------
def get_primary_notice_days() -> int:
	"""The first reminder threshold. Configurable - never hard-coded.

	Fleet Mgmt.docx is internally inconsistent on this number (14 in section 3
	and the 4.6 heading, 30 in the 4.6 trigger detail, 30/15/7 in section 5), so
	the value is read from GDL Fleet Settings and the escalation ladder with it.
	"""
	days = cint(
		frappe.db.get_single_value("GDL Fleet Settings", "renewal_notice_days")
	)
	return days or 30


@frappe.whitelist()
def get_current_renewal(vehicle: str, renewal_type: str):
	"""The live record of a given type for a vehicle: the one not yet superseded."""
	rows = frappe.get_all(
		"Renewal Register",
		filters={
			"vehicle": vehicle,
			"renewal_type": renewal_type,
			"docstatus": 1,
			"renewal_status": ("!=", "Renewed"),
		},
		fields=["name", "certificate_no", "provider", "effective_from", "expiry_date",
		        "renewal_status", "premium"],
		order_by="expiry_date desc",
		limit=1,
	)
	return rows[0] if rows else None


@frappe.whitelist()
def get_renewal_history(vehicle: str, renewal_type=None):
	"""Every renewal for a vehicle, newest first. Nothing is ever removed."""
	filters = {"vehicle": vehicle, "docstatus": ("<", 2)}
	if renewal_type:
		filters["renewal_type"] = renewal_type

	return frappe.get_all(
		"Renewal Register",
		filters=filters,
		fields=["name", "renewal_type", "certificate_no", "provider", "effective_from",
		        "expiry_date", "premium", "renewal_status", "previous_renewal"],
		order_by="renewal_type asc, expiry_date desc",
	)


@frappe.whitelist()
def make_renewal(source_name: str):
	"""Start the next renewal from the current one, chained to it."""
	frappe.has_permission("Renewal Register", "create", throw=True)

	source = frappe.get_doc("Renewal Register", source_name)
	target = frappe.new_doc("Renewal Register")
	target.renewal_type = source.renewal_type
	target.vehicle = source.vehicle
	target.provider = source.provider
	target.supplier = source.supplier
	target.previous_renewal = source.name
	target.effective_from = source.expiry_date
	return target.as_dict()


def refresh_statuses():
	"""Recompute Valid / Due Soon / Expired. Renewed records are left alone."""
	notice_days = get_primary_notice_days()
	today = getdate(nowdate())
    
	updated = 0
	for row in frappe.get_all(
		"Renewal Register",
		filters={"docstatus": 1, "renewal_status": ("!=", "Renewed")},
		fields=["name", "expiry_date", "renewal_status"],
	):
		days = date_diff(getdate(row.expiry_date), today)
		if days < 0:
			status = "Expired"
		elif days <= notice_days:
			status = "Due Soon"
		else:
			status = "Valid"

		if status != row.renewal_status:
			frappe.db.set_value(
				"Renewal Register", row.name,
				{"renewal_status": status, "days_to_expiry": days},
				update_modified=False,
			)
			updated += 1
	return updated
