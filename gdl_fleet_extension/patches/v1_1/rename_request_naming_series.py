"""Move Movement Order Request onto the MOR- series.

The DocType was renamed from Vehicle Booking Request, but its naming series
kept the old VBR- prefix, so new requests were still numbered VBR-2026-00018.

frappe's naming-series tool stores the options and the default as Property
Setters, which override whatever the DocType JSON says, so those are what has
to be corrected. VBR- stays in the options list: requests created before the
rename still carry it and must continue to validate.
"""

import frappe

DOCTYPE = "Movement Order Request"
NEW_SERIES = "MOR-.YYYY.-.#####"
OLD_SERIES = "VBR-.YYYY.-.#####"


def execute():
	options = f"{NEW_SERIES}\n{OLD_SERIES}"

	for property_name, value in (("options", options), ("default", NEW_SERIES)):
		existing = frappe.db.get_value(
			"Property Setter",
			{"doc_type": DOCTYPE, "field_name": "naming_series", "property": property_name},
			"name",
		)
		if existing:
			frappe.db.set_value("Property Setter", existing, "value", value)
		else:
			frappe.get_doc({
				"doctype": "Property Setter",
				"doctype_or_field": "DocField",
				"doc_type": DOCTYPE,
				"field_name": "naming_series",
				"property": property_name,
				"property_type": "Text" if property_name == "options" else "Data",
				"value": value,
				"module": "GDL Fleet",
			}).insert(ignore_permissions=True)

	frappe.clear_cache(doctype=DOCTYPE)
	frappe.db.commit()
