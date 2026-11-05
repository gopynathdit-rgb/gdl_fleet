# Copyright (c) 2026, GDL and contributors
"""The simple service record GDL asked for.

Final document 2.1.1.4 Vehicle Maintenance Management lists exactly what a
service record holds:

    Vehicle, Location, Service Date, Odometer Reading, Service Type,
    Service Provider, Service Description, Parts/Materials Used,
    Labour/Service Cost, Total Cost, Invoice/Reference No, the next service
    date or odometer, and the Cost Center / Project the expense belongs to.

Every one of those already exists on Asset Maintenance Log. What made the form
hard to use was the twenty-four fields standing AROUND them:

  * fourteen belong to ERPNext's own asset-maintenance machinery - Asset
    Maintenance, Asset Name, Item Code, Task, Periodicity, Certificate and so
    on. They are filled by the maintenance plan or left empty. A workshop clerk
    recording an oil change has no use for any of them.

  * ten are a service-bill approval and purchasing cycle - Bill Status,
    Submitted By, Approved By, Purchase Order, Purchase Invoice, Payment
    Status. The document asks for an Invoice/Reference No, not a procurement
    chain, and the chain could not run anyway: it needs a Service Item and a
    Purchasing Company that GDL has never set, so every completed record sat at
    "Purchasing: Pending" with an error nobody could clear.

Nothing is deleted. The fields keep their data and their code, and a Property
Setter is a row that can be removed the day GDL wants the purchasing cycle
back. They are simply off the screen until then.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

DOCTYPE = "Asset Maintenance Log"

# ERPNext's asset-maintenance scaffolding. Filled by a maintenance plan when one
# drives the log, meaningless when a clerk records a service by hand.
ERPNEXT_SCAFFOLDING = (
	"asset_maintenance", "asset_name", "item_code", "item_name",
	"task", "task_name", "maintenance_type", "periodicity",
	"assign_to_name", "task_assignee_email", "due_date",
	"has_certificate", "certificate_attachement", "description",
	# Both columns held nothing but the above. Left in place they render as
	# empty space beside the fields that remain.
	"column_break_2", "column_break_6",
)

# The service-bill approval and purchasing cycle. Off until GDL asks for it.
PURCHASING_CYCLE = (
	"bill_status", "submitted_by", "submission_date", "approved_by",
	"rejection_reason", "purchase_order", "purchase_invoice",
	"purchasing_status", "purchasing_message", "payment_status",
	"gdl_purchasing_section", "gdl_purchasing_cb",
)

# The document's own words, on the form.
LABELS = {
	DOCTYPE: {
		"odometer": "Odometer Reading",
		"actions_performed": "Service Description",
		"bill_no": "Invoice / Reference No",
		"service_items": "Service Items",
		"maintenance_status": "Status",
		"section_break_5": "Service Details",
		"service_items_section": "Service Items",
		"column_break_9": "Service Description",
	},
	"Fleet Service Item": {
		"service_item": "Service Type",
		"part_brand": "Part / Material Used",
	},
}

# One Invoice/Reference No, on the record - not one per line as well.
HIDE_ON_LINE = ("invoice_reference",)


def setup_simple_maintenance_form():
	"""Idempotent. Safe on install and on every migrate."""
	for fieldname in ERPNEXT_SCAFFOLDING + PURCHASING_CYCLE:
		hide(DOCTYPE, fieldname)

	reflow()

	for fieldname in HIDE_ON_LINE:
		hide("Fleet Service Item", fieldname)
		set_property("Fleet Service Item", fieldname, "in_list_view", "0", "Check")

	for doctype, labels in LABELS.items():
		for fieldname, label in labels.items():
			set_property(doctype, fieldname, "label", label, "Data")

	# The record is about a vehicle. Without one it joins no service history and
	# appears on no due list - which is how logs with no vehicle got saved.
	set_property(DOCTYPE, "vehicle", "reqd", "1", "Check")

	frappe.clear_cache(doctype=DOCTYPE)
	frappe.clear_cache(doctype="Fleet Service Item")


def reflow():
	"""Two readable columns once the scaffolding is gone.

	Vehicle then Location, because the record is filed against the vehicle. The
	service facts on the left, what it cost and when it is next due on the
	right.
	"""
	if frappe.db.exists("Custom Field", {"dt": DOCTYPE, "fieldname": "location"}):
		frappe.db.set_value("Custom Field", {"dt": DOCTYPE, "fieldname": "location"},
		                    "insert_after", "vehicle")

	create_custom_field(DOCTYPE, {
		"fieldname": "gdl_service_cb", "fieldtype": "Column Break",
		"insert_after": "service_provider", "module": "GDL Fleet",
	}, ignore_validate=True)

	# labour_cost also asks to sit after service_provider, and two fields
	# claiming the same anchor fall back on the order they were created in -
	# which put the break at the far end of the section. Chain them instead.
	frappe.db.set_value("Custom Field", {"dt": DOCTYPE, "fieldname": "labour_cost"},
	                    "insert_after", "gdl_service_cb")


def hide(doctype, fieldname):
	set_property(doctype, fieldname, "hidden", "1", "Check")


def set_property(doctype, fieldname, prop, value, property_type):
	if not frappe.get_meta(doctype).get_field(fieldname):
		return
	make_property_setter(doctype, fieldname, prop, value, property_type,
	                     for_doctype=False, validate_fields_for_doctype=False)
