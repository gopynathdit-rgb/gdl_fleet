// Copyright (c) 2026, GDL and contributors

frappe.query_reports["POL Supplier and Book Balance"] = {
	filters: [
		{"fieldname": "from_date", "label": __("From Date"), "fieldtype": "Date",
		 "default": frappe.datetime.add_months(frappe.datetime.get_today(), -3)},
		{"fieldname": "to_date", "label": __("To Date"), "fieldtype": "Date",
		 "default": frappe.datetime.get_today()},
		{"fieldname": "vehicle", "label": __("Vehicle"), "fieldtype": "Link", "options": "Vehicle"},
		{"fieldname": "supplier", "label": __("Supplier"), "fieldtype": "Link", "options": "Supplier"},
		{"fieldname": "site", "label": __("Site"), "fieldtype": "Link", "options": "Location"},
		{"fieldname": "status", "label": __("Status"), "fieldtype": "Select",
		 "options": ["", "Draft", "Submitted", "Approved", "Rejected", "Cancelled"]}
	],
};
