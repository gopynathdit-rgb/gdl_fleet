# Copyright (c) 2026, GDL and contributors
"""
Fleet Mgmt.docx section 4.7 - Movement Order Request.

References the STANDARD ERPNext Vehicle, Driver, Employee, Location, Department,
Cost Center, Project and Task. No master data is duplicated here.

Approval is handled entirely by the standard ERPNext Workflow
(User -> Validator -> Reviewer -> MTO/CEO -> FAS); this controller carries only
the rules a workflow cannot express.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime, getdate, now_datetime, nowdate

from gdl_fleet_extension.utils.location_officers import sites_for_user

# A request in one of these states occupies the vehicle.
#
# Only "Accepted" can occur. The earlier multi-level chain had Approved,
# Assigned and In Use, and patches/v1_1/map_movement_request_status.py folded
# all three into Accepted - but this constant was left naming the retired ones.
# Since no request could ever hold them, `status in OCCUPYING_STATUSES` matched
# nothing, and both the conflict guard below and get_available_vehicles were
# silently inert: two requests could be accepted for the same vehicle and
# window, and Check Availability offered vehicles that were already committed.
#
# TestOccupyingStatusesAreReal asserts every value here is a status the DocType
# actually allows, so a rename cannot quietly disable these queries again.
OCCUPYING_STATUSES = ("Accepted",)

# A vehicle in one of these states cannot be assigned at all.
UNASSIGNABLE_VEHICLE_STATUSES = ("Under Maintenance", "Unavailable", "Disposed")


class MovementOrderRequest(Document):
	def validate(self):
		self.set_schedule()
		self.validate_schedule()
		self.validate_passenger_count()
		self.validate_passengers()
		self.validate_vehicle_assignment()
		self.validate_no_overlapping_booking()
		self.apply_booking_lead_time()
		self.set_allocation_priority()
		self.set_assignment_audit()
		self.validate_location_approver()
		self.sync_status()

	def before_update_after_submit(self):
		"""A vehicle is assigned AFTER the request is approved.

		frappe does not run validate() when a submitted document is updated, so
		without this an assignment could be made with no availability check at
		all - the booking conflict rule would simply never run.
		"""
		self.validate_vehicle_assignment()
		self.validate_no_overlapping_booking()
		self.set_assignment_audit()
		self.sync_status()

	def on_submit(self):
		self.sync_status()

	def on_cancel(self):
		# Cancellation keeps the document and its version history; it never deletes.
		self.status = "Cancelled"
		self.db_set("status", "Cancelled")

	# ------------------------------------------------------------------
	# Schedule
	# ------------------------------------------------------------------
	def set_schedule(self):
		"""Derive the datetimes every availability and conflict check works from."""
		if not (self.required_date and self.required_from_time and self.required_to_time):
			return

		end_date = self.return_date or self.required_date
		self.from_datetime = get_datetime(f"{self.required_date} {self.required_from_time}")
		self.to_datetime = get_datetime(f"{end_date} {self.required_to_time}")

		if self.to_datetime > self.from_datetime:
			delta = self.to_datetime - self.from_datetime
			self.duration_hours = flt(delta.total_seconds() / 3600.0, 2)
		else:
			self.duration_hours = 0

	def validate_schedule(self):
		if not (self.from_datetime and self.to_datetime):
			return

		if self.return_date and getdate(self.return_date) < getdate(self.required_date):
			frappe.throw(_("Return Date cannot be before the Required Date."))

		if get_datetime(self.to_datetime) <= get_datetime(self.from_datetime):
			frappe.throw(
				_("Required To Time must be after Required From Time."),
				title=_("Invalid Schedule"),
			)

		# Only guard new drafts. An approved booking must stay editable afterwards,
		# and a completed trip is necessarily in the past.
		if self.is_new() and getdate(self.required_date) < getdate(nowdate()):
			frappe.throw(
				_("Required Date {0} is in the past.").format(
					frappe.bold(frappe.format(self.required_date, {"fieldtype": "Date"}))
				),
				title=_("Invalid Schedule"),
			)

	# ------------------------------------------------------------------
	# OFMS - online booking rules (final document, GAP item 1)
	# ------------------------------------------------------------------
	def apply_booking_lead_time(self):
		"""How much notice the requester gave, and whether that is enough.

		The lead time, the action taken when it is not met, and whether an
		emergency may bypass it are all configuration in GDL Fleet Settings.
		"""
		if not self.from_datetime:
			return

		# A new document has no creation stamp yet, so "now" is the moment it is
		# being raised.
		raised = get_datetime(self.creation) if self.creation else now_datetime()
		hours = (get_datetime(self.from_datetime) - raised).total_seconds() / 3600.0
		self.lead_time_hours = flt(hours, 2)

		required = cint(get_fleet_setting("booking_lead_time_hours", 24))
		if required <= 0 or hours >= required:
			return

		if self.priority == "Emergency" and cint(
			get_fleet_setting("emergency_bypasses_lead_time", 1)
		):
			return

		action = get_fleet_setting("booking_lead_time_action", "Require Reason")
		message = _(
			"This request gives {0} hours notice, less than the {1} hours required. "
		).format(flt(hours, 1), required)

		if action == "Block":
			frappe.throw(
				message + _("Raise it earlier, or mark it Emergency if it genuinely is one."),
				title=_("Insufficient Notice"),
			)
		elif action == "Require Reason":
			if not self.lead_time_waiver_reason:
				frappe.throw(
					message + _("Enter a Short-Notice Reason so the approver can judge it."),
					title=_("Short-Notice Reason Required"),
				)
		else:
			frappe.msgprint(message, title=_("Short Notice"), indicator="orange")

	def set_allocation_priority(self):
		"""Order in which competing requests should be served.

		Lower is served first. Priority is the first consideration; the notice
		given breaks ties, so of two equally urgent requests the one booked
		further ahead is served first.
		"""
		rank = {"Emergency": 100, "Critical Business": 200, "Routine": 300}
		base = rank.get(self.priority, 300)

		hours = flt(self.lead_time_hours)
		if hours >= 168:
			tie = 0
		elif hours >= 72:
			tie = 10
		elif hours >= 24:
			tie = 20
		else:
			tie = 30

		self.allocation_priority = base + tie

	def validate_passenger_count(self):
		if cint(self.passenger_count) < 0:
			frappe.throw(_("Passenger Count cannot be negative."))

		# Named passengers are optional - a requester often books before knowing
		# who travels. Once names ARE given they are the better figure, so they
		# set the count rather than being checked against it. Only a count that
		# is smaller than the list is wrong, and that is corrected silently
		# rather than blocking a booking over a number nobody typed on purpose.
		named = len(self.passengers or [])
		if named and cint(self.passenger_count) < named:
			self.passenger_count = named

	def validate_passengers(self):
		"""A passenger row is worth nothing without a name on it."""
		for row in self.passengers or []:
			if not (row.passenger_name or "").strip():
				frappe.throw(
					_("Row {0} in Passengers / Officials has no name. "
					  "Remove the row or name the passenger.").format(row.idx),
					title=_("Passenger Needs a Name"),
				)

	def validate_location_approver(self):
		"""Only this location's MTO - or the head office MTO - may accept.

		Client, 3 Nov 2026: a manager is named per location, with the final MTO
		at head office. The workflow already checks the ROLE; this checks that
		the person holding it is the one named for this location.
		"""
		if self.workflow_state not in ("Accepted", "Rejected"):
			return
		if self.get_doc_before_save() and \
		   self.get_doc_before_save().workflow_state == self.workflow_state:
			return

		from gdl_fleet_extension.utils.location_officers import validate_approver

		validate_approver(
			self.location_for_approval(),
			doctype=_("This vehicle request"),
		)

	def location_for_approval(self):
		"""The location whose MTO owns this request.

		The vehicle's own site decides it once a vehicle is allocated, because
		that is the fleet the request draws on. Before allocation it falls back
		to the site the request was raised at.
		"""
		if self.vehicle:
			site = frappe.db.get_value("Vehicle", self.vehicle, "site")
			if site:
				return site
		return self.site

	# ------------------------------------------------------------------
	# Vehicle assignment
	# ------------------------------------------------------------------
	def validate_vehicle_assignment(self):
		if not self.vehicle:
			return

		vehicle = frappe.db.get_value(
			"Vehicle",
			self.vehicle,
			["vehicle_type", "vehicle_status", "gdl_vehicle_id"],
			as_dict=True,
		)
		if not vehicle:
			frappe.throw(_("Vehicle {0} does not exist.").format(self.vehicle))

		if vehicle.vehicle_status in UNASSIGNABLE_VEHICLE_STATUSES:
			frappe.throw(
				_("Vehicle {0} cannot be assigned because its status is {1}.").format(
					frappe.bold(self.vehicle), frappe.bold(vehicle.vehicle_status)
				),
				title=_("Vehicle Unavailable"),
			)

		if self.vehicle_type and vehicle.vehicle_type and vehicle.vehicle_type != self.vehicle_type:
			frappe.throw(
				_("Vehicle {0} is of type {1}, but {2} was requested.").format(
					frappe.bold(self.vehicle),
					frappe.bold(vehicle.vehicle_type),
					frappe.bold(self.vehicle_type),
				),
				title=_("Vehicle Type Mismatch"),
			)

	def validate_no_overlapping_booking(self):
		"""Rule 5 and 9 - one vehicle, one booking, for any overlapping period.

		The vehicle row is locked first so that two approvals running at the same
		time cannot both pass this check.
		"""
		if not (self.vehicle and self.from_datetime and self.to_datetime):
			return

		if self.docstatus == 2 or self.status in ("Cancelled", "Rejected", "Completed"):
			return

		frappe.db.get_value("Vehicle", self.vehicle, "name", for_update=True)

		conflict = frappe.db.sql(
			"""
			select name, status, from_datetime, to_datetime
			from `tabMovement Order Request`
			where vehicle = %(vehicle)s
			  and name != %(name)s
			  and docstatus < 2
			  and status in %(statuses)s
			  and from_datetime < %(to_datetime)s
			  and to_datetime > %(from_datetime)s
			limit 1
			""",
			{
				"vehicle": self.vehicle,
				"name": self.name or "",
				"statuses": OCCUPYING_STATUSES,
				"from_datetime": self.from_datetime,
				"to_datetime": self.to_datetime,
			},
			as_dict=True,
		)

		if conflict:
			row = conflict[0]
			frappe.throw(
				_("Vehicle {0} is already booked by {1} ({2}) from {3} to {4}.").format(
					frappe.bold(self.vehicle),
					frappe.bold(row.name),
					row.status,
					frappe.format(row.from_datetime, {"fieldtype": "Datetime"}),
					frappe.format(row.to_datetime, {"fieldtype": "Datetime"}),
				),
				title=_("Booking Conflict"),
			)

	def set_assignment_audit(self):
		if not self.vehicle:
			return

		previous = self.get_doc_before_save()
		if previous and previous.vehicle == self.vehicle and self.assigned_by:
			return

		self.assigned_by = frappe.session.user
		self.assigned_on = now_datetime()

	# ------------------------------------------------------------------
	# Status
	# ------------------------------------------------------------------
	def sync_status(self):
		"""`status` mirrors the workflow state; it is never typed by hand.

		The workflow fixture also sets it through update_field, so this is a
		fallback for sites where no workflow is active yet.
		"""
		if self.docstatus == 2:
			self.status = "Cancelled"
		elif self.workflow_state:
			self.status = self.workflow_state
		elif not self.status:
			self.status = "Draft"


# ----------------------------------------------------------------------
# Availability API (rule 6) - used by the Check Availability button
# ----------------------------------------------------------------------
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def assignable_vehicle_query(doctype, txt, searchfield, start, page_len, filters):
	"""The Assigned Vehicle dropdown.

	Until now the dropdown filtered on vehicle_status alone, so it cheerfully
	offered a vehicle already booked for the requested window and the clash was
	only found when the save was refused. Check Availability knew better; the
	field it sits next to did not.

	This runs the SAME availability rules as that button, and scopes the list to
	the user's own location, so what is offered is what can actually be taken.
	"""
	window = (filters or {}).get("from_datetime"), (filters or {}).get("to_datetime")
	rows = (
		get_available_vehicles(window[0], window[1],
		                       vehicle_type=(filters or {}).get("vehicle_type"),
		                       exclude=(filters or {}).get("exclude"))
		if all(window)
		# Before the schedule is filled in there is no window to test against.
		# Fall back to every assignable vehicle at the user's own sites rather
		# than an empty dropdown with no explanation.
		else assignable_vehicles((filters or {}).get("vehicle_type"))
	)

	if txt:
		needle = txt.lower()
		rows = [r for r in rows
		        if needle in (r.get("name") or "").lower()
		        or needle in (r.get("gdl_vehicle_id") or "").lower()]

	page_len = cint(page_len) or 20
	start = cint(start)
	return [
		[r.get("name"), r.get("gdl_vehicle_id"), r.get("site")]
		for r in rows[start:start + page_len]
	]


def assignable_vehicles(vehicle_type=None) -> list[dict]:
	"""Every vehicle this user could be assigned, ignoring the clock."""
	filters = {"vehicle_status": ("not in", UNASSIGNABLE_VEHICLE_STATUSES)}
	if vehicle_type:
		filters["vehicle_type"] = vehicle_type

	allowed = sites_for_user()
	if allowed is not None:
		filters["site"] = ("in", allowed)

	return frappe.get_all(
		"Vehicle", filters=filters,
		fields=["name", "gdl_vehicle_id", "vehicle_type", "vehicle_status",
		        "make", "model", "site"],
		order_by="gdl_vehicle_id asc",
	)


@frappe.whitelist()
def get_available_vehicles(from_datetime, to_datetime, vehicle_type=None, exclude=None) -> list[dict]:
	"""Standard Vehicles that are free for the whole requested period.

	The datetimes arrive as strings from the desk and as datetime objects from
	server-side callers, so both are normalised here.
	"""
	frappe.has_permission("Movement Order Request", "read", throw=True)

	if not (from_datetime and to_datetime):
		frappe.throw(_("Both a start and an end time are required."))

	from_datetime = get_datetime(from_datetime)
	to_datetime = get_datetime(to_datetime)

	if to_datetime <= from_datetime:
		frappe.throw(_("The end time must be after the start time."))

	filters = {"vehicle_status": ("not in", UNASSIGNABLE_VEHICLE_STATUSES)}
	if vehicle_type:
		filters["vehicle_type"] = vehicle_type

	# A location's people are offered that location's fleet. The head office
	# MTO and the administrator seats are not restricted - see sites_for_user.
	allowed = sites_for_user()
	if allowed is not None:
		filters["site"] = ("in", allowed)

	vehicles = frappe.get_all(
		"Vehicle",
		filters=filters,
		fields=["name", "gdl_vehicle_id", "vehicle_type", "vehicle_status", "make", "model", "site"],
		order_by="gdl_vehicle_id asc",
	)
	if not vehicles:
		return []

	booked = frappe.db.sql(
		"""
		select distinct vehicle
		from `tabMovement Order Request`
		where vehicle in %(vehicles)s
		  and name != %(exclude)s
		  and docstatus < 2
		  and status in %(statuses)s
		  and from_datetime < %(to_datetime)s
		  and to_datetime > %(from_datetime)s
		""",
		{
			"vehicles": [v.name for v in vehicles],
			"exclude": exclude or "",
			"statuses": OCCUPYING_STATUSES,
			"from_datetime": from_datetime,
			"to_datetime": to_datetime,
		},
		pluck=True,
	)
	booked = set(booked or [])

	# A vehicle can also be committed by a Movement Order that this helper would
	# otherwise never see: an order created without a request, or one whose
	# window was widened after approval beyond the request it came from. The
	# order is the authority to travel, so it decides availability just as a
	# request does. Without this the list offers a vehicle that the Movement
	# Order conflict guard will then refuse - advice that contradicts the rule.
	from gdl_fleet_extension.gdl_fleet.doctype.movement_order.movement_order import (
		OCCUPYING_STATUSES as ORDER_OCCUPYING_STATUSES,
	)

	on_order = frappe.db.sql(
		"""
		select distinct vehicle
		from `tabMovement Order`
		where vehicle in %(vehicles)s
		  and docstatus < 2
		  and status in %(statuses)s
		  and departure_datetime < %(to_datetime)s
		  and ifnull(expected_return, departure_datetime) > %(from_datetime)s
		""",
		{
			"vehicles": [v.name for v in vehicles],
			"statuses": ORDER_OCCUPYING_STATUSES,
			"from_datetime": from_datetime,
			"to_datetime": to_datetime,
		},
		pluck=True,
	)
	booked |= set(on_order or [])

	return [v for v in vehicles if v.name not in booked]


def get_fleet_setting(fieldname, default=None):
	"""Every booking rule is configuration, never a literal in code."""
	value = frappe.db.get_single_value("GDL Fleet Settings", fieldname)
	return default if value in (None, "") else value
