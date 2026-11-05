// Copyright (c) 2026, GDL and contributors

frappe.query_reports["Mileage Deviation Dashboard"] = {
	filters: [
		{"fieldname": "from_date", "label": __("From Date"), "fieldtype": "Date",
		 "default": frappe.datetime.add_months(frappe.datetime.get_today(), -3)},
		{"fieldname": "to_date", "label": __("To Date"), "fieldtype": "Date",
		 "default": frappe.datetime.get_today()},
		{"fieldname": "vehicle", "label": __("Vehicle"), "fieldtype": "Link", "options": "Vehicle"},
		{"fieldname": "site", "label": __("Office / Site"), "fieldtype": "Link", "options": "Location"},
		{"fieldname": "deviation_only", "label": __("Outside Tolerance Only"), "fieldtype": "Check"}
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data && data.indicator) {
			const colour = {red: "#c0392b", orange: "#b9770e", green: "#1e8449", grey: "#7b7d7d"}[data.indicator];
			value = `<span style="color:${colour};font-weight:500">${value}</span>`;
		}
		return value;
	},
};
