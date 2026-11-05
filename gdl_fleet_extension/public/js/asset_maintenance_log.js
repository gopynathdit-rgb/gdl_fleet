// Copyright (c) 2026, GDL and contributors
// External maintenance: the driver brings back the service centre's bill, the
// company approves it, and only then is a purchasing document raised.

frappe.ui.form.on("Asset Maintenance Log", {
	refresh(frm) {
		if (frm.is_new()) return;
		const status = frm.doc.bill_status;

		if (["Service Completed", "Draft", "Rejected"].includes(status || "Draft")) {
			frm.add_custom_button(__("Submit Bill"), () => call(frm, "submit_bill",
				__("Submitting the service centre's bill...")), __("Service Bill"));
		}

		if (["Bill Submitted", "Pending Approval"].includes(status)) {
			frm.add_custom_button(__("Approve Bill"), () => call(frm, "approve_bill",
				__("Approving...")), __("Service Bill"));
			frm.add_custom_button(__("Reject Bill"), () => reject(frm), __("Service Bill"));
		}

		if (frm.doc.purchasing_status === "Pending" && status === "Approved") {
			frm.add_custom_button(__("Retry Purchasing"), () => call(frm,
				"retry_maintenance_purchase", __("Retrying...")), __("Service Bill"));
		}

		if (frm.doc.purchase_invoice) {
			frm.add_custom_button(__("Purchase Invoice"),
				() => frappe.set_route("Form", "Purchase Invoice", frm.doc.purchase_invoice),
				__("View"));
		}
		if (frm.doc.purchase_order) {
			frm.add_custom_button(__("Purchase Order"),
				() => frappe.set_route("Form", "Purchase Order", frm.doc.purchase_order),
				__("View"));
		}

		if (frm.doc.rejection_reason && status === "Rejected") {
			frm.dashboard.set_headline(
				__("Bill rejected: {0}", [frm.doc.rejection_reason]));
		}
	},
});

function call(frm, method, message) {
	frappe.call({
		method: `gdl_fleet_extension.utils.fleet_purchase_automation.${method}`,
		args: { maintenance_log: frm.doc.name },
		freeze: true,
		freeze_message: message,
		callback() {
			frm.reload_doc();
		},
	});
}

function reject(frm) {
	frappe.prompt(
		[{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1 }],
		(values) => {
			frappe.call({
				method: "gdl_fleet_extension.utils.fleet_purchase_automation.reject_bill",
				args: { maintenance_log: frm.doc.name, reason: values.reason },
				freeze: true,
				callback() {
					frm.reload_doc();
				},
			});
		},
		__("Reject this bill"),
		__("Reject"),
	);
}
