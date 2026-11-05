# Copyright (c) 2026, GDL and contributors
"""
Fleet Part Issue - spare parts and tyres issued to a vehicle.

Final document, GAP item 4: "Spare-part issuance/validation forms and tyre
issuance/replacement. Requires custom doctypes/forms integrated with Stock Entry
& Expense Claim." And under Tire Mileage: "Issuance via ERPNext Stock Entry."

The stock itself always moves through a standard ERPNext Stock Entry. This
document never maintains its own quantities, so the fleet module cannot drift
away from the stock ledger.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt


class FleetPartIssue(Document):
	def validate(self):
		self.set_driver_from_assignment()
		self.validate_items()
		self.validate_odometer()
		self.calculate_totals()
		self.set_status()

	def on_submit(self):
		self.create_stock_entry()
		self.create_tyre_records()
		self.db_set("status", "Issued")

	def on_cancel(self):
		self.cancel_stock_entry()
		self.cancel_tyre_records()
		self.db_set("status", "Cancelled")

	# ------------------------------------------------------------------
	def set_driver_from_assignment(self):
		if self.driver or not self.vehicle:
			return
		from gdl_fleet_extension.gdl_fleet.doctype.driver_assignment.driver_assignment import (
			get_active_driver,
		)
		self.driver = get_active_driver(self.vehicle, self.issue_date)

	def validate_items(self):
		if not self.items:
			frappe.throw(_("Add at least one part or tyre to issue."))

		for row in self.items:
			if flt(row.qty) <= 0:
				frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))

			if row.is_tyre:
				if flt(row.qty) != 1:
					frappe.throw(
						_("Row {0}: a tyre is issued one at a time so each one can be "
						  "tracked to the kilometres it achieves. Add a row per tyre.").format(row.idx),
						title=_("One Tyre Per Row"),
					)
				if not row.tyre_position:
					frappe.throw(_("Row {0}: a tyre needs a Position.").format(row.idx))

		self.validate_serial_numbers()

	def validate_serial_numbers(self):
		"""A serialised item must carry a serial number, and it must not already be out."""
		seen = {}
		for row in self.items:
			if not row.serial_no:
				if frappe.db.get_value("Item", row.item_code, "has_serial_no"):
					frappe.throw(
						_("Row {0}: {1} is a serialised item, so a Serial No is required.").format(
							row.idx, frappe.bold(row.item_code)
						)
					)
				continue

			key = row.serial_no.strip().lower()
			if key in seen:
				frappe.throw(
					_("Serial No {0} appears on both row {1} and row {2}.").format(
						frappe.bold(row.serial_no), seen[key], row.idx
					)
				)
			seen[key] = row.idx

			if row.is_tyre:
				fitted = frappe.db.exists(
					"Vehicle Tyre",
					{"serial_no": row.serial_no, "status": "Fitted", "docstatus": ("<", 2)},
				)
				if fitted:
					frappe.throw(
						_("Tyre with Serial No {0} is already recorded as fitted on {1}.").format(
							frappe.bold(row.serial_no), frappe.bold(fitted)
						),
						title=_("Tyre Already Fitted"),
					)

	def validate_odometer(self):
		if cint(self.odometer) < 0:
			frappe.throw(_("Odometer cannot be negative."))

		current = cint(frappe.db.get_value("Vehicle", self.vehicle, "last_odometer"))
		if current and cint(self.odometer) < current:
			frappe.msgprint(
				_("Odometer {0} is below the vehicle's current reading of {1}. "
				  "Check the reading before submitting.").format(self.odometer, current),
				title=_("Odometer Looks Low"),
				indicator="orange",
			)

	def calculate_totals(self):
		total_qty = total_amount = 0.0
		for row in self.items:
			row.amount = flt(row.qty) * flt(row.rate)
			total_qty += flt(row.qty)
			total_amount += flt(row.amount)
		self.total_qty = total_qty
		self.total_amount = total_amount

	def set_status(self):
		if self.docstatus == 2:
			self.status = "Cancelled"
		elif self.docstatus == 1:
			self.status = "Issued"
		else:
			self.status = "Draft"

	# ------------------------------------------------------------------
	# Stock - always through standard ERPNext
	# ------------------------------------------------------------------
	def create_stock_entry(self):
		"""Issue the parts from store with a standard Material Issue."""
		if not self.source_warehouse or self.stock_entry:
			return

		entry = frappe.new_doc("Stock Entry")
		entry.stock_entry_type = "Material Issue"
		entry.purpose = "Material Issue"
		entry.company = frappe.db.get_value("Vehicle", self.vehicle, "company") or frappe.defaults.get_user_default("Company")
		entry.posting_date = self.issue_date
		entry.remarks = _("Fleet Part Issue {0} for vehicle {1}").format(self.name, self.vehicle)

		for row in self.items:
			entry.append("items", {
				"item_code": row.item_code,
				"qty": row.qty,
				"s_warehouse": self.source_warehouse,
				"cost_center": self.cost_center,
				"serial_no": row.serial_no or None,
			})

		entry.flags.ignore_permissions = True
		entry.insert()
		entry.submit()
		self.db_set("stock_entry", entry.name)

	def cancel_stock_entry(self):
		if not self.stock_entry:
			return
		if frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus") == 1:
			doc = frappe.get_doc("Stock Entry", self.stock_entry)
			doc.flags.ignore_permissions = True
			doc.cancel()

	# ------------------------------------------------------------------
	# Tyre lifecycle
	# ------------------------------------------------------------------
	def create_tyre_records(self):
		for row in self.items:
			if not row.is_tyre:
				continue
			if frappe.db.exists("Vehicle Tyre", {"part_issue": self.name, "tyre_position": row.tyre_position,
			                                     "item_code": row.item_code}):
				continue
			tyre = frappe.get_doc({
				"doctype": "Vehicle Tyre",
				"vehicle": self.vehicle,
				"item_code": row.item_code,
				"serial_no": row.serial_no,
				"tyre_position": row.tyre_position,
				"status": "Fitted",
				"fitted_date": self.issue_date,
				"fitted_odometer": self.odometer,
				"part_issue": self.name,
				# A tyre is issued one per row, so the row amount IS this tyre's
				# cost. Carrying it onto the tyre is what makes cost per km
				# answerable years later, once the issue has been archived.
				"cost": flt(row.amount),
			})
			tyre.flags.ignore_permissions = True
			tyre.insert()

	def cancel_tyre_records(self):
		for name in frappe.get_all("Vehicle Tyre", filters={"part_issue": self.name}, pluck="name"):
			frappe.delete_doc("Vehicle Tyre", name, ignore_permissions=True, force=True)
