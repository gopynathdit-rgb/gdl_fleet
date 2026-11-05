// Copyright (c) 2026, GDL and contributors

frappe.query_reports["Tyre Cost Analysis"] = {
	filters: [
		{"fieldname": "from_date", "label": __("Fitted From"), "fieldtype": "Date",
		 "default": frappe.datetime.add_months(frappe.datetime.get_today(), -12)},
		{"fieldname": "to_date", "label": __("Fitted To"), "fieldtype": "Date",
		 "default": frappe.datetime.get_today()},
		{"fieldname": "group_by", "label": __("Group By"), "fieldtype": "Select",
		 "options": ["Vehicle", "Tyre Item", "Site", "Removal Reason"], "default": "Vehicle"},
		{"fieldname": "vehicle", "label": __("Vehicle"), "fieldtype": "Link", "options": "Vehicle"},
		{"fieldname": "site", "label": __("Site"), "fieldtype": "Link", "options": "Location"},
		{"fieldname": "status", "label": __("Status"), "fieldtype": "Select",
		 "options": ["", "Fitted", "Removed", "Scrapped"]},
		{"fieldname": "include_in_service", "label": __("Include Tyres Still Fitted"),
		 "fieldtype": "Check", "default": 1}
	],
};
