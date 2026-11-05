"""Point the POL fuel claim at the BOD and STCBL suppliers.

Both suppliers already exist on the site. The expense account is deliberately
NOT guessed - GDL has two fuel accounts (Chairman's Office and General Office)
and which one applies is their decision, so the claim refuses to run until it
is set rather than charging the wrong account.
"""

import frappe

DEFAULTS = {
	"pol_bod_supplier": "BOD",
	"pol_stcbl_supplier": "STCBL",
}


def execute():
	settings = frappe.get_single("GDL Fleet Settings")
	changed = False

	for fieldname, supplier in DEFAULTS.items():
		if not settings.meta.get_field(fieldname):
			continue
		if settings.get(fieldname):
			continue
		if frappe.db.exists("Supplier", supplier):
			settings.set(fieldname, supplier)
			changed = True

	if changed:
		settings.flags.ignore_permissions = True
		settings.save()
		frappe.db.commit()
