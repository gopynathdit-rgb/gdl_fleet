# Copyright (c) 2026, GDL and contributors
"""
Raising a Purchase Order from a fleet document.

Shared by maintenance completion and insurance renewal so both behave the same
way, and so there is one place that decides what "ready to purchase" means.

Three principles run through this module.

  * A purchase order is a commitment. Both automations are OFF until GDL turns
    them on and names the service item, so nothing is ordered on anyone's
    behalf by surprise.

  * Nothing is invented. Supplier, item and company come from the source
    document or from GDL Fleet Settings. Where a value is missing the document
    is marked Pending with a note naming exactly what is absent, and the people
    who can fix it are told. An incomplete purchase order is never created.

  * Repeating is safe. The caller may be a scheduler that runs daily, a retry,
    or someone saving a record twice. Every entry point checks for an existing
    live order first, so the same requirement is never ordered twice.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

NOT_REQUIRED = "Not Required"
INVOICED = "Invoiced"
PENDING = "Pending"
ORDERED = "Ordered"
FAILED = "Failed"


def get_setting(fieldname, default=None):
	value = frappe.db.get_single_value("GDL Fleet Settings", fieldname)
	return default if value in (None, "") else value


def get_purchasing_company(doc=None):
	"""Configured company, else the one on the document, else the site default."""
	company = get_setting("purchasing_company")
	if company:
		return company
	if doc is not None and doc.get("company"):
		return doc.get("company")
	if doc is not None and doc.get("vehicle"):
		vehicle_company = frappe.db.get_value("Vehicle", doc.get("vehicle"), "company")
		if vehicle_company:
			return vehicle_company
	return frappe.defaults.get_user_default("Company")


def has_live_order(doctype: str, name: str) -> str | None:
	"""An order already raised for this record and not cancelled."""
	existing = frappe.db.get_value(doctype, name, "purchase_order")
	if not existing:
		return None
	if not frappe.db.exists("Purchase Order", existing):
		return None
	if frappe.db.get_value("Purchase Order", existing, "docstatus") == 2:
		return None
	return existing


def record_outcome(doctype, name, status, message=None, purchase_order=None):
	"""Write the result back without disturbing the document's own lifecycle.

	db_set is used deliberately: these records are often submitted, and a full
	save would fight the workflow or be refused outright.
	"""
	values = {"purchasing_status": status, "purchasing_message": message or ""}
	if purchase_order is not None:
		values["purchase_order"] = purchase_order
	frappe.db.set_value(doctype, name, values, update_modified=False)


def notify(subject, message, doctype=None, name=None):
	"""Tell whoever is responsible. Never raises - a failed notice must not
	undo a purchase order that was created successfully."""
	role = get_setting("purchase_order_notify_role")
	if not role:
		return
	try:
		recipients = [
			u for u in frappe.get_all(
				"Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"
			) if frappe.db.get_value("User", u, "enabled")
		]
		if not recipients:
			return
		notification = frappe.get_doc({
			"doctype": "Notification Log",
			"subject": subject,
			"email_content": message,
			"document_type": doctype,
			"document_name": name,
			"for_user": recipients[0],
			"type": "Alert",
		})
		notification.flags.ignore_permissions = True
		notification.insert()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Fleet purchasing notification failed")


def missing_configuration(supplier, item, company) -> list[str]:
	"""What is stopping a valid order being raised."""
	missing = []
	if not supplier:
		missing.append(_("Supplier"))
	elif not frappe.db.exists("Supplier", supplier):
		missing.append(_("Supplier {0} does not exist").format(supplier))

	if not item:
		missing.append(_("Service Item"))
	elif not frappe.db.exists("Item", item):
		missing.append(_("Item {0} does not exist").format(item))

	if not company:
		missing.append(_("Company"))
	return missing


def create_purchase_order(
	*,
	source_doctype: str,
	source_name: str,
	supplier: str,
	item_code: str,
	rate,
	description: str,
	schedule_date=None,
	company=None,
	cost_center=None,
	project=None,
	qty=1,
):
	"""Create a DRAFT Purchase Order for a fleet requirement.

	Left as a draft on purpose: purchasing reviews and submits it, so the
	automation never commits spend on its own. Returns the order name, or None
	when the configuration is incomplete - in which case the source document is
	marked Pending with the reason.
	"""
	existing = has_live_order(source_doctype, source_name)
	if existing:
		return existing

	missing = missing_configuration(supplier, item_code, company)
	if missing:
		reason = _("Cannot raise a purchase order: {0} missing. Set it on the record "
		           "or in GDL Fleet Settings, then retry.").format(", ".join(missing))
		record_outcome(source_doctype, source_name, PENDING, reason)
		notify(
			_("Fleet purchase order pending: {0}").format(source_name),
			reason, source_doctype, source_name,
		)
		return None

	# ERPNext refuses a Required By date earlier than the order date. The
	# triggers here are often historic - an insurance policy that expired last
	# week, a service completed yesterday - so the need is "now", not the date
	# that prompted it.
	today = getdate(nowdate())
	required_by = getdate(schedule_date) if schedule_date else today
	if required_by < today:
		required_by = today

	try:
		order = frappe.new_doc("Purchase Order")
		order.supplier = supplier
		order.company = company
		order.transaction_date = nowdate()
		order.schedule_date = required_by
		order.append("items", {
			"item_code": item_code,
			"description": description,
			"qty": flt(qty) or 1,
			"rate": flt(rate),
			"schedule_date": required_by,
			"cost_center": cost_center or None,
			"project": project or None,
		})
		order.flags.ignore_permissions = True
		order.insert()
	except Exception as exc:
		reason = _("Purchase order could not be created: {0}").format(str(exc)[:200])
		record_outcome(source_doctype, source_name, FAILED, reason)
		frappe.log_error(frappe.get_traceback(), f"Fleet purchase order failed for {source_name}")
		notify(_("Fleet purchase order failed: {0}").format(source_name),
		       reason, source_doctype, source_name)
		return None

	record_outcome(
		source_doctype, source_name, ORDERED,
		_("Draft Purchase Order {0} raised for review.").format(order.name),
		purchase_order=order.name,
	)
	notify(
		_("Fleet purchase order {0} raised").format(order.name),
		_("Raised from {0} {1} for supplier {2}.").format(source_doctype, source_name, supplier),
		source_doctype, source_name,
	)
	return order.name


def duplicate_bill(supplier: str, bill_no: str, exclude_invoice: str | None = None) -> str | None:
	"""Has this supplier's bill number already been invoiced?

	The site has Accounts Settings > check_supplier_invoice_uniqueness switched
	OFF, so ERPNext will happily take the same bill twice. The check is made
	here so a service centre cannot be paid twice for one job.
	"""
	if not supplier or not bill_no:
		return None

	filters = {"supplier": supplier, "bill_no": bill_no, "docstatus": ("<", 2)}
	if exclude_invoice:
		filters["name"] = ("!=", exclude_invoice)
	return frappe.db.exists("Purchase Invoice", filters)


def create_purchase_invoice(
	*,
	source_doctype: str,
	source_name: str,
	supplier: str,
	item_code: str,
	rate,
	description: str,
	bill_no=None,
	bill_date=None,
	company=None,
	cost_center=None,
	project=None,
	qty=1,
	purchase_order=None,
	link_field="purchase_invoice",
):
	"""Create a DRAFT Purchase Invoice from a supplier's actual bill.

	Draft on purpose: Accounts check it against the paper bill and submit it.
	Nothing here posts to the ledger, and nothing marks anything paid.
	"""
	existing = frappe.db.get_value(source_doctype, source_name, link_field)
	if existing and frappe.db.exists("Purchase Invoice", existing):
		if frappe.db.get_value("Purchase Invoice", existing, "docstatus") != 2:
			return existing

	missing = missing_configuration(supplier, item_code, company)
	if missing:
		reason = _("Cannot raise a purchase invoice: {0} missing.").format(", ".join(missing))
		record_outcome(source_doctype, source_name, PENDING, reason)
		notify(_("Fleet invoice pending: {0}").format(source_name), reason,
		       source_doctype, source_name)
		return None

	clash = duplicate_bill(supplier, bill_no)
	if clash:
		reason = _("Bill {0} from {1} is already on Purchase Invoice {2}. "
		           "A service centre must not be paid twice for one job.").format(
			bill_no, supplier, clash)
		record_outcome(source_doctype, source_name, FAILED, reason)
		notify(_("Duplicate supplier bill: {0}").format(source_name), reason,
		       source_doctype, source_name)
		return None

	today = getdate(nowdate())
	posting = getdate(bill_date) if bill_date else today
	if posting > today:
		posting = today

	try:
		invoice = frappe.new_doc("Purchase Invoice")
		invoice.supplier = supplier
		invoice.company = company
		invoice.posting_date = nowdate()
		invoice.set_posting_time = 1
		if bill_no:
			invoice.bill_no = bill_no
		if bill_date:
			invoice.bill_date = posting
		invoice.append("items", {
			"item_code": item_code,
			"description": description,
			"qty": flt(qty) or 1,
			"rate": flt(rate),
			"cost_center": cost_center or None,
			"project": project or None,
			"purchase_order": purchase_order or None,
		})
		invoice.flags.ignore_permissions = True
		invoice.insert()
	except Exception as exc:
		reason = _("Purchase invoice could not be created: {0}").format(str(exc)[:200])
		record_outcome(source_doctype, source_name, FAILED, reason)
		frappe.log_error(frappe.get_traceback(), f"Fleet purchase invoice failed for {source_name}")
		notify(_("Fleet invoice failed: {0}").format(source_name), reason,
		       source_doctype, source_name)
		return None

	frappe.db.set_value(source_doctype, source_name, link_field, invoice.name,
	                    update_modified=False)
	record_outcome(
		source_doctype, source_name, INVOICED,
		_("Draft Purchase Invoice {0} raised from bill {1} for Accounts to check.")
		.format(invoice.name, bill_no or "-"),
	)
	notify(_("Fleet purchase invoice {0} raised").format(invoice.name),
	       _("From {0} {1}, supplier {2}, bill {3}.").format(
		       source_doctype, source_name, supplier, bill_no or "-"),
	       source_doctype, source_name)
	return invoice.name


def get_payment_status(invoice: str | None) -> str:
	"""Payment state read from the accounting record, never asserted.

	A bill being submitted or a job being finished says nothing about whether
	the service centre has been paid. Only the invoice knows.
	"""
	if not invoice or not frappe.db.exists("Purchase Invoice", invoice):
		return "Not Invoiced"

	row = frappe.db.get_value("Purchase Invoice", invoice,
	                          ["docstatus", "status", "outstanding_amount"], as_dict=True)
	if row.docstatus == 2:
		return "Cancelled"
	if row.docstatus == 0:
		return "Not Invoiced"

	if row.status in ("Paid", "Partly Paid", "Overdue"):
		return row.status
	return "Paid" if flt(row.outstanding_amount) <= 0 else "Unpaid"
