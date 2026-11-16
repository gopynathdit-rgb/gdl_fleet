# Copyright (c) 2026, GDL and contributors
"""Clear the invoice link off the service record.

The link now lives on the Purchase Invoice ("Service Record"), and the service
form reads it from there. A link stored the other way round makes frappe refuse
to cancel the invoice:

    Cannot delete or cancel because Purchase Invoice ... is linked with
    Asset Maintenance Log ...

and cancelling a wrong invoice is how Accounts fix one. POL points the same way
for the same reason.

Records written before the change still carry the old value, so the very
invoices GDL raised while testing could not be cancelled. This moves each one
onto the invoice, where it belongs, and then clears it.
"""

import frappe

DOCTYPE = "Asset Maintenance Log"


def execute():
	if not frappe.db.has_column(DOCTYPE, "purchase_invoice"):
		return

	rows = frappe.db.sql(f"""
		select name, purchase_invoice from `tab{DOCTYPE}`
		where ifnull(purchase_invoice, '') != ''
	""", as_dict=True)

	moved = cleared = 0
	for row in rows:
		if frappe.db.exists("Purchase Invoice", row.purchase_invoice):
			# Carry it onto the invoice first, so nothing is lost: the form
			# reads from there now, and a record cleared without this would
			# forget it had ever been invoiced.
			if frappe.get_meta("Purchase Invoice").get_field("asset_maintenance_log") \
			   and not frappe.db.get_value("Purchase Invoice", row.purchase_invoice,
			                               "asset_maintenance_log"):
				frappe.db.set_value("Purchase Invoice", row.purchase_invoice,
				                    "asset_maintenance_log", row.name,
				                    update_modified=False)
				moved += 1

		frappe.db.set_value(DOCTYPE, row.name, "purchase_invoice", None,
		                    update_modified=False)
		cleared += 1

	if cleared:
		frappe.db.commit()
		print(f"  Cleared the stored invoice link on {cleared} service record(s); "
		      f"{moved} invoice(s) now name the service they came from. "
		      f"Those invoices can be cancelled again.")
