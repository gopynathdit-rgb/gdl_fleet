// Copyright (c) 2026, GDL and contributors

frappe.listview_settings["Movement Order Request"] = {
	add_fields: ["status", "priority", "vehicle", "required_date"],
	get_indicator(doc) {
		const map = {
			Draft: "grey",
			"Pending Validation": "orange",
			"Pending Review": "orange",
			"Pending MTO/CEO": "orange",
			"Pending FAS": "orange",
			Approved: "blue",
			Assigned: "purple",
			"In Use": "yellow",
			Completed: "green",
			Rejected: "red",
			Cancelled: "dark grey",
		};
		return [__(doc.status), map[doc.status] || "grey", "status,=," + doc.status];
	},
};
