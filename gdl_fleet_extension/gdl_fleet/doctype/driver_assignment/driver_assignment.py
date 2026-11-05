# Copyright (c) 2026, GDL and contributors
"""
Fleet Mgmt.docx section 4.2 - date-effective Driver-to-Vehicle Assignment.

The document is explicit that history must be preserved rather than the current
driver being overwritten, which is exactly what a single `driver` field on the
Vehicle cannot do. Each assignment is its own submitted record, so the trail of
who drove what, and when, is permanent.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from gdl_fleet_extension.utils.driver import get_driver_details, validate_driver_employee
from frappe.utils import getdate, nowdate

PRIMARY = "Primary"
OPEN_ENDED = "2999-12-31"


class DriverAssignment(Document):
	def validate(self):
		validate_driver_employee(self)
		self.validate_dates()
		self.sync_driver_details()
		self.validate_no_overlapping_primary()
		self.set_status()

	def on_submit(self):
		self.set_status()
		self.push_current_driver_to_vehicle()

	def on_cancel(self):
		self.db_set("status", "Cancelled")
		self.push_current_driver_to_vehicle()

	# ------------------------------------------------------------------
	def validate_dates(self):
		if not self.to_date:
			return
		if getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(
				_("From Date ({0}) cannot be after To Date ({1}).").format(
					frappe.format(self.from_date, {"fieldtype": "Date"}),
					frappe.format(self.to_date, {"fieldtype": "Date"}),
				),
				title=_("Invalid Period"),
			)

	def sync_driver_details(self):
		"""Keep the driver's details on the record in step with the master.

		The form fetches these through `fetch_from`, but a record created over
		the API or by an import never runs that, so the same thing is done here.

		The licence is refreshed outright because it is purely derived from the
		driver. The employee is only filled when blank: a value that disagrees
		with the driver has already been refused by validate_driver_employee,
		so anything still here was put there deliberately.
		"""
		if not self.driver:
			return

		details = get_driver_details(self.driver)
		self.license_no = details.get("license_number") or None

		if not self.employee:
			self.employee = details.get("employee") or None
		if not self.location:
			self.location = details.get("site") or None

	def validate_no_overlapping_primary(self):
		"""Only one Primary assignment may be active for a vehicle at a time.

		Temporary and Relief assignments are deliberately allowed to overlap a
		Primary one - that is what they are for.
		"""
		if self.assignment_type != PRIMARY:
			return
		if self.status == "Cancelled" or self.docstatus == 2:
			return

		clash = frappe.db.sql(
			"""
			select name, driver, from_date, to_date
			from `tabDriver Assignment`
			where vehicle = %(vehicle)s
			  and name != %(name)s
			  and docstatus < 2
			  and assignment_type = 'Primary'
			  and status != 'Cancelled'
			  and from_date <= %(to_date)s
			  and coalesce(to_date, %(open_ended)s) >= %(from_date)s
			limit 1
			""",
			{
				"vehicle": self.vehicle,
				"name": self.name or "",
				"from_date": self.from_date,
				"to_date": self.to_date or OPEN_ENDED,
				"open_ended": OPEN_ENDED,
			},
			as_dict=True,
		)
		if clash:
			row = clash[0]
			frappe.throw(
				_(
					"Vehicle {0} already has a primary driver ({1}) for an overlapping "
					"period ({2}). Close that assignment first, or record this one as "
					"Temporary or Relief."
				).format(
					frappe.bold(self.vehicle), frappe.bold(row.driver), row.name
				),
				title=_("Overlapping Primary Assignment"),
			)

	def set_status(self):
		if self.docstatus == 2:
			self.status = "Cancelled"
		elif self.to_date and getdate(self.to_date) < getdate(nowdate()):
			self.status = "Completed"
		else:
			self.status = "Active"

	def push_current_driver_to_vehicle(self):
		"""Vehicle.driver becomes a derived convenience field, not the record."""
		if not self.vehicle:
			return
		current = get_active_driver(self.vehicle)
		frappe.db.set_value("Vehicle", self.vehicle, "driver", current, update_modified=False)


# ----------------------------------------------------------------------
@frappe.whitelist()
def get_active_driver(vehicle: str, on_date=None, assignment_type=None):
	"""The driver assigned to a vehicle on a given date.

	A Temporary or Relief assignment covering the date takes precedence over the
	Primary one, since that is the point of raising it.
	"""
	if not vehicle:
		return None

	on_date = on_date or nowdate()
	rows = frappe.db.sql(
		"""
		select driver, assignment_type
		from `tabDriver Assignment`
		where vehicle = %(vehicle)s
		  and docstatus = 1
		  and status != 'Cancelled'
		  and from_date <= %(on_date)s
		  and coalesce(to_date, %(open_ended)s) >= %(on_date)s
		  {type_filter}
		order by field(assignment_type, 'Temporary', 'Relief', 'Primary'), from_date desc
		limit 1
		""".format(
			type_filter="and assignment_type = %(assignment_type)s" if assignment_type else ""
		),
		{
			"vehicle": vehicle,
			"on_date": on_date,
			"open_ended": OPEN_ENDED,
			"assignment_type": assignment_type,
		},
		as_dict=True,
	)
	return rows[0].driver if rows else None


@frappe.whitelist()
def get_assignment_history(vehicle=None, driver=None, from_date=None, to_date=None):
	filters = {"docstatus": ("<", 2)}
	if vehicle:
		filters["vehicle"] = vehicle
	if driver:
		filters["driver"] = driver
	if from_date and to_date:
		filters["from_date"] = ("<=", to_date)

	rows = frappe.get_all(
		"Driver Assignment",
		filters=filters,
		fields=[
			"name", "vehicle", "driver", "employee", "license_no", "assignment_type",
			"from_date", "to_date", "status", "remarks",
		],
		order_by="vehicle asc, from_date desc",
	)
	if from_date and to_date:
		rows = [
			r for r in rows
			if not r.to_date or str(r.to_date) >= str(from_date)
		]
	return rows


def refresh_statuses():
	"""Move assignments whose period has closed to Completed."""
	stale = frappe.get_all(
		"Driver Assignment",
		filters={
			"docstatus": 1,
			"status": "Active",
			"to_date": ("<", nowdate()),
		},
		pluck="name",
	)
	for name in stale:
		frappe.db.set_value("Driver Assignment", name, "status", "Completed",
		                    update_modified=False)
	return len(stale)
