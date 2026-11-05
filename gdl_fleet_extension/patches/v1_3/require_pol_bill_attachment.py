"""Switch on the POL supplier bill requirement for sites that already exist.

Same trap as seed_pol_settings: the Check default in the DocType JSON applies
only when the single is first created, so on a site that already has GDL Fleet
Settings the new field arrives as 0 and the rule would sit there doing nothing.

Set once by a patch rather than by the seeder, which runs on every migrate and
could not tell "never configured" from "GDL switched this off deliberately".
"""

import frappe

FIELDNAME = "pol_abstract_requires_attachment"


def execute():
	settings = frappe.get_single("GDL Fleet Settings")
	if not settings.meta.get_field(FIELDNAME) or settings.get(FIELDNAME):
		return

	settings.set(FIELDNAME, 1)
	settings.flags.ignore_permissions = True
	settings.save()
	frappe.db.commit()
