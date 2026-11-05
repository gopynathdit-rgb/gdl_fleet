// Copyright (c) 2026, GDL and contributors

frappe.query_reports["Parts Consumption"] = {
	filters: [
		{"fieldname": "from_date", "label": __("From Date"), "fieldtype": "Date",
		 "default": frappe.datetime.add_months(frappe.datetime.get_today(), -3), "reqd": 1},
		{"fieldname": "to_date", "label": __("To Date"), "fieldtype": "Date",
		 "default": frappe.datetime.get_today(), "reqd": 1},
		{"fieldname": "group_by", "label": __("Group By"), "fieldtype": "Select",
		 "options": ["Item", "Vehicle", "Site", "Purpose", "Detail"], "default": "Item"},
		{"fieldname": "vehicle", "label": __("Vehicle"), "fieldtype": "Link", "options": "Vehicle"},
		{"fieldname": "item_code", "label": __("Item"), "fieldtype": "Link", "options": "Item"},
		{"fieldname": "site", "label": __("Site"), "fieldtype": "Link", "options": "Location"},
		{"fieldname": "purpose", "label": __("Purpose"), "fieldtype": "Select",
		 "options": ["", "Routine Replacement", "Breakdown", "Accident", "Wear and Tear", "Other"]},
		{"fieldname": "tyres_only", "label": __("Tyres Only"), "fieldtype": "Check"},
		{"fieldname": "exclude_tyres", "label": __("Exclude Tyres"), "fieldtype": "Check"}
	],
};
