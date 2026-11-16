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
		self.validate_stock_setup()
		self.calculate_totals()
		self.set_status()

	def before_submit(self):
		# Deliberately before_submit, not on_submit. A throw in on_submit comes
		# AFTER frappe has written docstatus=1: the request rolls back, but the
		# record has already been marked submitted inside the transaction, and a
		# test reading the row straight back sees a submitted document. Raised
		# here, nothing is written at all.
		self.validate_stock_available()

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

	def validate_stock_setup(self):
		"""Say what is wrong HERE, not three screens later out of ERPNext.

		Submitting raises a Material Issue, and ERPNext refuses one for reasons
		that name neither this document nor the setting at fault. GDL met the
		worst of them: "Please enter Difference Account or set default Stock
		Adjustment Account for company ..." - raised on submit, against a
		company setting, from a form that mentions no accounts at all.

		Checked on validate so it is answered while the record is still a
		draft, rather than at the moment somebody presses Submit.
		"""
		if not self.source_warehouse:
			return		# no warehouse, no stock movement, nothing to check

		if frappe.db.get_value("Warehouse", self.source_warehouse, "is_group"):
			frappe.throw(
				_("{0} is a group warehouse, and stock cannot be issued from one. "
				  "Choose the warehouse the parts are actually held in.").format(
					frappe.bold(self.source_warehouse)),
				title=_("Group Warehouse"),
			)

		company = (frappe.db.get_value("Vehicle", self.vehicle, "company")
		           or frappe.defaults.get_user_default("Company"))
		if company and cint(frappe.db.get_value("Company", company, "enable_perpetual_inventory")):
			if not frappe.db.get_value("Company", company, "stock_adjustment_account"):
				frappe.throw(
					_("Company {0} has no <b>Stock Adjustment Account</b>, so ERPNext cannot "
					  "post the issue. Set it on the Company record (Accounting Settings), "
					  "then submit this issue.").format(frappe.bold(company)),
					title=_("Stock Adjustment Account Not Set"),
				)

		self.warn_on_short_stock()

	def warn_on_short_stock(self):
		"""A warning, not a refusal - the parts may arrive before this is submitted."""
		short = []
		for row in self.items:
			if not row.item_code:
				continue
			if not frappe.db.get_value("Item", row.item_code, "is_stock_item"):
				continue
			available = flt(frappe.db.get_value(
				"Bin", {"item_code": row.item_code, "warehouse": self.source_warehouse},
				"actual_qty"))
			if available < flt(row.qty):
				short.append(_("Row {0}: {1} - {2} in stock, {3} being issued.").format(
					row.idx, frappe.bold(row.item_code), available, flt(row.qty)))
		if short:
			frappe.msgprint(
				"<br>".join(short) + "<br><br>" + _(
					"Receive the stock into {0} before submitting, or this issue will be "
					"refused.").format(frappe.bold(self.source_warehouse)),
				title=_("Not Enough Stock"),
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

	def validate_stock_available(self):
		"""Refuse at SUBMIT what was only a warning in the draft.

		ERPNext's own refusals here are honest but unhelpful on this form:
		"Valuation Rate for the Item ... is required to do accounting entries
		for Stock Entry MAT-STE-...". It names a stock entry the user never
		opened, and its first suggestion - enable 'Allow Zero Valuation Rate' -
		would post a Nu. 2,000 tyre out of store at no value at all. That is a
		wrong answer to the right question, and it is the one on offer.

		A part cannot be issued from a store that does not hold it. Say so.
		"""
		if not self.source_warehouse:
			return		# no warehouse, no stock movement

		problems = []
		for row in self.items:
			if not row.item_code:
				continue
			if not frappe.db.get_value("Item", row.item_code, "is_stock_item"):
				continue

			bin_row = frappe.db.get_value(
				"Bin", {"item_code": row.item_code, "warehouse": self.source_warehouse},
				["actual_qty", "valuation_rate"], as_dict=True) or frappe._dict()
			available = flt(bin_row.get("actual_qty"))

			if available < flt(row.qty):
				problems.append(_("Row {0}: {1} - {2} in {3}, {4} being issued.").format(
					row.idx, frappe.bold(row.item_code), available,
					frappe.bold(self.source_warehouse), flt(row.qty)))
				continue

			# In stock, but received at no rate - ERPNext cannot value the issue.
			if not flt(bin_row.get("valuation_rate")) and not flt(
					frappe.db.get_value("Item", row.item_code, "valuation_rate")):
				problems.append(_("Row {0}: {1} is in {2} but has no valuation - it was "
				                  "received without a rate.").format(
					row.idx, frappe.bold(row.item_code), frappe.bold(self.source_warehouse)))

		if problems:
			frappe.throw(
				"<br>".join(problems) + "<br><br>" + _(
					"Receive the stock into {0} first &mdash; a <b>Material Receipt</b> Stock "
					"Entry, with the rate paid for it. The issue can then be submitted and "
					"the cost reaches the vehicle."
				).format(frappe.bold(self.source_warehouse)),
				title=_("Not In Stock"),
			)

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
