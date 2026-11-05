# Copyright (c) 2026, GDL and contributors
"""
Phase 5 - GDL Vehicle Log, a subclass of the STANDARD hrms Vehicle Log.

This is the one place the approved architecture calls for `override_doctype_class`
rather than a doc_event, because ERPNext's `on_cancel` has to be REPLACED, not
merely added to.

Standard hrms behaviour (unchanged and still inherited):
    validate      - Ending Odometer must not be below the vehicle's current reading
    before_cancel - cleans up draft Expense Claims raised from the log
    make_expense_claim / get_draft_expense_claims - untouched

What this subclass changes:
    on_submit  - recomputes Vehicle.last_odometer from live readings
    on_cancel  - REPLACES the standard arithmetic (see the defect note below)

The defect: hrms subtracts `(odometer - last_odometer)` from the vehicle's CURRENT
reading on cancel. That is only correct when the log being cancelled is the most
recent one. Cancelling an older log silently drags the vehicle's odometer
backwards. Recomputing MAX() over the remaining live readings is correct whatever
order documents are cancelled in.
"""

import frappe
from frappe import _
from frappe.utils import cint
from hrms.hr.doctype.vehicle_log.vehicle_log import VehicleLog

from gdl_fleet_extension.utils.odometer import (
	get_last_odometer,
	recalculate_vehicle_odometer,
)


class GDLVehicleLog(VehicleLog):
	# ------------------------------------------------------------------
	def validate(self):
		self.set_start_odometer()
		# standard hrms validation still runs
		super().validate()
		self.validate_odometer_range()
		self.set_distance()
		self.set_defaults_from_vehicle()
		self.validate_one_record_per_day()
		self.warn_on_abnormal_mileage()

	def set_start_odometer(self):
		"""Default the trip's starting reading to the vehicle's latest valid one."""
		if self.start_odometer:
			return
		if not self.license_plate:
			return

		self.start_odometer = get_last_odometer(
			self.license_plate,
			exclude=("Vehicle Log", self.name or ""),
			include_vehicle_current=True,
		)

	def validate_odometer_range(self):
		start = cint(self.start_odometer)
		end = cint(self.odometer)

		if start < 0:
			frappe.throw(_("Starting Odometer cannot be negative."))

		if end < start:
			frappe.throw(
				_("Ending Odometer ({0}) cannot be less than Starting Odometer ({1}).").format(
					end, start
				),
				title=_("Invalid Odometer Reading"),
			)

	def set_distance(self):
		self.distance_travelled = cint(self.odometer) - cint(self.start_odometer)

	def validate_one_record_per_day(self):
		"""Section 4.3: one primary daily record per vehicle.

		A second reading for the same vehicle and date is refused unless it is
		tied to its own Movement Order, which is how a genuine second authorised
		trip is recorded.
		"""
		if not (self.license_plate and self.date):
			return

		movement_order = self.get("movement_order")
		filters = {
			"license_plate": self.license_plate,
			"date": self.date,
			"docstatus": ("<", 2),
			"name": ("!=", self.name or ""),
		}
		# An unset link is stored as NULL, which never matches "" in SQL.
		filters["movement_order"] = (
			movement_order if movement_order else ("in", ["", None])
		)

		clash = frappe.db.get_value(
			"Vehicle Log", filters, ["name", "movement_order"], as_dict=True
		)
		if clash:
			frappe.throw(
				_(
					"A daily record already exists for {0} on {1} ({2}). Record the "
					"additional trip against its own Movement Order, or amend the "
					"existing entry."
				).format(
					frappe.bold(self.license_plate),
					frappe.format(self.date, {"fieldtype": "Date"}),
					clash.name,
				),
				title=_("Duplicate Daily Record"),
			)

	def warn_on_abnormal_mileage(self):
		"""Section 4.3: warn on abnormal daily mileage. A warning, not a block."""
		threshold = cint(
			frappe.db.get_single_value("GDL Fleet Settings", "abnormal_daily_km")
		)
		if not threshold or cint(self.distance_travelled) <= threshold:
			return

		frappe.msgprint(
			_(
				"Distance of {0} km on {1} is above the abnormal-mileage threshold "
				"of {2} km. Please confirm the readings."
			).format(
				cint(self.distance_travelled),
				frappe.format(self.date, {"fieldtype": "Date"}),
				threshold,
			),
			title=_("Unusually High Daily Mileage"),
			indicator="orange",
		)

	def set_defaults_from_vehicle(self):
		"""Inherit the vehicle's site and cost dimensions when not given."""
		if not self.license_plate:
			return

		vehicle = frappe.db.get_value(
			"Vehicle",
			self.license_plate,
			["site", "department", "cost_center", "project", "driver"],
			as_dict=True,
		)
		if not vehicle:
			return

		for fieldname in ("site", "department", "cost_center", "project"):
			if not self.get(fieldname) and vehicle.get(fieldname):
				self.set(fieldname, vehicle.get(fieldname))

		if not self.driver:
			# Section 4.3: fetched from the active assignment or the movement.
			from gdl_fleet_extension.gdl_fleet.doctype.driver_assignment.driver_assignment import (
				get_active_driver,
			)

			if self.get("movement_order"):
				self.driver = frappe.db.get_value(
					"Movement Order", self.movement_order, "driver"
				)
			if not self.driver:
				self.driver = get_active_driver(self.license_plate, str(self.date))
			if not self.driver and vehicle.get("driver"):
				self.driver = vehicle.driver

	# ------------------------------------------------------------------
	def on_submit(self):
		"""Standard sets last_odometer = this reading; recompute instead.

		Identical result for the normal in-order case, and correct when logs are
		entered out of order or another source already holds a higher reading.
		"""
		recalculate_vehicle_odometer(self.license_plate)

	def on_cancel(self):
		"""REPLACES the standard subtraction. See the module docstring."""
		recalculate_vehicle_odometer(
			self.license_plate, exclude=("Vehicle Log", self.name)
		)
