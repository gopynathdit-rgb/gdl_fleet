# Copyright (c) 2026, GDL and contributors
"""
Fleet settings, and the one rule worth enforcing here.

An expense account is only usable by the company that owns it, and ERPNext
cannot post to a group account at all. Both facts are easy to get wrong while
picking an account from a long list, and the error they produce surfaces much
later - at the point someone tries to raise a claim, worded in ERPNext's terms
rather than GDL's. Checking on save puts the complaint next to the field that
caused it.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class GDLFleetSettings(Document):
	def validate(self):
		self.validate_fuel_accounts()
		self.validate_location_officers()

	def validate_fuel_accounts(self):
		seen = {}
		for row in self.get("pol_fuel_accounts") or []:
			if row.company in seen:
				frappe.throw(
					_("Row {0}: {1} already has a fuel account on row {2}.").format(
						row.idx, frappe.bold(row.company), seen[row.company]),
					title=_("Duplicate Company"),
				)
			seen[row.company] = row.idx
			check_expense_account(row.expense_account, row.company, _("Row {0}").format(row.idx))

		# The fallback has no company of its own, so all that can be checked here
		# is that it is postable. Whether it suits a given company is settled when
		# the claim is raised, against that claim's company.
		account = self.get("pol_fuel_expense_account")
		if account and frappe.db.get_value("Account", account, "is_group"):
			frappe.throw(
				_("{0} is a group account, so nothing can be posted to it. "
				  "Choose the ledger account beneath it.").format(frappe.bold(account)),
				title=_("Group Account"),
			)

	def validate_location_officers(self):
		"""One MTO per location, and exactly one head office.

		Two rows for the same location would make "who approves here" ambiguous,
		and two head offices would make "who is the final MTO" ambiguous. Both
		are cheap to catch here and expensive to debug later.
		"""
		seen = {}
		heads = []
		for row in self.location_officers or []:
			if row.location in seen:
				frappe.throw(
					_("{0} is listed twice, on rows {1} and {2}. "
					  "A location has one MTO.").format(
						frappe.bold(row.location), seen[row.location], row.idx
					),
					title=_("Duplicate Location"),
				)
			seen[row.location] = row.idx

			if cint(row.is_head_office):
				heads.append(row.idx)

			if frappe.db.get_value("Location", row.location, "is_group"):
				frappe.throw(
					_("Row {0}: {1} is a group location. Vehicles belong to the "
					  "locations under it, so name one of those instead.").format(
						row.idx, frappe.bold(row.location)
					),
					title=_("Group Location"),
				)

			if not frappe.db.get_value("User", row.mto, "enabled"):
				frappe.throw(
					_("Row {0}: {1} is disabled and cannot approve anything.").format(
						row.idx, frappe.bold(row.mto)
					)
				)

		if len(heads) > 1:
			frappe.throw(
				_("Rows {0} are all ticked Head Office. There is one final MTO.").format(
					frappe.bold(", ".join(str(i) for i in heads))
				),
				title=_("More Than One Head Office"),
			)

		if self.location_officers and not heads and cint(self.enforce_location_mto):
			frappe.msgprint(
				_("No row is ticked Head Office, so no one can approve for a location "
				  "whose own MTO is away. Tick the head office row."),
				title=_("No Final MTO"),
				indicator="orange",
			)


def check_expense_account(account, company, prefix=""):
	"""Refuse an account that cannot carry this company's fuel expense."""
	if not account or not company:
		return

	row = frappe.db.get_value(
		"Account", account, ["company", "is_group", "root_type", "disabled"], as_dict=True)
	if not row:
		return

	lead = f"{prefix}: " if prefix else ""

	if row.is_group:
		frappe.throw(
			_("{0}{1} is a group account, so nothing can be posted to it. "
			  "Choose the ledger account beneath it.").format(lead, frappe.bold(account)),
			title=_("Group Account"),
		)
	if row.company != company:
		frappe.throw(
			_("{0}{1} belongs to {2}, not to {3}. An account can only be used by "
			  "the company that owns it.").format(
				lead, frappe.bold(account), frappe.bold(row.company), frappe.bold(company)),
			title=_("Wrong Company"),
		)
	if row.disabled:
		frappe.throw(
			_("{0}{1} is disabled.").format(lead, frappe.bold(account)),
			title=_("Account Disabled"),
		)
	if row.root_type != "Expense":
		frappe.throw(
			_("{0}{1} is {2}, not an Expense account.").format(
				lead, frappe.bold(account), frappe.bold(row.root_type or _("untyped"))),
			title=_("Not an Expense Account"),
		)
