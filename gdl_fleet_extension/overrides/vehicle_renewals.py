# Copyright (c) 2026, GDL and contributors
"""Vehicle insurance / registration details -> the Renewal Register.

GDL: "once these details were updated, it should show in the Renewal Register
for both Registration and Insurance Renewal. Its not updating. Please link
these 2."

The link already ran one way: submitting a Renewal Register wrote its dates
onto the Vehicle. Typing the dates straight onto the Vehicle did nothing, so a
vehicle could show an insurance expiry that the register had never heard of -
and the register is what the reminders, the Insurance / Renewal Due report and
the whole §4.5 history run off.

This closes the loop. Saving a Vehicle with insurance or registration details
creates - or renews - the matching Renewal Register record.

Three cases, deliberately distinguished:

  nothing in the register yet   create a submitted record from the Vehicle
  same expiry, other details    correct the live record in place
  a different expiry            a RENEWAL: a new record chained to the old one
                                through previous_renewal, which marks the old
                                one Renewed and keeps it. §4.5 requires the
                                history to be retained, so nothing is edited
                                away.

No loop: the register writes back with frappe.db.set_value, which runs no
document hooks, so that write cannot re-enter this.
"""

import frappe
from frappe import _
from frappe.utils import getdate

from gdl_fleet_extension.gdl_fleet.doctype.renewal_register.renewal_register import (
	get_current_renewal,
)

# Which Vehicle field feeds which Renewal Register field, per type.
#
# Insurance and Registration only - the two GDL named. Fitness has an
# Inspection Expiry on the same screen and could be added here in one line,
# but creating register records nobody asked for is not this change's job.
RENEWAL_SOURCES = {
	"Insurance": {
		"expiry_date": "end_date",
		"effective_from": "start_date",
		"provider": "insurance_company",
		"certificate_no": "policy_no",
	},
	"Registration": {
		"expiry_date": "registration_expiry",
	},
}

# Corrected in place when the expiry has not moved. Never expiry_date itself -
# a changed expiry is a renewal, not a correction.
CORRECTABLE = ("provider", "certificate_no", "effective_from")


def on_update(doc, method=None):
	for renewal_type, mapping in RENEWAL_SOURCES.items():
		try:
			sync_one(doc, renewal_type, mapping)
		except Exception:
			# A master record must still save. The register is a convenience
			# built on top of it, and a failure here is worth logging, not
			# worth blocking somebody editing a vehicle.
			frappe.log_error(
				title=f"Renewal Register sync failed for {doc.name} ({renewal_type})",
				message=frappe.get_traceback(),
			)


def sync_one(doc, renewal_type, mapping):
	values = {field: doc.get(source) for field, source in mapping.items()}
	if not values.get("expiry_date"):
		return		# nothing recorded on the vehicle for this type

	live = get_current_renewal(doc.name, renewal_type)

	if not live:
		create(doc, renewal_type, values)
		return

	if getdate(live.get("expiry_date")) == getdate(values["expiry_date"]):
		correct(live.get("name"), values)
		return

	create(doc, renewal_type, values, previous=live.get("name"))


def create(doc, renewal_type, values, previous=None):
	renewal = frappe.new_doc("Renewal Register")
	renewal.vehicle = doc.name
	renewal.renewal_type = renewal_type
	renewal.location = doc.get("site")
	if previous:
		renewal.previous_renewal = previous
	for field, value in values.items():
		if value:
			renewal.set(field, value)
	renewal.remarks = _("Raised from the Vehicle master.")

	# The register writes straight back onto this Vehicle on submit. That uses
	# frappe.db.set_value and fires no hooks, so it cannot re-enter on_update.
	renewal.flags.ignore_permissions = True
	renewal.insert()
	renewal.submit()
	return renewal.name


def correct(name, values):
	"""Same expiry, different particulars - a correction, not a renewal.

	Written with db_set because the record is submitted. Only the descriptive
	fields; the dates that define the period are never quietly rewritten.
	"""
	changed = {}
	for field in CORRECTABLE:
		new = values.get(field)
		if new and frappe.db.get_value("Renewal Register", name, field) != new:
			changed[field] = new
	if changed:
		frappe.db.set_value("Renewal Register", name, changed, update_modified=False)
