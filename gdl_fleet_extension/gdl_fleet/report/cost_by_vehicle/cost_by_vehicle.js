// Copyright (c) 2026, GDL and contributors

frappe.query_reports["Cost by Vehicle"] = {
	filters: [
	{"fieldname": "from_date", "label": __("From Date"), "fieldtype": "Date",
	 "default": frappe.datetime.month_start(), "reqd": 1},
	{"fieldname": "to_date", "label": __("To Date"), "fieldtype": "Date",
	 "default": frappe.datetime.get_today(), "reqd": 1},
	{"fieldname": "vehicle", "label": __("Vehicle"), "fieldtype": "Link", "options": "Vehicle"},
	{"fieldname": "site", "label": __("Site"), "fieldtype": "Link", "options": "Location"},
	{"fieldname": "department", "label": __("Department"), "fieldtype": "Link", "options": "Department"},
	{"fieldname": "driver", "label": __("Driver"), "fieldtype": "Link", "options": "Driver"},
	{"fieldname": "project", "label": __("Project"), "fieldtype": "Link", "options": "Project"},
	{"fieldname": "cost_center", "label": __("Cost Center"), "fieldtype": "Link", "options": "Cost Center"}
],
};
