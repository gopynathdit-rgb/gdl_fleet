// Copyright (c) 2026, GDL and contributors
//
// A service is recorded, submitted, and then billed - in one step, by someone
// pressing a button.
//
// This used to drive a four-stage chain: Submit Bill, Approve Bill, Reject
// Bill, Retry Purchasing. GDL switched that off; the buttons are gone with it,
// rather than left on screen acting on a bill_status nothing maintains.

frappe.ui.form.on("Asset Maintenance Log", {
	onload(frm) {
		// A driver writes this down AFTER the vehicle has been serviced, so
		// the work is done before the form is opened. ERPNext starts at
		// "Planned", which then refuses to submit ("Maintenance Status has to
		// be Cancelled or Completed to Submit") and sends the driver hunting
		// for a field to change.
		//
		// Set here and not as a DocType default on purpose: a default reaches
		// Asset Maintenance's sync_maintenance_tasks() too, which creates a
		// log for every SCHEDULED task - and a scheduled service that starts
		// at Completed is then refused for having no completion date.
		if (frm.is_new() && !frm.doc.asset_maintenance && !frm.doc.task) {
			frm.set_value("maintenance_status", "Completed");
		}
	},

	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.docstatus !== 1) return;
		if (frm.doc.maintenance_status !== "Completed") return;

		// Asked of the invoice side, not read off this record. The service
		// stores no link to its invoice: a stored Link makes frappe refuse to
		// cancel the invoice, and cancelling a wrong invoice is how Accounts
		// fix one. A cancelled invoice is not returned, so the service can be
		// billed again.
		frappe.call({
			method: "gdl_fleet_extension.utils.fleet_purchase_automation.get_maintenance_invoice",
			args: { maintenance_log: frm.doc.name },
		}).then((r) => {
			const invoice = r.message;

			if (invoice) {
				// Already billed: no second Create, whoever is looking.
				frm.dashboard.set_headline(__("Invoiced on {0}.", [invoice]));
				// Only for someone who can open a Purchase Invoice. A driver
				// cannot, and a link that errors is worse than no link.
				if (frappe.model.can_read("Purchase Invoice")) {
					frm.add_custom_button(__("View Purchase Invoice"), () =>
						frappe.set_route("Form", "Purchase Invoice", invoice)
					);
				}
				return;
			}

			// Not billed yet, and only for someone who may raise one.
			if (!frappe.model.can_create("Purchase Invoice")) return;
			frm.add_custom_button(__("Purchase Invoice"), () => make_invoice(frm), __("Create"));
			frm.page.set_inner_btn_group_as_primary(__("Create"));
		});
	},
});

function make_invoice(frm) {
	frappe.call({
		method: "gdl_fleet_extension.utils.fleet_purchase_automation.make_maintenance_invoice",
		args: { maintenance_log: frm.doc.name },
		freeze: true,
		freeze_message: __("Raising the purchase invoice..."),
		callback(r) {
			if (!r.message) return;
			frappe.show_alert({
				message: __("Purchase Invoice {0} created as a draft.", [r.message]),
				indicator: "green",
			});
			frappe.set_route("Form", "Purchase Invoice", r.message);
		},
	});
}
