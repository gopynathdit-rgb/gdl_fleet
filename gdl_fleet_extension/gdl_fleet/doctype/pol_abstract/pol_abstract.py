# Copyright (c) 2026, GDL and contributors
"""
POL Abstract - the periodic fuel abstract from the customer's POL.xlsx.

Each POL Entry row records one fuel supply (supply memo, date, fuel type,
litres, rate, odometer, amounts per provider). The abstract totals them, applies
the tank-balance adjustment and reports performance per litre.

POL posts no accounting of its own; fuel expenditure is claimed from the
provider on the strength of the approved abstract.

All arithmetic lives in utils/pol.py so it is testable without a document.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, nowdate

from gdl_fleet_extension.utils.mileage_deviation import classify
from gdl_fleet_extension.utils.pol import compute_abstract, line_amount, quantize, to_decimal

# Statuses in which an abstract still owns the fuel entries it lists. A
# cancelled abstract releases them so they can be abstracted again.
OCCUPYING_DOCSTATUS = (0, 1)


class POLAbstract(Document):
	def validate(self):
		self.set_driver_from_assignment()
		self.validate_period()
		self.validate_entries()
		self.validate_entry_suppliers()
		self.validate_supplier_bill()
		self.validate_odometer()
		self.validate_tank_balances()
		self.calculate()
		self.evaluate_mileage()
		self.set_status()

	def before_submit(self):
		"""docstatus 1 means approved.

		The workflow only reaches doc_status 1 through the Approve transition,
		so whoever takes the document to submitted is the approver. A direct
		programmatic submit lands in the same state rather than an ambiguous one.
		"""
		if not self.submitted_by:
			self.submitted_by = self.owner
		self.approved_by = frappe.session.user
		self.status = "Approved"

	def on_submit(self):
		if cint(get_pol_setting("pol_invoice_on_approval", 0)):
			self.raise_fuel_claims()

	def raise_fuel_claims(self):
		"""Raise the claim for each provider that has an amount."""
		for provider in ("BOD", "STCBL"):
			amount_field, supplier_setting = PROVIDERS[provider]
			if flt(self.get(amount_field)) <= 0:
				continue
			if get_claim_invoice(self.name, get_pol_setting(supplier_setting)):
				continue
			try:
				make_fuel_invoice(self.name, provider)
			except Exception as exc:
				# A configuration gap must not block the approval itself.
				frappe.msgprint(
					_("The {0} fuel claim was not raised: {1}").format(provider, exc),
					title=_("Fuel Claim Not Raised"), indicator="orange",
				)

	def on_cancel(self):
		self.db_set("status", "Cancelled")

	# ------------------------------------------------------------------
	# Defaults
	# ------------------------------------------------------------------
	def set_driver_from_assignment(self):
		"""Reuse the Driver Assignment history rather than re-keying a driver."""
		if self.driver or not self.vehicle:
			return

		from gdl_fleet_extension.gdl_fleet.doctype.driver_assignment.driver_assignment import (
			get_active_driver,
		)

		self.driver = get_active_driver(self.vehicle, self.period_to or self.abstract_date)

	# ------------------------------------------------------------------
	# Validation
	# ------------------------------------------------------------------
	def validate_period(self):
		if self.period_from and self.period_to and getdate(self.period_to) < getdate(self.period_from):
			frappe.throw(
				_("Period To cannot be before Period From."),
				title=_("Invalid Reporting Period"),
			)

	def validate_entries(self):
		if not self.entries:
			frappe.throw(_("A POL Abstract needs at least one fuel supply entry."))

		seen_memos = {}
		enforce_unique = cint(get_pol_setting("pol_enforce_unique_supply_memo", 1))

		for row in self.entries:
			if to_decimal(row.litres) <= 0:
				frappe.throw(
					_("Row {0}: Litres must be greater than zero.").format(row.idx),
					title=_("Invalid Fuel Quantity"),
				)
			if to_decimal(row.rate) < 0:
				frappe.throw(_("Row {0}: Rate cannot be negative.").format(row.idx))
			if to_decimal(row.recoupment_bod) < 0 or to_decimal(row.recoupment_stcbl) < 0:
				frappe.throw(_("Row {0}: Recoupment cannot be negative.").format(row.idx))

			self.set_entry_amount(row)
			self.set_entry_total(row)

			if enforce_unique and row.supply_memo_no:
				key = str(row.supply_memo_no).strip().lower()
				if key in seen_memos:
					frappe.throw(
						_("Supply Memo No. {0} appears on both row {1} and row {2}.").format(
							frappe.bold(row.supply_memo_no), seen_memos[key], row.idx
						),
						title=_("Duplicate Supply Memo"),
					)
				seen_memos[key] = row.idx

		if enforce_unique:
			self.validate_memo_unique_for_vehicle()

	def set_entry_amount(self, row):
		"""One amount per row. Litres x Rate, unless someone typed otherwise.

		Sheet BG-1-A2397 of the workbook carries hand-entered amounts that do
		not equal the raw product (41.81 x 105.55 = 4413.0455, typed 4413.04).
		The approved figure must survive, so a value already present is left
		exactly as it stands and simply flagged.
		"""
		computed = line_amount(row.litres, row.rate, self.currency_precision)

		if row.total_amount in (None, "", 0):
			row.total_amount = float(computed)
			row.amount_overridden = 0
		else:
			row.amount_overridden = 1 if to_decimal(row.total_amount) != computed else 0

	def set_entry_total(self, row):
		"""Route the row's amount to the provider its supplier belongs to.

		GDL used to type Amount (BOD) and Amount (STCBL) side by side, which
		meant saying twice what the supplier already says once - and left room
		for a row credited to both providers or neither. Now the row carries
		one amount and the supplier decides which claim it lands in.

		Both provider columns are kept and still drive the claim, the book
		balance and every POL report. They are derived rather than entered.
		"""
		amount = to_decimal(row.total_amount)
		provider = provider_for_supplier(row.supplier)

		if provider == "BOD":
			row.amount_bod = float(quantize(amount, self.currency_precision))
			row.amount_stcbl = 0.0
		else:
			# STCBL is the default. A supplier that is neither is refused by
			# validate_entry_suppliers, so this only takes effect before the
			# providers are configured at all.
			row.amount_stcbl = float(quantize(amount, self.currency_precision))
			row.amount_bod = 0.0

	def validate_entry_suppliers(self):
		"""Every fuel line must name one of GDL's two providers.

		Only enforced once BOTH are configured. Before that there is nothing to
		check against, and refusing every row would stop the fleet working on
		the day the module goes live rather than the day it is set up.
		"""
		bod = get_pol_setting("pol_bod_supplier")
		stcbl = get_pol_setting("pol_stcbl_supplier")
		if not (bod and stcbl):
			return

		for row in self.entries:
			if row.supplier in (bod, stcbl):
				continue
			frappe.throw(
				_(
					"Row {0}: {1} is not one of GDL's fuel providers. Choose {2} or {3} - "
					"the amount is claimed from whichever provider the supplier names."
				).format(row.idx, frappe.bold(row.supplier or _("(blank)")),
				         frappe.bold(bod), frappe.bold(stcbl)),
				title=_("Not a Fuel Provider"),
			)

	def validate_memo_unique_for_vehicle(self):
		"""A supply memo belongs to one abstract for a vehicle."""
		memos = [r.supply_memo_no for r in self.entries if r.supply_memo_no]
		if not memos:
			return

		clash = frappe.db.sql(
			"""
			select e.supply_memo_no, a.name
			from `tabPOL Entry` e
			inner join `tabPOL Abstract` a on a.name = e.parent
			where e.parenttype = 'POL Abstract'
			  and a.vehicle = %(vehicle)s
			  and a.name != %(name)s
			  and a.docstatus in (0, 1)
			  and e.supply_memo_no in %(memos)s
			limit 1
			""",
			{"vehicle": self.vehicle, "name": self.name or "new", "memos": tuple(memos)},
			as_dict=True,
		)
		if clash:
			frappe.throw(
				_("Supply Memo No. {0} is already on POL Abstract {1} for this vehicle.").format(
					frappe.bold(clash[0].supply_memo_no), frappe.bold(clash[0].name)
				),
				title=_("Duplicate Supply Memo"),
			)

	def validate_supplier_bill(self):
		"""The supplier's bill has to be on the record before anyone approves it.

		Checked as the abstract leaves Draft rather than at submit: the driver
		moves it to Submitted at docstatus 0, so a before_submit rule would let
		an unsupported abstract reach the approver's queue and only stop it at
		the very last step.

		Abstracts approved before this rule existed are untouched; the check
		only runs while the record is being saved.
		"""
		if not cint(get_pol_setting("pol_abstract_requires_attachment", 1)):
			return
		if self.supplier_bill_attachment:
			return
		if self.status in ("Submitted", "Approved") or self.docstatus == 1:
			frappe.throw(
				_("Attach the supplier's fuel bill before sending this abstract for approval."),
				title=_("Supplier Bill Required"),
			)

	def validate_odometer(self):
		if to_decimal(self.closing_km) < to_decimal(self.opening_km):
			label = _("Hours") if self.distance_basis == "Hours" else _("KM")
			frappe.throw(
				_("Closing {0} ({1}) cannot be less than Opening {0} ({2}). Distance can never be negative.").format(
					label, self.closing_km, self.opening_km
				),
				title=_("Invalid Reading"),
			)

	def validate_tank_balances(self):
		if to_decimal(self.previous_tank_balance) < 0:
			frappe.throw(_("Previous Tank Balance cannot be negative."))
		if to_decimal(self.present_tank_balance) < 0:
			frappe.throw(_("Present Tank Balance cannot be negative."))

		consumed = (
			to_decimal(self.total_fuel_supplied_from_entries())
			+ to_decimal(self.previous_tank_balance)
			- to_decimal(self.present_tank_balance)
		)
		if consumed < 0:
			frappe.throw(
				_(
					"Total Fuel Consumed works out to {0} litres. "
					"The present tank balance cannot exceed the fuel supplied plus the previous balance."
				).format(consumed),
				title=_("Negative Consumption"),
			)

	def total_fuel_supplied_from_entries(self):
		return sum(to_decimal(r.litres) for r in self.entries)

	# ------------------------------------------------------------------
	# Calculation
	# ------------------------------------------------------------------
	@property
	def currency_precision(self) -> int:
		return cint(frappe.get_cached_value("System Settings", None, "currency_precision")) or 2

	def set_opening_book_balance(self):
		"""Last period's unspent coupon is this period's opening balance.

		Blueprint, POL Management: the coupon's "to-date amount should be
		maintained". A coupon book is not emptied and reissued each period, so
		what was left over has to arrive here or it is simply lost.

		Read-only and always recomputed: letting a user type an opening balance
		would let the running total drift away from the abstract it came from.
		"""
		carry = get_book_balance_carry_forward(
			self.vehicle, self.period_from, exclude=self.name
		)
		self.opening_book_balance_bod = carry["bod"]
		self.opening_book_balance_stcbl = carry["stcbl"]

	def calculate(self):
		"""Every derived figure, straight from the workbook's formulas."""
		self.set_opening_book_balance()
		result = compute_abstract(
			entries=[r.as_dict() for r in self.entries],
			opening_km=self.opening_km,
			closing_km=self.closing_km,
			previous_tank_balance=self.previous_tank_balance,
			present_tank_balance=self.present_tank_balance,
			recoupment_bod=self.recoupment_bod,
			recoupment_stcbl=self.recoupment_stcbl,
			currency_precision=self.currency_precision,
			# Stored at full accuracy; the precision setting governs display.
			performance_precision=None,
			opening_book_balance_bod=self.opening_book_balance_bod,
			opening_book_balance_stcbl=self.opening_book_balance_stcbl,
		)

		self.total_fuel_supplied = float(result["total_fuel_supplied"])
		self.total_amount_bod = float(result["total_amount_bod"])
		self.total_amount_stcbl = float(result["total_amount_stcbl"])
		self.total_km = float(result["total_km"])
		self.total_fuel_consumed = float(result["total_fuel_consumed"])
		self.fuel_book_balance_bod = float(result["fuel_book_balance_bod"])
		self.fuel_book_balance_stcbl = float(result["fuel_book_balance_stcbl"])

		performance = result["performance_per_litre"]
		self.performance_per_litre = float(performance) if performance is not None else None

	def evaluate_mileage(self):
		"""Compare actual km/l against the vehicle's minimum.

		Final document, Optimal Fleet Utilization: a deviation beyond tolerance
		"requires HR approval workflow". The abstract already goes to HR/MTO for
		approval, so rather than adding a second workflow this records the
		deviation and holds the abstract until a reason is given - which is what
		HR reviews.
		"""
		if not self.min_mileage and self.vehicle:
			self.min_mileage = frappe.db.get_value("Vehicle", self.vehicle, "min_mileage")

		status, deviation = classify(self.performance_per_litre or 0, self.min_mileage)
		if self.performance_per_litre is None:
			status, deviation = "Not Applicable", None

		self.mileage_status = status
		self.mileage_deviation = float(deviation) if deviation is not None else None

		if status not in ("Below Tolerance", "Above Tolerance"):
			return
		if not cint(get_pol_setting("mileage_requires_hr_approval", 1)):
			return
		if self.deviation_reason:
			return

		direction = _("below") if status == "Below Tolerance" else _("above")
		frappe.throw(
			_(
				"Mileage of {0} KM/L is {1}% {2} the minimum of {3} KM/L for this "
				"vehicle, which is outside the {4}% tolerance. Enter a Deviation "
				"Reason for HR to review."
			).format(
				frappe.bold(f"{self.performance_per_litre:.2f}"),
				frappe.bold(f"{abs(float(deviation)):.1f}"),
				direction,
				frappe.bold(f"{self.min_mileage:.2f}"),
				get_pol_setting("mileage_deviation_tolerance", 10),
			),
			title=_("Mileage Deviation Requires a Reason"),
		)

	def set_status(self):
		"""Status follows docstatus, except while the workflow owns the draft.

		At docstatus 0 the workflow moves the record between Draft, Submitted
		and Rejected, so those are left alone; anything else is corrected back
		to Draft.
		"""
		if self.docstatus == 2:
			self.status = "Cancelled"
		elif self.docstatus == 1:
			self.status = "Approved"
		elif self.status not in ("Draft", "Submitted", "Rejected"):
			self.status = "Draft"

		# "Submitted By" is the driver who sent the abstract up for approval.
		if self.status != "Draft" and not self.submitted_by:
			self.submitted_by = frappe.session.user


# ---------------------------------------------------------------------------
# Settings access - every threshold is configuration, never a literal in code
# ---------------------------------------------------------------------------
def get_pol_setting(fieldname, default=None):
	value = frappe.db.get_single_value("GDL Fleet Settings", fieldname)
	return default if value in (None, "") else value


# ---------------------------------------------------------------------------
# Carry-forward and fuel-entry pull
# ---------------------------------------------------------------------------
def provider_for_supplier(supplier):
	"""Which of GDL's two fuel providers this supplier is, or None.

	The supplier IS the routing key - it is the one thing a driver already
	knows and writes on the memo.
	"""
	if not supplier:
		return None
	if supplier == get_pol_setting("pol_bod_supplier"):
		return "BOD"
	if supplier == get_pol_setting("pol_stcbl_supplier"):
		return "STCBL"
	return None


@frappe.whitelist()
def get_fuel_suppliers():
	"""The two providers, for the Supplier link filter on the entry grid."""
	return [s for s in (get_pol_setting("pol_bod_supplier"),
	                    get_pol_setting("pol_stcbl_supplier")) if s]


@frappe.whitelist()
def bill_attachment_required():
	"""Whether the supplier's bill must be attached before the abstract goes up.

	A whitelisted flag, not a reading of GDL Fleet Settings from the browser.
	frappe.db.get_single_value() in client code goes through frappe.client.get_value,
	which checks read permission on the WHOLE settings record - fuel expense
	accounts, approver roles, provider configuration - so a driver opening a POL
	abstract was met with "No permission for GDL Fleet Settings" before they
	could read their own form.

	Nothing here is confidential: it answers one yes-or-no question about the
	form the caller already has open.
	"""
	return bool(get_pol_setting("pol_abstract_requires_attachment"))


def get_book_balance_carry_forward(vehicle, period_from=None, exclude=None) -> dict:
	"""The closing coupon balance of this vehicle's previous abstract.

	Zero when the setting is off, when there is no previous abstract, or when
	the vehicle is not set yet. Zero is the honest answer in all three cases -
	it is what a brand new coupon book starts at.

	Only an APPROVED abstract carries forward. A draft or a rejected one is not
	an agreed balance, and treating it as one would let an unapproved claim
	silently move the next period's opening figure.
	"""
	empty = {"bod": 0.0, "stcbl": 0.0, "source": None}
	if not vehicle:
		return empty
	if not cint(get_pol_setting("pol_carry_forward_book_balance", 1)):
		return empty

	filters = {"vehicle": vehicle, "docstatus": 1}
	if period_from:
		filters["period_to"] = ("<", period_from)
	if exclude:
		filters["name"] = ("!=", exclude)

	previous = frappe.get_all(
		"POL Abstract",
		filters=filters,
		fields=["name", "fuel_book_balance_bod", "fuel_book_balance_stcbl"],
		order_by="period_to desc, creation desc",
		limit=1,
	)
	if not previous:
		return empty

	row = previous[0]
	return {
		"bod": flt(row.fuel_book_balance_bod),
		"stcbl": flt(row.fuel_book_balance_stcbl),
		"source": row.name,
	}


@frappe.whitelist()
def get_vehicle_book_balance(vehicle) -> dict:
	"""The to-date coupon balance for a vehicle, for the form and for reports."""
	frappe.has_permission("POL Abstract", "read", throw=True)
	return get_book_balance_carry_forward(vehicle)


def get_previous_abstract(vehicle, before_date=None, exclude=None):
	"""The most recent submitted abstract for a vehicle."""
	filters = {"vehicle": vehicle, "docstatus": 1}
	if before_date:
		filters["period_to"] = ("<=", before_date)
	if exclude:
		filters["name"] = ("!=", exclude)

	rows = frappe.get_all(
		"POL Abstract",
		filters=filters,
		fields=["name", "closing_km", "present_tank_balance", "period_to"],
		order_by="period_to desc, creation desc",
		limit=1,
	)
	return rows[0] if rows else None


@frappe.whitelist()
def get_carry_forward(vehicle, period_from=None, exclude=None):
	"""Opening KM and previous tank balance carried from the last abstract.

	Both are returned as suggestions. The form writes them into editable
	fields, so an authorised user can always override - GDL's own workbook
	notes mark the tank balance as "manual (Assump)".
	"""
	previous = get_previous_abstract(vehicle, period_from, exclude)
	carry_km = cint(get_pol_setting("pol_carry_forward_opening_km", 1))
	carry_tank = cint(get_pol_setting("pol_carry_forward_tank_balance", 1))

	result = {"opening_km": None, "previous_tank_balance": None, "source": None}
	if not previous:
		# No prior abstract: fall back to the vehicle's own odometer so the
		# first POL period does not start from zero.
		if carry_km:
			result["opening_km"] = frappe.db.get_value("Vehicle", vehicle, "last_odometer")
			result["source"] = "Vehicle"
		return result

	result["source"] = previous.name
	if carry_km:
		result["opening_km"] = previous.closing_km
	if carry_tank:
		result["previous_tank_balance"] = previous.present_tank_balance
	return result


# ---------------------------------------------------------------------------
# Fuel claim -> Purchase Invoice, per provider
#
# Final document, POL Management: "There is a provision to maintain the fuel
# coupon from two different fuel provider - BOD and STCBL ... Based on this, the
# fuel invoice and payment are made based on the detailed amount claimed from
# each provider."
#
# The abstract itself still posts nothing. It is the approval document; the
# Purchase Invoice is what reaches the ledger, which keeps a litre of fuel from
# being accounted for twice.
# ---------------------------------------------------------------------------
# The claim is found by looking at the invoices, not by storing a link on the
# abstract. A Link field here would make the invoice impossible to cancel -
# frappe refuses to cancel a document another record points at - and Accounts
# must be able to reverse a claim raised in error.
PROVIDERS = {
	"BOD": ("total_amount_bod", "pol_bod_supplier"),
	"STCBL": ("total_amount_stcbl", "pol_stcbl_supplier"),
}


def get_claim_invoice(pol_abstract, supplier):
	"""The live (not cancelled) claim invoice for this abstract and supplier."""
	if not supplier:
		return None
	rows = frappe.get_all(
		"Purchase Invoice",
		filters={"pol_abstract": pol_abstract, "supplier": supplier, "docstatus": ("<", 2)},
		pluck="name",
		limit=1,
	)
	return rows[0] if rows else None


def _provider_config(provider):
	if provider not in PROVIDERS:
		frappe.throw(_("Unknown fuel provider {0}. Expected BOD or STCBL.").format(provider))
	return PROVIDERS[provider]


def get_fuel_expense_account(company):
	"""The account this company's fuel is charged to.

	The claim is raised in the company that owns the VEHICLE, so the account has
	to be that company's too. GDL runs more than one company, and an account
	belongs to exactly one of them, so a single setting cannot serve them all -
	hence the per-company table, with the old single field kept as the fallback
	for a company that has no row.

	Everything is checked here rather than left to ERPNext, whose own refusal
	("The Expense Account ... does not belong to the company ...") arrives on
	row 1 of an invoice the user never asked to see and says nothing about where
	the account came from.
	"""
	from gdl_fleet_extension.gdl_fleet.doctype.gdl_fleet_settings.gdl_fleet_settings import (
		check_expense_account,
	)

	if not company:
		frappe.throw(
			_("This abstract's vehicle has no company, so there is nothing to charge the fuel to."),
			title=_("Company Not Set"),
		)

	settings = frappe.get_cached_doc("GDL Fleet Settings")
	for row in settings.get("pol_fuel_accounts") or []:
		if row.company == company:
			check_expense_account(row.expense_account, company)
			return row.expense_account

	fallback = settings.get("pol_fuel_expense_account")
	if not fallback:
		frappe.throw(
			_("No fuel expense account is set for {0}. Add a row for it under "
			  "Fuel Expense Account by Company in GDL Fleet Settings.").format(frappe.bold(company)),
			title=_("Expense Account Not Configured"),
		)

	owner = frappe.db.get_value("Account", fallback, "company")
	if owner and owner != company:
		frappe.throw(
			_("The fallback fuel account {0} belongs to {1}, but this abstract is for a "
			  "vehicle in {2}. Add a row for {2} under Fuel Expense Account by Company "
			  "in GDL Fleet Settings.").format(
				frappe.bold(fallback), frappe.bold(owner), frappe.bold(company)),
			title=_("Wrong Company"),
		)

	check_expense_account(fallback, company)
	return fallback


@frappe.whitelist()
def make_fuel_invoice(pol_abstract, provider):
	"""Raise the fuel claim for one provider against an approved abstract."""
	amount_field, supplier_setting = _provider_config(provider)
	doc = frappe.get_doc("POL Abstract", pol_abstract)

	if doc.docstatus != 1:
		frappe.throw(
			_("{0} is not approved yet. The fuel claim is raised from an approved abstract.").format(doc.name),
			title=_("Not Approved"),
		)

	amount = flt(doc.get(amount_field))
	if amount <= 0:
		frappe.throw(
			_("There is no {0} amount on this abstract to claim.").format(provider),
			title=_("Nothing to Claim"),
		)

	supplier = get_pol_setting(supplier_setting)
	if not supplier:
		frappe.throw(
			_("Set the {0} Supplier in GDL Fleet Settings before raising the claim.").format(provider),
			title=_("Supplier Not Configured"),
		)

	existing = get_claim_invoice(doc.name, supplier)
	if existing:
		frappe.throw(
			_("The {0} fuel claim for this abstract is already on Purchase Invoice {1}.").format(
				provider, frappe.bold(existing)
			),
			title=_("Already Claimed"),
		)

	company = frappe.db.get_value("Vehicle", doc.vehicle, "company") or frappe.defaults.get_user_default("Company")
	expense_account = get_fuel_expense_account(company)

	invoice = frappe.new_doc("Purchase Invoice")
	invoice.supplier = supplier
	invoice.company = company
	invoice.posting_date = doc.abstract_date or nowdate()
	invoice.set_posting_time = 1
	invoice.pol_abstract = doc.name
	invoice.remarks = _("Fuel claimed from {0} on POL Abstract {1} for vehicle {2}, period {3} to {4}.").format(
		provider, doc.name, doc.vehicle, doc.period_from, doc.period_to
	)
	invoice.append("items", {
		"item_name": _("Fuel - {0}").format(provider),
		"description": _("POL {0}: {1} litres for vehicle {2} ({3} to {4})").format(
			provider, doc.total_fuel_supplied, doc.vehicle, doc.period_from, doc.period_to
		),
		"qty": 1,
		"rate": amount,
		"uom": frappe.db.get_value("UOM", "Nos", "name") or None,
		"conversion_factor": 1,
		"expense_account": expense_account,
		"cost_center": doc.cost_center or None,
		"project": doc.project or None,
	})

	invoice.flags.ignore_permissions = True
	invoice.insert()
	return invoice.name


@frappe.whitelist()
def get_claim_status(pol_abstract):
	"""What can still be claimed on this abstract, for the form buttons."""
	doc = frappe.get_doc("POL Abstract", pol_abstract)
	status = {}
	for provider, (amount_field, supplier_setting) in PROVIDERS.items():
		invoice = get_claim_invoice(doc.name, get_pol_setting(supplier_setting))
		amount = flt(doc.get(amount_field))
		status[provider] = {
			"amount": amount,
			"invoice": invoice,
			"claimable": amount > 0 and not invoice,
		}
	return status
