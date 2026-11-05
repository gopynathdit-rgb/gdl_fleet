import frappe
from frappe import _
from frappe.utils import cint


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "name", "label": _("Renewal"), "fieldtype": "Link", "options": "Renewal Register", "width": 150},
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 130},
		{"fieldname": "renewal_type", "label": _("Type"), "fieldtype": "Data", "width": 120},
		{"fieldname": "certificate_no", "label": _("Certificate No."), "fieldtype": "Data", "width": 150},
		{"fieldname": "provider", "label": _("Provider / Authority"), "fieldtype": "Data", "width": 190},
		{"fieldname": "effective_from", "label": _("From"), "fieldtype": "Date", "width": 100},
		{"fieldname": "expiry_date", "label": _("Expiry"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_to_expiry", "label": _("Days to Expiry"), "fieldtype": "Int", "width": 120},
		{"fieldname": "premium", "label": _("Premium / Fee"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "renewal_status", "label": _("Status"), "fieldtype": "Data", "width": 110},
	]

	conditions = {"docstatus": ("<", 2)}
	if filters.get("vehicle"):
		conditions["vehicle"] = filters.vehicle
	if filters.get("renewal_type"):
		conditions["renewal_type"] = filters.renewal_type
	if not filters.get("include_renewed"):
		conditions["renewal_status"] = ("!=", "Renewed")

	data = frappe.get_all(
		"Renewal Register", filters=conditions,
		fields=["name", "vehicle", "renewal_type", "certificate_no", "provider",
		        "effective_from", "expiry_date", "days_to_expiry", "premium",
		        "renewal_status"],
		order_by="expiry_date asc",
	)
	message = _(
		"Section 5 asks for 30/15/7-day due and expired renewals. The reminder "
		"ladder is configured in GDL Fleet Settings, so this list follows whatever "
		"thresholds GDL has set."
	)
	return columns, data, message
