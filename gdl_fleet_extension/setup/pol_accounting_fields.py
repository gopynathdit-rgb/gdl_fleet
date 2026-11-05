# Copyright (c) 2026, GDL and contributors
"""
Traceability from the fuel invoice back to the POL abstract it came from.

A custom field on the STANDARD Purchase Invoice, shipped as app data - no core
file is edited.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

POL_INVOICE_FIELD = {
	"fieldname": "pol_abstract",
	"label": "POL Abstract",
	"fieldtype": "Link",
	"options": "POL Abstract",
	"insert_after": "bill_date",
	"read_only": 1,
	"no_copy": 1,
	"print_hide": 0,
	"module": "GDL Fleet",
	"description": "The approved fuel abstract this claim was raised from.",
}


def setup_pol_accounting_fields():
	if not frappe.db.exists("Custom Field", {"dt": "Purchase Invoice", "fieldname": "pol_abstract"}):
		create_custom_field("Purchase Invoice", POL_INVOICE_FIELD, ignore_validate=True)
	return True
