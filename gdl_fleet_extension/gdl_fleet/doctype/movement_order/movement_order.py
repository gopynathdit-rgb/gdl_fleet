# Copyright (c) 2026, GDL and contributors
"""
Fleet Mgmt.docx sections 4.8 and 4.9 - Movement Order.

Created from an accepted Movement Order Request. The vehicle must be available,
the driver comes from the active Driver Assignment with an authorised override,
and the order is not valid for dispatch until approved through the workflow.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_datetime, now_datetime

# A Movement Order in one of these states occupies the vehicle.
OCCUPYING_STATUSES = ("Approved", "Dispatched")

# Fleet Mgmt.docx 4.1: the vehicle must be Active/Available to be dispatched.
UNAVAILABLE_VEHICLE_STATUSES = ("Under Maintenance", "Unavailable", "Disposed")


class MovementOrder(Document):
	def validate(self):
		self.validate_request_on_save()
		self.validate_schedule()
		self.set_driver_from_assignment()
		self.validate_vehicle_available()
		self.validate_no_overlap()
		self.validate_location_approver()
		self.sync_status()

	def before_update_after_submit(self):
		"""Vehicle and driver may be changed after approval, so re-check then too."""
		self.validate_schedule()
		self.validate_vehicle_available()
		self.validate_no_overlap()
		self.sync_status()

	def on_cancel(self):
		self.db_set("status", "Cancelled")

	# ------------------------------------------------------------------
	def validate_location_approver(self):
		"""Only this vehicle's location MTO - or the head office MTO - approves.

		Client, 3 Nov 2026: a manager per location, final MTO at head office.
		The approving states differ between the simple and the full chain, so
		this keys off a move INTO any approving state rather than naming one.
		"""
		approving = ("Approved", "Rejected", "Pending FAS", "Pending MTO/CEO")
		if self.workflow_state not in approving:
			return

		before = self.get_doc_before_save()
		if before and before.workflow_state == self.workflow_state:
			return

		from gdl_fleet_extension.utils.location_officers import validate_approver

		site = self.site
		if self.vehicle:
			site = frappe.db.get_value("Vehicle", self.vehicle, "site") or site

		validate_approver(site, doctype=_("This movement order"))

	def validate_schedule(self):
		if not (self.departure_datetime and self.expected_return):
			return
		if get_datetime(self.expected_return) <= get_datetime(self.departure_datetime):
			frappe.throw(
				_("Expected Return must be after the Departure Date & Time."),
				title=_("Invalid Schedule"),
			)

	def validate_request_on_save(self):
		"""The linked request must be usable, and its details must be present.

		The form fetches these when the request is chosen, but a record created
		over the API or by an import never runs that, so the same mapping is
		applied here. Only blank fields are filled - an authorised change made
		on the order is not undone.
		"""
		if not self.movement_order_request:
			return

		validate_request_is_usable(self.movement_order_request, for_order=self.name)

		if self.docstatus != 0:
			return

		for field, value in get_request_details(self.movement_order_request).items():
			if not self.meta.get_field(field) or not value:
				continue
			if not self.get(field):
				self.set(field, value)

	def set_driver_from_assignment(self):
		"""Section 4.8: fetched from the active assignment, or selected."""
		if self.driver or not (self.vehicle and self.departure_datetime):
			self.record_assignment_used()
			return

		from gdl_fleet_extension.gdl_fleet.doctype.driver_assignment.driver_assignment import (
			get_active_driver,
		)

		on_date = get_datetime(self.departure_datetime).date()
		self.driver = get_active_driver(self.vehicle, str(on_date))
		self.record_assignment_used()

	def record_assignment_used(self):
		"""Note which assignment justified this driver, for the audit trail."""
		if not (self.vehicle and self.driver and self.departure_datetime):
			return

		on_date = get_datetime(self.departure_datetime).date()
		self.driver_assignment = frappe.db.get_value(
			"Driver Assignment",
			{
				"vehicle": self.vehicle,
				"driver": self.driver,
				"docstatus": 1,
				"status": ("!=", "Cancelled"),
				"from_date": ("<=", str(on_date)),
			},
			"name",
			order_by="from_date desc",
		)

	def validate_vehicle_available(self):
		if not self.vehicle:
			return

		status = frappe.db.get_value("Vehicle", self.vehicle, "vehicle_status")
		if status in UNAVAILABLE_VEHICLE_STATUSES:
			frappe.throw(
				_("Vehicle {0} is {1} and cannot be dispatched.").format(
					frappe.bold(self.vehicle), frappe.bold(status)
				),
				title=_("Vehicle Not Available"),
			)

	def validate_no_overlap(self):
		"""One vehicle cannot be on two movement orders at the same time."""
		if not (self.vehicle and self.departure_datetime and self.expected_return):
			return
		if self.docstatus == 2 or self.status in ("Cancelled", "Completed"):
			return

		frappe.db.get_value("Vehicle", self.vehicle, "name", for_update=True)

		clash = frappe.db.sql(
			"""
			select name, status, departure_datetime, expected_return
			from `tabMovement Order`
			where vehicle = %(vehicle)s
			  and name != %(name)s
			  and docstatus < 2
			  and status in %(statuses)s
			  and departure_datetime < %(expected_return)s
			  and coalesce(expected_return, departure_datetime) > %(departure_datetime)s
			limit 1
			""",
			{
				"vehicle": self.vehicle,
				"name": self.name or "",
				"statuses": OCCUPYING_STATUSES,
				"departure_datetime": self.departure_datetime,
				"expected_return": self.expected_return,
			},
			as_dict=True,
		)
		if clash:
			row = clash[0]
			frappe.throw(
				_("Vehicle {0} is already on Movement Order {1} ({2}) from {3} to {4}.").format(
					frappe.bold(self.vehicle), frappe.bold(row.name), row.status,
					frappe.format(row.departure_datetime, {"fieldtype": "Datetime"}),
					frappe.format(row.expected_return, {"fieldtype": "Datetime"}),
				),
				title=_("Vehicle Already Committed"),
			)

	def sync_status(self):
		if self.docstatus == 2:
			self.status = "Cancelled"
		elif self.workflow_state:
			self.status = self.workflow_state
		elif not self.status:
			self.status = "Draft"


# ----------------------------------------------------------------------
@frappe.whitelist()
def make_movement_order(source_name: str):
	"""Raise a Movement Order from an ACCEPTED Movement Order Request."""
	frappe.has_permission("Movement Order", "create", throw=True)
	validate_request_is_usable(source_name)

	order = frappe.new_doc("Movement Order")
	order.movement_order_request = source_name

	for field, value in get_request_details(source_name).items():
		docfield = order.meta.get_field(field)
		if not docfield:
			continue
		if docfield.fieldtype == "Table":
			order.set(field, [])
			for row in value or []:
				order.append(field, row)
		else:
			order.set(field, value)

	return order.as_dict()


@frappe.whitelist()
def get_movement_register(from_date=None, to_date=None, vehicle=None, driver=None,
                          department=None, status=None):
	"""Approved movements by vehicle, driver, department, destination and period."""
	frappe.has_permission("Movement Order", "read", throw=True)

	filters = {"docstatus": ("<", 2)}
	if vehicle:
		filters["vehicle"] = vehicle
	if driver:
		filters["driver"] = driver
	if department:
		filters["department"] = department
	if status:
		filters["status"] = status
	if from_date and to_date:
		filters["departure_datetime"] = ("between", [from_date, to_date])

	return frappe.get_all(
		"Movement Order",
		filters=filters,
		fields=("name", "movement_order_request", "vehicle", "driver", "department",
		        "requested_by", "departure_datetime", "expected_return", "purpose",
		        "from_location", "destination", "passenger_count", "status"),
		order_by="departure_datetime desc",
	)


# ---------------------------------------------------------------------------
# Movement Order Request -> Movement Order
#
# One mapping, used by both the "Create Movement Order" action and the form's
# own fetch when the request is chosen on an existing order. Two copies would
# drift apart.
#
# Allocation fields - vehicle and driver - are deliberately NOT in here. They
# are handled separately so an authorised change made on the order is not
# silently undone by re-selecting the request.
# ---------------------------------------------------------------------------
REQUEST_FIELD_MAP = {
	# The allocation the MTO made when they accepted the request. These two
	# belong in the map, not bolted on afterwards: an order can be started
	# EITHER from the request's "Create Movement Order" button OR by picking
	# the request on a blank order, and both paths read this map. With the
	# vehicle and driver set only in make_movement_order, the second path left
	# the two mandatory fields empty and the user had to retype the allocation
	# the manager had already made.
	"vehicle": "vehicle",
	"driver": "driver",
	"department": "department",
	"requested_by": "employee",
	"site": "site",
	"purpose": "purpose",
	"destination": "destination",
	"passenger_count": "passenger_count",
	"vehicle_type": "vehicle_type",
	"departure_datetime": "from_datetime",
	"expected_return": "to_datetime",
}

USABLE_REQUEST_STATUSES = ("Accepted",)


def get_request_details(request_name: str) -> dict:
	"""The fields a Movement Order takes from its request."""
	request = frappe.get_doc("Movement Order Request", request_name)
	values = {
		target: request.get(source)
		for target, source in REQUEST_FIELD_MAP.items()
	}
	# the request keeps the journey start in one of two fields
	values["from_location"] = request.get("from_location") or request.get("pickup_location")
	values["contact_details"] = request.get("contact_details") or _contact_from_requester(request)
	values["passengers"] = passengers_from_request(request)
	return values


def passengers_from_request(request) -> list[dict]:
	"""The named passengers the requester listed, ready to append to an order.

	Returned as plain dicts, not the request's own child rows: those carry the
	request's name and parentfield, and reusing them would re-parent the
	requester's rows onto the order instead of copying them.
	"""
	return [
		{
			"passenger_name": row.passenger_name,
			"employee": row.employee,
			"designation": row.designation,
			"contact_no": row.contact_no,
		}
		for row in (request.get("passengers") or [])
	]


def _contact_from_requester(request) -> str | None:
	"""Best available contact number for the person who asked."""
	if request.get("employee"):
		number = frappe.db.get_value(
			"Employee", request.employee, "cell_number"
		)
		if number:
			return number
	return None


def validate_request_is_usable(request_name: str, for_order: str | None = None):
	"""A Movement Order may only be built on an accepted request."""
	status = frappe.db.get_value("Movement Order Request", request_name, "status")
	docstatus = frappe.db.get_value("Movement Order Request", request_name, "docstatus")

	if docstatus == 2 or status == "Cancelled":
		frappe.throw(
			_("Movement Order Request {0} has been cancelled and cannot be used.")
			.format(frappe.bold(request_name)),
			title=_("Request Cancelled"),
		)

	if status not in USABLE_REQUEST_STATUSES:
		frappe.throw(
			_("Movement Order Request {0} is {1}. Only an Accepted request can be "
			  "turned into a Movement Order.").format(
				frappe.bold(request_name), frappe.bold(status or "Draft")
			),
			title=_("Request Not Accepted"),
		)

	clash = frappe.db.exists(
		"Movement Order",
		{"movement_order_request": request_name, "docstatus": ("<", 2),
		 "name": ("!=", for_order or "")},
	)
	if clash:
		frappe.throw(
			_("Movement Order {0} already exists for this request.").format(frappe.bold(clash)),
			title=_("Already Ordered"),
		)


@frappe.whitelist()
def fetch_request_details(movement_order_request: str) -> dict:
	"""Form-facing fetch when the request is chosen on an open order."""
	frappe.has_permission("Movement Order Request", "read", throw=True)
	validate_request_is_usable(movement_order_request)
	return get_request_details(movement_order_request)

