# Copyright (c) 2026, GDL and contributors
"""Show a person's name, not their record id.

An Employee is named by its naming series, so every Link to one displayed
"E260001". That is the primary key, not a person - and it appeared on the POL
abstract, the service record, the movement order and its request alike, leaving
the reader to look up who E260001 is.

Employee already carries title_field = employee_name. It just was not being
used: frappe shows the title in a Link only when show_title_field_in_link is
set on the TARGET doctype. Setting it there fixes every Link to Employee at
once - the one place that covers "all place" - rather than adding a fetched
name field beside each one.

A Property Setter, so it is one row to remove and no core file is touched.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

# doctype -> the field holding the person's name. Each already declares it as
# its title_field; only the display flag is missing.
SHOW_NAME_IN_LINKS = {
	"Employee": "employee_name",
	# Driver is deliberately NOT here. GDL looked at it and said the id is what
	# they want to see for a driver. Adding "Driver": "full_name" is all it
	# would take if that changes.
}


def setup_people_display():
	"""Idempotent. Safe on install and on every migrate."""
	for doctype, title_field in SHOW_NAME_IN_LINKS.items():
		if not frappe.db.exists("DocType", doctype):
			continue

		meta = frappe.get_meta(doctype)
		if not meta.get_field(title_field):
			continue

		# Without a title_field there is no title to show, and the flag would
		# silently do nothing.
		if meta.title_field != title_field:
			make_property_setter(doctype, None, "title_field", title_field, "Data",
			                     for_doctype=True, validate_fields_for_doctype=False)

		make_property_setter(doctype, None, "show_title_field_in_link", 1, "Check",
		                     for_doctype=True, validate_fields_for_doctype=False)
		frappe.clear_cache(doctype=doctype)
