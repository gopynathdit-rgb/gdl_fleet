import frappe
from frappe import _

from gdl_fleet_extension.utils.cost import get_vehicle_cost


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"fieldname": "vehicle", "label": _("Vehicle"), "fieldtype": "Link", "options": "Vehicle", "width": 130},
		{"fieldname": "gdl_vehicle_id", "label": _("Vehicle ID"), "fieldtype": "Data", "width": 120},
		{"fieldname": "site", "label": _("Site"), "fieldtype": "Link", "options": "Location", "width": 120},
		{"fieldname": "expense_claim", "label": _("Expense Claims"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "purchase_invoice", "label": _("Purchase Invoices"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "stock_entry", "label": _("Stock Issues"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "asset_repair", "label": _("Repairs"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "journal_entry", "label": _("Journal"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "total_cost", "label": _("Total Cost"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "distance_km", "label": _("Distance KM"), "fieldtype": "Int", "width": 110},
		{"fieldname": "cost_per_km", "label": _("Cost / KM"), "fieldtype": "Currency", "width": 120},
	]
	data = get_vehicle_cost(
		filters.get("from_date"), filters.get("to_date"), vehicle=filters.get("vehicle"),
		site=filters.get("site"), cost_center=filters.get("cost_center"),
		project=filters.get("project"),
	)
	message = _(
		"Every figure is read from the standard General Ledger using the Vehicle "
		"accounting dimension. Only debits to expense accounts on submitted, "
		"uncancelled vouchers are counted, so nothing is double counted. "
		"Depreciation is excluded unless the entry is tagged with the vehicle."
	)
	return columns, data, message
