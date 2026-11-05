# Copyright (c) 2026, GDL and contributors
"""
Vehicle Tyre - the life of one tyre on one vehicle.

Final document, Tire Mileage: "Tire performance target: 20,000 km +/-20%."

This records where a tyre was fitted and what it achieved. It holds no stock of
its own - the quantity moves through a standard Stock Entry raised by the
Fleet Part Issue, and serialised tyres carry the standard ERPNext serial number.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from gdl_fleet_extension.utils.tyre import DEFAULT_TARGET_KM, classify_tyre, get_tyre_target


class VehicleTyre(Document):
	def validate(self):
		self.validate_odometer()
		self.set_target()
		self.calculate_performance()
		self.set_status()

	def validate_odometer(self):
		if self.fitted_odometer is not None and cint(self.fitted_odometer) < 0:
			frappe.throw(_("Fitted odometer cannot be negative."))

		if self.removed_odometer in (None, ""):
			return

		if cint(self.removed_odometer) < cint(self.fitted_odometer):
			frappe.throw(
				_("Removed odometer ({0}) cannot be less than the fitted odometer ({1}).").format(
					self.removed_odometer, self.fitted_odometer
				),
				title=_("Invalid Odometer"),
			)

	def set_target(self):
		self.target_km = get_tyre_target()

	def calculate_performance(self):
		if self.removed_odometer in (None, "") or not self.removed_date:
			self.km_achieved = None
			self.performance = "In Service"
			return

		self.km_achieved = cint(self.removed_odometer) - cint(self.fitted_odometer)
		self.performance = classify_tyre(self.km_achieved)

	def set_status(self):
		if self.removed_date and self.status == "Fitted":
			self.status = "Removed"


@frappe.whitelist()
def get_fitted_tyres(vehicle):
	"""Tyres currently on a vehicle, for the removal screen."""
	return frappe.get_all(
		"Vehicle Tyre",
		filters={"vehicle": vehicle, "status": "Fitted"},
		fields=["name", "item_code", "serial_no", "tyre_position", "fitted_date", "fitted_odometer"],
		order_by="tyre_position asc",
	)
