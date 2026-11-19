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
	# Both breaks are hidden only because everything behind them is. hide()
	# refuses either one the moment a visible field moves in after it - see the
	# scar recorded there.
	"column_break_2", "column_break_6",
)

# The service-bill approval and purchasing cycle. Off until GDL asks for it.
PURCHASING_CYCLE = (
	"bill_status", "submitted_by", "submission_date", "approved_by",
	"rejection_reason", "purchase_order", "purchase_invoice",
	"purchasing_message", "payment_status",
	"gdl_purchasing_cb",
)

# Back on the form, because GDL asked for the button that fills them: once a
# service is invoiced, the record should say so and link to it. The approval
# chain above stays off - this is one button and the invoice it made.
# purchase_invoice is NOT here. The record stores no link to its invoice - a
# stored Link makes the invoice impossible to cancel - so the form reads it
# from the invoice side and shows it as a button instead of a field.
SHOW_AGAIN = ("gdl_purchasing_section", "purchasing_status")

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
	# Order first, hide second. hide() refuses a Column Break that still has
	# visible fields behind it, so hiding before the reflow would refuse
	# column_break_6 on every run and never recover.
	reflow()

	for fieldname in ERPNEXT_SCAFFOLDING + PURCHASING_CYCLE:
		hide(DOCTYPE, fieldname)

	for fieldname in SHOW_AGAIN:
		set_property(DOCTYPE, fieldname, "hidden", "0", "Check")

	for fieldname in HIDE_ON_LINE:
		hide("Fleet Service Item", fieldname)
		set_property("Fleet Service Item", fieldname, "in_list_view", "0", "Check")

	for doctype, labels in LABELS.items():
		for fieldname, label in labels.items():
			set_property(doctype, fieldname, "label", label, "Data")

	# The record is about a vehicle. Without one it joins no service history and
	# appears on no due list - which is how logs with no vehicle got saved.
	set_property(DOCTYPE, "vehicle", "reqd", "1", "Check")

	# Service Date is required only once the service is Completed. A flat
	# reqd=1 broke ERPNext's own maintenance plan: Asset Maintenance
	# sync_maintenance_tasks() creates a log for each SCHEDULED task, with no
	# completion date because the work has not happened yet, and mandatory
	# validation refused every one of them. Conditional keeps the driver
	# prompted without breaking the plan.
	set_property(DOCTYPE, "completion_date", "mandatory_depends_on",
	             'eval:doc.maintenance_status=="Completed"', "Data")

	# The driver's default (Completed) is set on the FORM, not here - see
	# public/js/asset_maintenance_log.js. A DocType-level default reaches
	# ERPNext's plan machinery too, and a scheduled service that defaults to
	# Completed then demands a completion date it cannot have.

	frappe.clear_cache(doctype=DOCTYPE)
	frappe.clear_cache(doctype="Fleet Service Item")


# ERPNext's own order for Asset Maintenance Log, with maintenance_status and
# completion_date lifted ahead of column_break_6. Everything else keeps its
# place. Fields ERPNext adds later are not in this list; Meta.sort_fields
# appends those rather than dropping them.
STANDARD_FIELD_ORDER = [
	"asset_maintenance", "naming_series", "asset_name", "column_break_2",
	"item_code", "item_name",
	"section_break_5",
	# the service record, in the first column
	"maintenance_status", "completion_date",
	# the scaffolding, behind the break, where being hidden costs nothing
	"column_break_6",
	"task", "task_name", "maintenance_type", "periodicity",
	"has_certificate", "certificate_attachement",
	"assign_to_name", "task_assignee_email", "due_date",
	"description", "column_break_9", "actions_performed", "amended_from",
]


def reflow():
	"""Two readable columns once the scaffolding is gone.

	The service fields are moved ahead of column_break_6 so they sit in the
	section's FIRST column, and the hidden scaffolding ends up behind the break
	where it costs nothing.

	It has to be done by reordering, not by adding a section of our own.
	Meta.sort_fields deliberately relocates a break:

	    if field.fieldtype in ["Section Break", "Column Break"] ...
	        # Find the next section or column break and set target_position
	        # to just one field before

	so a Section Break inserted mid-section is pushed to the END of that
	section, wherever insert_after points. A new "Service Details" section
	landed after Service Items for exactly that reason.

	Vehicle then Location, because the record is filed against the vehicle. The
	service facts on the left, what it cost and when it is next due on the
	right.
	"""
	import json
	make_property_setter(DOCTYPE, None, "field_order",
	                     json.dumps(STANDARD_FIELD_ORDER), "Text",
	                     for_doctype=True, validate_fields_for_doctype=False)

	create_custom_field(DOCTYPE, {
		"fieldname": "gdl_service_cb", "fieldtype": "Column Break",
		"insert_after": "service_provider", "module": "GDL Fleet",
	}, ignore_validate=True)

	# Where `location` and `labour_cost` sit is NOT decided here any more.
	# This function used to pin location after `vehicle` and labour_cost after
	# `gdl_service_cb`, and because it runs after maintenance_fields it quietly
	# undid both of GDL's later layout changes - Location beside Vehicle, and
	# the costs under the Service Items table. One owner for the order:
	# maintenance_fields.enforce_field_order(), which runs last.
	from gdl_fleet_extension.setup.maintenance_fields import enforce_field_order

	enforce_field_order()


def hide(doctype, fieldname):
	"""Take a field off the form.

	A Column Break is the exception that has to be checked. frappe's
	Column.refresh() puts hide-control on the column WRAPPER, and every field
	in that column is a child of it - so hiding a column break hides every
	field after it until the next break, however visible those fields say they
	are in the meta.

	That is not theory. Hiding column_break_6 took Status, Service Date,
	Odometer Reading and Service Provider off the form while the meta still
	reported all four as visible, and a maintenance log could not be submitted
	because nobody could reach Status to set it to Completed.
	"""
	if frappe.get_meta(doctype).get_field(fieldname) \
	   and frappe.get_meta(doctype).get_field(fieldname).fieldtype == "Column Break":
		swallowed = fields_in_column(doctype, fieldname)
		if swallowed:
			frappe.msgprint(
				f"Refusing to hide {doctype}.{fieldname}: it would also hide "
				f"{', '.join(swallowed)}.", raise_exception=False)
			return

	set_property(doctype, fieldname, "hidden", "1", "Check")


def fields_in_column(doctype, column_break):
	"""The visible fields a hidden column break would take with it."""
	fields = frappe.get_meta(doctype).fields
	seen = False
	out = []
	for field in fields:
		if field.fieldname == column_break:
			seen = True
			continue
		if not seen:
			continue
		if field.fieldtype in ("Column Break", "Section Break", "Tab Break"):
			break
		if not field.hidden:
			out.append(field.fieldname)
	return out


def set_property(doctype, fieldname, prop, value, property_type):
	if not frappe.get_meta(doctype).get_field(fieldname):
		return
	make_property_setter(doctype, fieldname, prop, value, property_type,
	                     for_doctype=False, validate_fields_for_doctype=False)
