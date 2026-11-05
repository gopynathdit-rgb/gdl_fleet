// Copyright (c) 2026, GDL and contributors

frappe.query_reports["Tyre Mileage Report"] = {
	filters: [
		{"fieldname": "from_date", "label": __("Fitted From"), "fieldtype": "Date",
		 "default": frappe.datetime.add_months(frappe.datetime.get_today(), -12)},
		{"fieldname": "to_date", "label": __("Fitted To"), "fieldtype": "Date",
		 "default": frappe.datetime.get_today()},
		{"fieldname": "vehicle", "label": __("Vehicle"), "fieldtype": "Link", "options": "Vehicle"},
		{"fieldname": "status", "label": __("Status"), "fieldtype": "Select",
		 "options": ["", "Fitted", "Removed", "Scrapped"]},
		{"fieldname": "outside_tolerance_only", "label": __("Outside Tolerance Only"), "fieldtype": "Check"}
	],
};
