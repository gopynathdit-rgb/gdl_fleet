# Copyright (c) 2026, GDL and contributors
"""Push renewals that were submitted before the Vehicle sync covered them.

Re-runnable: the field map it reads has since grown to include the two
"renew by" dates, so a later run fills those on records already migrated.

Only Insurance was ever copied onto the Vehicle. A Registration or Fitness
renewal submitted before this change left the Vehicle's Registration Expiry
and Inspection Expiry blank, so the fields read as empty on a vehicle that
holds a valid certificate.

Walks the live renewal of each type per vehicle - never a superseded one - so
this cannot drag a vehicle back to a lapsed policy.
"""

import frappe

from gdl_fleet_extension.gdl_fleet.doctype.renewal_register.renewal_register import (
	VEHICLE_FIELDS_BY_TYPE,
	get_current_renewal,
)


def execute():
	if not frappe.db.exists("DocType", "Renewal Register"):
		return

	pairs = frappe.get_all(
		"Renewal Register",
		filters={"docstatus": 1, "renewal_type": ("in", list(VEHICLE_FIELDS_BY_TYPE))},
		fields=["vehicle", "renewal_type"],
		distinct=True,
	)

	updated = 0
	for pair in pairs:
		if not pair.vehicle or not frappe.db.exists("Vehicle", pair.vehicle):
			continue

		live = get_current_renewal(pair.vehicle, pair.renewal_type)
		if not live:
			continue

		doc = frappe.get_doc("Renewal Register", live.get("name"))
		values = {vehicle_field: doc.get(renewal_field)
		          for vehicle_field, renewal_field
		          in VEHICLE_FIELDS_BY_TYPE[pair.renewal_type].items()}

		current = frappe.db.get_value("Vehicle", pair.vehicle, list(values), as_dict=True)
		if current and all(current.get(k) == v for k, v in values.items()):
			continue		# already in step

		frappe.db.set_value("Vehicle", pair.vehicle, values, update_modified=False)
		updated += 1

	if updated:
		frappe.db.commit()
		print(f"  Brought {updated} vehicle/renewal pair(s) in step with the register.")
