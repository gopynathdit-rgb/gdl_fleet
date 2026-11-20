// Copyright (c) 2026, GDL and contributors
//
// Two things GDL asked for on a new Vehicle Log:
// "Driver is not showing and in Employee, it should show all employee".

frappe.ui.form.on("Vehicle Log", {
	setup(frm) {
		// HRMS sets this query in its own vehicle_log.js:
		//
		//     frm.set_query("employee", () => ({ filters: { status: "Active" } }))
		//
		// which is why the list said 'Filtered by: Status equals "Active"'.
		// GDL want every employee - a journey can belong to somebody who has
		// since left, and the log is a record of what happened. Ours runs
		// after theirs, so this replaces it.
		frm.set_query("employee", () => ({}));
	},

	vehicle(frm) {
		// The server already fills the driver on save, from the assignment
		// live on the log's date. Doing it here too means the driver appears
		// as soon as the vehicle is chosen, instead of the field looking
		// broken until somebody saves.
		if (!frm.doc.vehicle || frm.doc.driver) return;

		const vehicle = frm.doc.vehicle;
		frappe.call({
			method: "gdl_fleet_extension.gdl_fleet.doctype.driver_assignment.driver_assignment.get_active_driver",
			args: { vehicle, on_date: frm.doc.date || frappe.datetime.get_today() },
		}).then((r) => {
			// A slow reply must not land on a form that has moved on.
			if (frm.doc.vehicle !== vehicle || frm.doc.driver) return;
			if (r.message) frm.set_value("driver", r.message);
		});
	},
});
