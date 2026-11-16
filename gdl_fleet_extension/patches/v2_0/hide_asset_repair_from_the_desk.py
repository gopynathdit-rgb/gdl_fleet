# Copyright (c) 2026, GDL and contributors
"""Take Asset Repair off the fleet menu.

It cannot be used on this system and the requirement document does not ask for
it.

Asset is a MANDATORY field on Asset Repair, and no GDL vehicle is linked to an
Asset - 0 of 14 - so saving a repair against any vehicle fails outright with
"Asset None not found". The form has been on the menu since the module went in,
and has never held a record.

The document settles whether that matters. Section 2.1.1.4:

    "All routine and corrective service activities should be recorded against
     the vehicle and its odometer reading."

One record for both, and the only use of the word "repair" anywhere in it is
"Other repair or maintenance item" - the twelfth Service Type in that record's
own dropdown. The document never uses the words breakdown, accident, downtime,
capitalisation or fixed asset, which are the things Asset Repair exists to
provide.

Hidden on the workspace, not deleted. The DocType, its GDL fields, its records
and the code behind it all stay exactly as they are. If GDL ever puts its
vehicles on the asset register, un-hiding this link is the only step needed.
"""

import frappe

WORKSPACE = "GDL Fleet"
LINK = "Asset Repair"


def execute():
	if not frappe.db.exists("Workspace", WORKSPACE):
		return

	rows = frappe.get_all("Workspace Link", filters={
		"parent": WORKSPACE, "link_to": LINK, "type": "Link", "hidden": 0},
		pluck="name")

	for name in rows:
		frappe.db.set_value("Workspace Link", name, "hidden", 1, update_modified=False)

	if rows:
		frappe.clear_cache()
		frappe.db.commit()
		print(f"  {LINK} is off the {WORKSPACE} menu - it cannot be saved without an "
		      f"Asset, and the document does not ask for it.")
