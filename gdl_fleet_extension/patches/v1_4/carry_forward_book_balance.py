# Copyright (c) 2026, GDL and contributors
"""
Blueprint, POL Management: the fuel coupon's "to-date amount should be
maintained". POL Abstract gained an opening book balance so unspent coupon
carries from one period into the next.

A Check field's JSON default only applies when the Single is first created, so
an existing site needs the value written once. Existing abstracts are left
alone: their opening balance stays 0, which is exactly the number their
closing balance was already calculated from, so no figure on file changes.
The carry forward starts from the next abstract raised.
"""

import frappe


def execute():
	if not frappe.db.exists("DocType", "GDL Fleet Settings"):
		return

	field = "pol_carry_forward_book_balance"
	settings = frappe.get_single("GDL Fleet Settings")
	if not settings.meta.get_field(field):
		return
	if settings.get(field) not in (None, "", 0, "0"):
		return

	settings.set(field, 1)
	settings.flags.ignore_permissions = True
	settings.flags.ignore_validate = True
	settings.save()
	frappe.db.commit()
	print("  Fuel book balance now carries forward between POL abstracts.")
