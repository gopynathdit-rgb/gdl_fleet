// Copyright (c) 2026, GDL and contributors

frappe.ui.form.on("Movement Order Request", {
	setup(frm) {
		frm.set_query("employee", () => ({ filters: { status: "Active" } }));
		frm.set_query("driver", () => ({ filters: { status: "Active" } }));
		// Sites are leaf Locations only - groups exist for reporting roll-up.
		frm.set_query("site", () => ({ filters: { is_group: 0 } }));
		// Offer only what can actually be taken: free for THIS window, and at a
		// location this user draws on. The old filter tested vehicle_status
		// alone, so a vehicle already booked was offered and the clash only
		// surfaced when the save was refused.
		frm.set_query("vehicle", () => ({
			query:
				"gdl_fleet_extension.gdl_fleet.doctype.movement_order_request.movement_order_request.assignable_vehicle_query",
			filters: {
				from_datetime: frm.doc.from_datetime,
				to_datetime: frm.doc.to_datetime,
				vehicle_type: frm.doc.vehicle_type,
				exclude: frm.doc.name,
			},
		}));
	},

	refresh(frm) {
		frm.toggle_display("check_availability", !frm.doc.__islocal);
		show_movement_order(frm);
	},

	check_availability(frm) {
		if (!frm.doc.from_datetime || !frm.doc.to_datetime) {
			frappe.msgprint(__("Enter the required date and times first, then save."));
			return;
		}

		frappe.call({
			method:
				"gdl_fleet_extension.gdl_fleet.doctype.movement_order_request.movement_order_request.get_available_vehicles",
			args: {
				from_datetime: frm.doc.from_datetime,
				to_datetime: frm.doc.to_datetime,
				vehicle_type: frm.doc.vehicle_type,
				exclude: frm.doc.name,
			},
			callback(r) {
				const rows = r.message || [];
				if (!rows.length) {
					frappe.msgprint({
						title: __("No Vehicles Available"),
						message: __(
							"No {0} is free between {1} and {2}.",
							[
								frm.doc.vehicle_type || __("vehicle"),
								frappe.datetime.str_to_user(frm.doc.from_datetime),
								frappe.datetime.str_to_user(frm.doc.to_datetime),
							]
						),
						indicator: "orange",
					});
					return;
				}

				// Reading a registration off a list and typing it into the
				// field below is work the screen can do. Each row assigns.
				const body = rows
					.map(
						(v) =>
							`<tr data-vehicle="${frappe.utils.escape_html(v.name)}" style="cursor:pointer">
							 <td>${frappe.utils.escape_html(v.gdl_vehicle_id || "")}</td>
							 <td>${frappe.utils.escape_html(v.name)}</td>
							 <td>${frappe.utils.escape_html(v.vehicle_type || "")}</td>
							 <td>${frappe.utils.escape_html([v.make, v.model].filter(Boolean).join(" "))}</td>
							 <td>${frappe.utils.escape_html(v.site || "")}</td>
							 <td><button class="btn btn-xs btn-default">${__("Assign")}</button></td></tr>`
					)
					.join("");

				const dialog = frappe.msgprint({
					title: __("Available Vehicles"),
					message: `<p class="text-muted">${__("Click a row to assign it.")}</p>
						<table class="table table-bordered gdl-available-vehicles">
						<thead><tr>
							<th>${__("Vehicle ID")}</th><th>${__("Registration")}</th>
							<th>${__("Type")}</th><th>${__("Make / Model")}</th><th>${__("Site")}</th>
							<th></th>
						</tr></thead><tbody>${body}</tbody></table>`,
						indicator: "green",
				});

				dialog.$wrapper.on("click", "tr[data-vehicle]", function () {
					frm.set_value("vehicle", $(this).attr("data-vehicle"));
					dialog.hide();
					frappe.show_alert({
						message: __("Assigned {0}. Save the request to hold it.",
							[$(this).attr("data-vehicle")]),
						indicator: "green",
					});
				});
			},
		});
	},

	required_date(frm) {
		if (frm.doc.required_date && !frm.doc.return_date) {
			frm.set_value("return_date", frm.doc.required_date);
		}
	},
});

function show_movement_order(frm) {
	// The MTO accepts the request and then raises the order from it. Until now
	// that meant leaving this page, opening a blank Movement Order and typing
	// the request's number back in. The server has always been able to build
	// the order from the request; nothing on the form ever asked it to.
	if (frm.doc.__islocal) return;

	// Only an accepted request may become an order - the server refuses
	// anything else, and a button that always throws is worse than no button.
	if (frm.doc.workflow_state !== "Accepted") return;

	// A requester has no business raising the order, and the lookup below
	// would fail for them anyway.
	if (!frappe.model.can_create("Movement Order")) return;

	frappe.db
		.get_value("Movement Order", {
			movement_order_request: frm.doc.name,
			docstatus: ["<", 2],
		}, "name")
		.then((r) => {
			const existing = r.message && r.message.name;

			// One order per request. If there is one, offer the way to it
			// rather than a second Create that the server would refuse.
			if (existing) {
				frm.add_custom_button(existing, () =>
					frappe.set_route("Form", "Movement Order", existing)
				, __("Movement Order"));
				return;
			}

			frm.add_custom_button(__("Movement Order"), () =>
				frappe.model.open_mapped_doc({
					method:
						"gdl_fleet_extension.gdl_fleet.doctype.movement_order.movement_order.make_movement_order",
					frm,
				})
			, __("Create"));
			frm.page.set_inner_btn_group_as_primary(__("Create"));
		});
}
