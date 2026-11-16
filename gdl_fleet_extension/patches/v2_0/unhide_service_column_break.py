# Copyright (c) 2026, GDL and contributors
"""Put Status, Service Date, Odometer and Service Provider back on the form.

A regression from the form simplification. column_break_6 was hidden to spare
an empty column, and frappe's Column.refresh() puts hide-control on the column
WRAPPER:

    const hide = this.df.hidden || this.df.hidden_due_to_dependency;
    this.wrapper.toggleClass("hide-control", !!hide);

Every field in that column is a child of that wrapper, so hiding the break hid
the four fields after it. The meta still reported all four as visible, which is
why nothing caught it: GDL found it when a maintenance log could not be
submitted - "Maintenance Status has to be Cancelled or Completed to Submit" -
with no Status field anywhere on the screen to change.

The Property Setter is deleted rather than set to 0, so the field goes back to
what the DocType says instead of carrying a GDL override that means "the same
as standard".
"""

import frappe

DOCTYPE = "Asset Maintenance Log"
FIELD = "column_break_6"


def execute():
	name = frappe.db.get_value("Property Setter", {
		"doc_type": DOCTYPE, "field_name": FIELD, "property": "hidden"})

	if name:
		frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
		print(f"  {DOCTYPE}.{FIELD} is no longer hidden - the four fields after "
		      f"it are back on the form.")

	# The section heading moved to gdl_service_section, which setup creates.
	stale = frappe.db.get_value("Property Setter", {
		"doc_type": DOCTYPE, "field_name": "section_break_5", "property": "label"})
	if stale:
		frappe.delete_doc("Property Setter", stale, ignore_permissions=True, force=True)

	frappe.clear_cache(doctype=DOCTYPE)
	frappe.db.commit()
