// Copyright (c) 2026, GDL and contributors

frappe.ui.form.on("Movement Order", {
	setup(frm) {
		// Only drivers free over this order's window. GDL: "if the Driver is
		// Assigned to another vehicle at the same time, it shouldnt show in
		// the Driver selection."
		//
		// The times go with the query, so the list narrows as soon as they
		// are set and widens again if they move. The server applies the same
		// rule on save - a filtered list is a convenience, not the guard.
		frm.set_query("driver", () => ({
			query: "gdl_fleet_extension.gdl_fleet.doctype.movement_order.movement_order.driver_query",
			filters: {
				departure_datetime: frm.doc.departure_datetime,
				expected_return: frm.doc.expected_return,
				name: frm.doc.name,
			},
		}));
	},

	movement_order_request(frm) {
		// Selecting the request fills in everything already captured on it, so
		// the same information is not keyed twice. Vehicle and driver are left
		// alone: an authorised allocation on the order must not be undone by
		// re-selecting the request.
		if (!frm.doc.movement_order_request) return;

		frappe.call({
			method: "gdl_fleet_extension.gdl_fleet.doctype.movement_order.movement_order.fetch_request_details",
			args: { movement_order_request: frm.doc.movement_order_request },
			callback(r) {
				if (!r.message) return;
				Object.entries(r.message).forEach(([field, value]) => {
					const docfield = frm.fields_dict[field];
					if (!value || !docfield) return;
					if (docfield.df.fieldtype === "Table") {
						// set_value does not reliably replace grid rows, so the
						// table is cleared and rebuilt row by row.
						frm.clear_table(field);
						value.forEach((row) => frm.add_child(field, row));
						frm.refresh_field(field);
					} else {
						frm.set_value(field, value);
					}
				});
				frappe.show_alert({
					message: __("Details carried over from {0}.", [frm.doc.movement_order_request]),
					indicator: "green",
				});
			},
			error() {
				// validate_request_is_usable already explained why; clear the
				// link so the order is not left pointing at a request it may
				// not use.
				frm.set_value("movement_order_request", null);
			},
		});
	},

	driver(frm) {
		if (!frm.doc.driver) return;
		frappe.db.get_value("Driver", frm.doc.driver, "employee").then((r) => {
			if (r && r.message && !r.message.employee) {
				frappe.show_alert({
					message: __("Driver {0} has no Employee on their Driver record.",
						[frm.doc.driver]),
					indicator: "orange",
				});
			}
		});
	},
});
