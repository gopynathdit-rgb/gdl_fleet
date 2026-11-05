# Copyright (c) 2026, GDL and contributors
"""
The two purchasing automations the customer asked for.

CR3 - a completed maintenance record may raise a purchase order for the
workshop that did the work.

CR4 - an insurance policy reaching expiry may raise a purchase order for its
renewal.

Both are OFF until switched on in GDL Fleet Settings, because a purchase order
is a spending commitment and neither rule is safe to assume.

A note on CR3 that GDL should settle: a purchase order raised AFTER a workshop
has finished is a formality, not a control - the money is already committed. For
outsourced work the order normally comes first. The automation is built as asked
and defaults to off; see the final report.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, now_datetime, nowdate

from gdl_fleet_extension.utils.purchasing import (
	INVOICED,
	NOT_REQUIRED,
	ORDERED,
	PENDING,
	create_purchase_invoice,
	create_purchase_order,
	duplicate_bill,
	get_payment_status,
	get_purchasing_company,
	get_setting,
	has_live_order,
	notify,
	record_outcome,
)

MAINTENANCE_DOCTYPE = "Asset Maintenance Log"
RENEWAL_DOCTYPE = "Renewal Register"


# ---------------------------------------------------------------------------
# External maintenance: the driver's service bill
#
# The real process is: the driver takes the vehicle out, an external service
# centre does the work, the driver brings back the bill, the company approves
# it, and the service centre is paid.
#
# So nothing is raised when maintenance is merely marked Completed - at that
# moment there is no bill and no agreed amount. The purchasing document is
# raised when the bill is APPROVED, and it carries the supplier's own invoice
# number and the amount actually billed.
#
# Because the work is already done, a Purchase Invoice normally matches
# reality. A Purchase Order is supported for companies whose policy demands one
# even after the fact, and is then raised first and referenced by the invoice.
# ---------------------------------------------------------------------------
BILL_DRAFT = "Draft"
BILL_SERVICE_COMPLETED = "Service Completed"
BILL_SUBMITTED = "Bill Submitted"
BILL_PENDING_APPROVAL = "Pending Approval"
BILL_APPROVED = "Approved"
BILL_PAID = "Payment Processed"
BILL_REJECTED = "Rejected"


def bill_is_complete(doc) -> list[str]:
	"""What the driver still has to supply before the bill can go for approval."""
	missing = []
	if not doc.get("service_provider"):
		missing.append(_("Service Centre (Supplier)"))
	if not doc.get("bill_no"):
		missing.append(_("Bill / Invoice No."))
	if not doc.get("bill_date"):
		missing.append(_("Bill Date"))
	if flt(doc.get("total_cost")) <= 0:
		missing.append(_("Total Bill Amount"))
	if int(get_setting("maintenance_bill_requires_attachment", 1) or 0) and not doc.get("bill_attachment"):
		missing.append(_("Bill Attachment"))
	return missing


def maintenance_description(doc) -> str:
	"""What the service centre is being paid for, from the record's own items."""
	items = [row.service_item for row in (doc.get("service_items") or []) if row.service_item]
	detail = ", ".join(items) if items else _("Vehicle maintenance")
	return _("{0} on vehicle {1}, serviced {2} at odometer {3}. Bill {4}.").format(
		detail, doc.get("vehicle") or "-", doc.get("completion_date") or "-",
		doc.get("odometer") or "-", doc.get("bill_no") or "-",
	)


def _approver_role():
	return get_setting("maintenance_approver_role") or get_setting("purchase_order_notify_role")


def _may_approve() -> bool:
	role = _approver_role()
	roles = set(frappe.get_roles())
	if "System Manager" in roles or "Fleet Administrator" in roles:
		return True
	return bool(role) and role in roles


@frappe.whitelist()
def submit_bill(maintenance_log: str):
	"""The driver hands in the service centre's bill."""
	frappe.has_permission(MAINTENANCE_DOCTYPE, "write", throw=True)
	doc = frappe.get_doc(MAINTENANCE_DOCTYPE, maintenance_log)

	if doc.get("bill_status") in (BILL_APPROVED, BILL_PAID):
		frappe.throw(_("This bill has already been approved."), title=_("Already Approved"))

	missing = bill_is_complete(doc)
	if missing:
		frappe.throw(
			_("The bill cannot be submitted yet. Still needed: {0}.").format(", ".join(missing)),
			title=_("Bill Incomplete"),
		)

	clash = duplicate_bill(doc.get("service_provider"), doc.get("bill_no"))
	if clash:
		frappe.throw(
			_("Bill {0} from {1} is already on Purchase Invoice {2}.").format(
				frappe.bold(doc.bill_no), frappe.bold(doc.service_provider), frappe.bold(clash)),
			title=_("Duplicate Bill"),
		)

	frappe.db.set_value(MAINTENANCE_DOCTYPE, maintenance_log, {
		"bill_status": BILL_PENDING_APPROVAL,
		"submitted_by": frappe.session.user,
		"submission_date": now_datetime(),
		"rejection_reason": None,
	}, update_modified=False)

	notify(
		_("Service bill awaiting approval: {0}").format(maintenance_log),
		_("{0} submitted bill {1} from {2} for {3}, amount {4}.").format(
			frappe.session.user, doc.bill_no, doc.service_provider,
			doc.vehicle or "-", flt(doc.total_cost)),
		MAINTENANCE_DOCTYPE, maintenance_log,
	)
	return BILL_PENDING_APPROVAL


@frappe.whitelist()
def approve_bill(maintenance_log: str):
	"""The company approves the bill, and the purchasing document follows."""
	frappe.has_permission(MAINTENANCE_DOCTYPE, "write", throw=True)
	if not _may_approve():
		frappe.throw(
			_("You are not allowed to approve service bills. The approver role is {0}.")
			.format(frappe.bold(_approver_role() or _("not configured"))),
			frappe.PermissionError, title=_("Not an Approver"),
		)

	doc = frappe.get_doc(MAINTENANCE_DOCTYPE, maintenance_log)
	if doc.get("bill_status") not in (BILL_SUBMITTED, BILL_PENDING_APPROVAL):
		frappe.throw(
			_("Only a submitted bill can be approved. This one is {0}.")
			.format(frappe.bold(doc.get("bill_status") or BILL_DRAFT)),
			title=_("Not Awaiting Approval"),
		)

	missing = bill_is_complete(doc)
	if missing:
		frappe.throw(
			_("The bill is incomplete and cannot be approved. Still needed: {0}.")
			.format(", ".join(missing)), title=_("Bill Incomplete"))

	frappe.db.set_value(MAINTENANCE_DOCTYPE, maintenance_log, {
		"bill_status": BILL_APPROVED,
		"approved_by": frappe.session.user,
	}, update_modified=False)

	doc.reload()
	raise_maintenance_purchase(doc)
	sync_payment_status(maintenance_log)
	return frappe.db.get_value(
		MAINTENANCE_DOCTYPE, maintenance_log,
		["bill_status", "purchasing_status", "purchase_order", "purchase_invoice",
		 "payment_status", "purchasing_message"], as_dict=True)


@frappe.whitelist()
def reject_bill(maintenance_log: str, reason: str):
	"""Send the bill back to the driver to correct and resubmit."""
	frappe.has_permission(MAINTENANCE_DOCTYPE, "write", throw=True)
	if not _may_approve():
		frappe.throw(_("You are not allowed to reject service bills."),
		             frappe.PermissionError, title=_("Not an Approver"))
	if not (reason or "").strip():
		frappe.throw(_("Give a reason so the driver knows what to correct."),
		             title=_("Reason Required"))

	frappe.db.set_value(MAINTENANCE_DOCTYPE, maintenance_log, {
		"bill_status": BILL_REJECTED,
		"rejection_reason": reason,
		"approved_by": frappe.session.user,
	}, update_modified=False)
	notify(
		_("Service bill rejected: {0}").format(maintenance_log),
		reason, MAINTENANCE_DOCTYPE, maintenance_log,
	)
	return BILL_REJECTED


def raise_maintenance_purchase(doc):
	"""Create the purchasing document for an approved bill."""
	if not int(get_setting("maintenance_po_on_completion", 0) or 0):
		record_outcome(
			MAINTENANCE_DOCTYPE, doc.name, NOT_REQUIRED,
			_("Bill approved. Purchasing automation is switched off, so no "
			  "document was raised - record it in Accounts directly."),
		)
		return None

	company = get_purchasing_company(doc)
	item = get_setting("maintenance_service_item")
	description = maintenance_description(doc)
	amount = flt(doc.get("total_cost"))

	purchase_order = None
	if get_setting("maintenance_purchase_document") == "Purchase Order then Invoice":
		purchase_order = create_purchase_order(
			source_doctype=MAINTENANCE_DOCTYPE, source_name=doc.name,
			supplier=doc.get("service_provider"), item_code=item, rate=amount,
			description=description, schedule_date=doc.get("completion_date"),
			company=company, cost_center=doc.get("cost_center"), project=doc.get("project"),
		)
		if not purchase_order:
			return None

	return create_purchase_invoice(
		source_doctype=MAINTENANCE_DOCTYPE, source_name=doc.name,
		supplier=doc.get("service_provider"), item_code=item, rate=amount,
		description=description, bill_no=doc.get("bill_no"), bill_date=doc.get("bill_date"),
		company=company, cost_center=doc.get("cost_center"), project=doc.get("project"),
		purchase_order=purchase_order,
	)


def sync_payment_status(maintenance_log: str):
	"""Read the payment state back from the invoice."""
	invoice = frappe.db.get_value(MAINTENANCE_DOCTYPE, maintenance_log, "purchase_invoice")
	status = get_payment_status(invoice)
	values = {"payment_status": status}
	if status == "Paid":
		values["bill_status"] = BILL_PAID
	frappe.db.set_value(MAINTENANCE_DOCTYPE, maintenance_log, values, update_modified=False)
	return status


def process_maintenance_completion(doc, method=None):
	"""Attached to the maintenance hooks.

	Completion no longer raises anything. It only moves a record that is still
	a draft to Service Completed, so the driver can see the bill is now due.
	"""
	if not frappe.db.has_column(MAINTENANCE_DOCTYPE, "bill_status"):
		return
	if doc.get("maintenance_status") != "Completed":
		return
	if doc.get("bill_status") in (None, "", BILL_DRAFT):
		frappe.db.set_value(MAINTENANCE_DOCTYPE, doc.name,
		                    "bill_status", BILL_SERVICE_COMPLETED, update_modified=False)


def on_purchase_invoice_change(invoice_doc, method=None):
	"""Keep the maintenance record's payment status true to the accounts."""
	refresh_payment_status_for_invoice(invoice_doc.name)


def refresh_payment_status_for_invoice(invoice: str):
	if not frappe.db.has_column(MAINTENANCE_DOCTYPE, "purchase_invoice"):
		return
	for name in frappe.get_all(MAINTENANCE_DOCTYPE,
	                           filters={"purchase_invoice": invoice}, pluck="name"):
		sync_payment_status(name)


def on_payment_entry_change(payment_doc, method=None):
	"""A payment changes an invoice's outstanding, so the status moves with it."""
	for row in (payment_doc.get("references") or []):
		if row.reference_doctype == "Purchase Invoice" and row.reference_name:
			refresh_payment_status_for_invoice(row.reference_name)


@frappe.whitelist()
def retry_maintenance_purchase(maintenance_log: str):
	"""Retry after the missing supplier or item has been supplied."""
	frappe.has_permission(MAINTENANCE_DOCTYPE, "write", throw=True)
	doc = frappe.get_doc(MAINTENANCE_DOCTYPE, maintenance_log)
	if doc.get("bill_status") != BILL_APPROVED:
		frappe.throw(_("Only an approved bill can be purchased. This one is {0}.")
		             .format(frappe.bold(doc.get("bill_status") or BILL_DRAFT)))
	raise_maintenance_purchase(doc)
	sync_payment_status(maintenance_log)
	return frappe.db.get_value(
		MAINTENANCE_DOCTYPE, maintenance_log,
		["purchasing_status", "purchase_order", "purchase_invoice", "payment_status",
		 "purchasing_message"], as_dict=True)


# ---------------------------------------------------------------------------
# CR4 - insurance renewal
# ---------------------------------------------------------------------------
def renewal_is_eligible(row) -> bool:
	"""An insurance policy that has reached its trigger date and is still live."""
	if row.get("renewal_type") != "Insurance":
		return False
	if row.get("renewal_status") in ("Renewed", "Cancelled"):
		return False
	if row.get("docstatus") != 1:
		return False
	return True


def get_renewals_due_for_purchase(on_date=None) -> list[dict]:
	"""Insurance policies at or past the configured trigger point.

	Superseded policies are excluded: if a later renewal already chains to this
	one, the cover has been replaced and buying it again would be wrong.
	"""
	on_date = getdate(on_date or nowdate())
	lead_days = int(get_setting("insurance_renewal_lead_days", 0) or 0)
	trigger_on_or_before = add_days(on_date, lead_days)

	rows = frappe.get_all(
		RENEWAL_DOCTYPE,
		filters={
			"renewal_type": "Insurance",
			"docstatus": 1,
			"expiry_date": ("<=", trigger_on_or_before),
			"renewal_status": ("not in", ["Renewed", "Cancelled"]),
		},
		# Renewal Register carries no cost centre or project of its own; the
		# vehicle supplies them when a purchase order needs a dimension.
		fields=["name", "vehicle", "supplier", "provider", "premium", "expiry_date",
		        "renewal_status", "certificate_no",
		        "purchase_order", "purchasing_status", "docstatus"],
	)

	due = []
	for row in rows:
		if frappe.db.exists(RENEWAL_DOCTYPE,
		                    {"previous_renewal": row.name, "docstatus": ("<", 2)}):
			continue
		if has_live_order(RENEWAL_DOCTYPE, row.name):
			continue
		due.append(row)
	return due


def _vehicle_dimension(vehicle, fieldname):
	"""Cost centre / project for a renewal come from the vehicle it covers."""
	if not vehicle:
		return None
	return frappe.db.get_value("Vehicle", vehicle, fieldname)


def process_insurance_renewal(row) -> str | None:
	premium = flt(row.get("premium"))
	supplier = row.get("supplier") or get_setting("insurance_supplier")

	if premium <= 0:
		record_outcome(
			RENEWAL_DOCTYPE, row["name"], PENDING,
			_("No premium recorded on the policy, so there is no amount to order. "
			  "Enter the renewal premium and retry."),
		)
		return None

	return create_purchase_order(
		source_doctype=RENEWAL_DOCTYPE,
		source_name=row["name"],
		supplier=supplier,
		item_code=get_setting("insurance_service_item"),
		rate=premium,
		description=_("Insurance renewal for vehicle {0}, policy {1} expiring {2}").format(
			row.get("vehicle") or "-", row.get("certificate_no") or "-",
			row.get("expiry_date") or "-",
		),
		schedule_date=row.get("expiry_date") or nowdate(),
		company=get_purchasing_company(frappe._dict(vehicle=row.get("vehicle"))),
		cost_center=_vehicle_dimension(row.get("vehicle"), "cost_center"),
		project=_vehicle_dimension(row.get("vehicle"), "project"),
	)


def raise_insurance_renewal_orders(on_date=None) -> dict:
	"""Daily sweep for expired insurance.

	A scheduled job, not a form hook: nobody may open the record on the day it
	expires, so nothing would fire. Safe to run repeatedly - each record is
	skipped once it already has a live order.
	"""
	if not int(get_setting("insurance_po_on_expiry", 0) or 0):
		return {"enabled": False, "ordered": [], "pending": []}

	ordered, pending = [], []
	for row in get_renewals_due_for_purchase(on_date):
		result = process_insurance_renewal(row)
		(ordered if result else pending).append(row["name"])

	return {"enabled": True, "ordered": ordered, "pending": pending}


def daily_fleet_purchasing():
	"""Scheduler entry point."""
	try:
		raise_insurance_renewal_orders()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Daily fleet purchasing sweep failed")


@frappe.whitelist()
def retry_renewal_purchase(renewal: str):
	frappe.has_permission(RENEWAL_DOCTYPE, "write", throw=True)
	row = frappe.db.get_value(
		RENEWAL_DOCTYPE, renewal,
		["name", "vehicle", "supplier", "premium", "expiry_date", "certificate_no",
		 "renewal_type", "renewal_status", "docstatus"],
		as_dict=True,
	)
	if not renewal_is_eligible(row):
		frappe.throw(_("{0} is {1} and does not need a renewal order.").format(
			frappe.bold(renewal), frappe.bold(row.get("renewal_status") or "")))
	process_insurance_renewal(row)
	return frappe.db.get_value(RENEWAL_DOCTYPE, renewal,
	                           ["purchasing_status", "purchase_order", "purchasing_message"],
	                           as_dict=True)
