// Copyright (c) 2026, GDL and contributors

frappe.query_reports["Fleet Register"] = {
	filters: [
	{"fieldname": "from_date", "label": __("From Date"), "fieldtype": "Date",
	 "default": frappe.datetime.month_start()},
	{"fieldname": "to_date", "label": __("To Date"), "fieldtype": "Date",
	 "default": frappe.datetime.get_today()},
	{"fieldname": "vehicle", "label": __("Vehicle"), "fieldtype": "Link", "options": "Vehicle"},
	{"fieldname": "site", "label": __("Site"), "fieldtype": "Link", "options": "Location"},
	{"fieldname": "department", "label": __("Department"), "fieldtype": "Link", "options": "Department"},
	{"fieldname": "driver", "label": __("Driver"), "fieldtype": "Link", "options": "Driver"}
],
};
