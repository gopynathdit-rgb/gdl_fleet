// Copyright (c) 2026, GDL and contributors

frappe.query_reports["Part Replacement History"] = {
	filters: [
		{"fieldname": "from_date", "label": __("From Date"), "fieldtype": "Date",
		 "default": frappe.datetime.add_months(frappe.datetime.get_today(), -24)},
		{"fieldname": "to_date", "label": __("To Date"), "fieldtype": "Date",
		 "default": frappe.datetime.get_today()},
		{"fieldname": "vehicle", "label": __("Vehicle"), "fieldtype": "Link", "options": "Vehicle"},
		{"fieldname": "item_code", "label": __("Item"), "fieldtype": "Link", "options": "Item"},
		{"fieldname": "site", "label": __("Site"), "fieldtype": "Link", "options": "Location"},
		{"fieldname": "repeated_only", "label": __("Repeatedly Replaced Only"),
		 "fieldtype": "Check", "default": 1},
		{"fieldname": "replaced_within_km", "label": __("Replaced Within (KM)"), "fieldtype": "Int",
		 "description": __("Show only parts that came back sooner than this many kilometres.")},
		{"fieldname": "tyres_only", "label": __("Tyres Only"), "fieldtype": "Check"},
		{"fieldname": "exclude_tyres", "label": __("Exclude Tyres"), "fieldtype": "Check"}
	],
};
