// Copyright (c) 2026, GDL and contributors

frappe.ui.form.on("POL Abstract", {
	refresh(frm) {
		set_performance_help(frm);
		add_fuel_claim_buttons(frm);
		add_bulk_entry_button(frm);
		show_bill_requirement(frm);
		restrict_fuel_suppliers(frm);
	},

	onload(frm) {
		restrict_fuel_suppliers(frm);
	},

	vehicle(frm) {
		frm.set_value("driver", null);
		carry_forward(frm);
	},

	period_from(frm) {
		carry_forward(frm);
	},

	// Performance is stored at full accuracy; this only governs what is shown.
	total_fuel_consumed(frm) {
		set_performance_help(frm);
		add_fuel_claim_buttons(frm);
	},
});

frappe.ui.form.on("POL Entry", {
	litres: (frm, cdt, cdn) => default_amount(frm, cdt, cdn),
	rate: (frm, cdt, cdn) => default_amount(frm, cdt, cdn),
	entries_add(frm, cdt, cdn) {
		// The document captures Driver against the fuel supply; it is the same
		// driver as the abstract unless the row says otherwise.
		if (frm.doc.driver) frappe.model.set_value(cdt, cdn, "driver", frm.doc.driver);
	},
});

function default_amount(frm, cdt, cdn) {
	// Mirrors the server: Litres x Rate is only a default. An amount the user
	// has already typed is left alone, because the customer's workbook carries
	// hand-entered amounts that must survive as approved.
	const row = locals[cdt][cdn];
	if (row.amount_overridden) return;
	frappe.model.set_value(cdt, cdn, "total_amount", flt(row.litres) * flt(row.rate));
}

function restrict_fuel_suppliers(frm) {
	// The supplier is the routing key: it decides whether a fill is claimed
	// from BOD or from STCBL. Offering any supplier at all would let a row be
	// credited to neither, so the list is narrowed to GDL's two providers.
	frappe.call({
		method: "gdl_fleet_extension.gdl_fleet.doctype.pol_abstract.pol_abstract.get_fuel_suppliers",
		callback(r) {
			const providers = r.message || [];
			if (!providers.length) return;   // not configured yet - leave it open
			frm.set_query("supplier", "entries", () => ({
				filters: { name: ["in", providers] },
			}));
		},
	});
}

function carry_forward(frm) {
	if (!frm.doc.vehicle || frm.doc.docstatus !== 0) return;

	frappe.call({
		method: "gdl_fleet_extension.gdl_fleet.doctype.pol_abstract.pol_abstract.get_carry_forward",
		args: { vehicle: frm.doc.vehicle, period_from: frm.doc.period_from, exclude: frm.doc.name },
		callback(r) {
			if (!r.message) return;
			if (r.message.opening_km !== null && !frm.doc.opening_km) {
				frm.set_value("opening_km", r.message.opening_km);
			}
			if (r.message.previous_tank_balance !== null && !frm.doc.previous_tank_balance) {
				frm.set_value("previous_tank_balance", r.message.previous_tank_balance);
			}
			if (r.message.source) {
				frm.dashboard.set_headline(
					__("Opening readings carried forward from {0}. Override them if required.", [r.message.source])
				);
			}
		},
	});
}

function set_performance_help(frm) {
	if (!frm.doc.performance_per_litre) return;
	frm.get_field("performance_per_litre").set_description(
		__("{0} KM/L = Total KM {1} / Total Fuel Consumed {2}", [
			flt(frm.doc.performance_per_litre, 2),
			frm.doc.total_km,
			frm.doc.total_fuel_consumed,
		])
	);
}

function add_fuel_claim_buttons(frm) {
	// The fuel claim is raised from an APPROVED abstract, one invoice per provider.
	if (frm.doc.docstatus !== 1) return;

	frappe.call({
		method: "gdl_fleet_extension.gdl_fleet.doctype.pol_abstract.pol_abstract.get_claim_status",
		args: { pol_abstract: frm.doc.name },
		callback(r) {
			const status = r.message || {};
			Object.keys(status).forEach((provider) => {
				const info = status[provider];
				if (info.invoice) {
					frm.add_custom_button(
						__("{0} Invoice: {1}", [provider, info.invoice]),
						() => frappe.set_route("Form", "Purchase Invoice", info.invoice),
						__("Fuel Claim")
					);
				} else if (info.claimable) {
					frm.add_custom_button(
						__("Raise {0} Claim", [provider]),
						() => raise_claim(frm, provider),
						__("Fuel Claim")
					);
				}
			});
		},
	});
}

function raise_claim(frm, provider) {
	frappe.call({
		method: "gdl_fleet_extension.gdl_fleet.doctype.pol_abstract.pol_abstract.make_fuel_invoice",
		args: { pol_abstract: frm.doc.name, provider: provider },
		freeze: true,
		freeze_message: __("Raising the {0} fuel claim...", [provider]),
		callback(r) {
			if (!r.message) return;
			frappe.show_alert({
				message: __("Purchase Invoice {0} created as a draft for review.", [r.message]),
				indicator: "green",
			});
			frm.reload_doc();
		},
	});
}


function show_bill_requirement(frm) {
	// The server refuses the abstract without it as soon as it leaves Draft.
	// Marking the field here means the driver finds out while filling the
	// form, not after clicking Submit for Approval.
	// There is nothing to mark on a document that can no longer be edited, and
	// the call was what greeted anyone opening an approved abstract.
	if (frm.doc.docstatus !== 0) return;

	// Asked of the server as a single flag. Reading the setting from here goes
	// through frappe.client.get_value, which demands read on the whole of GDL
	// Fleet Settings - which a driver has not got, and does not need.
	frappe
		.call({
			method: "gdl_fleet_extension.gdl_fleet.doctype.pol_abstract.pol_abstract.bill_attachment_required",
		})
		.then((r) => frm.toggle_reqd("supplier_bill_attachment", !!r.message));
}

function add_bulk_entry_button(frm) {
	if (frm.doc.docstatus !== 0) return;
	const grid = frm.fields_dict.entries.grid;

	// A month of fuel supplies shares a supplier, a fuel type and usually a
	// rate. Typing those into every row is the slow part of the abstract, so
	// they are set once here instead.
	grid.add_custom_button(__("Set for All Rows"), () => {
		const rows = selected_or_all(grid);
		if (!rows.length) {
			frappe.msgprint(__("Add a fuel supply row first."));
			return;
		}
		frappe.prompt(
			bulk_fields(grid, frm),
			(values) => apply_to_rows(frm, rows, values),
			__("Set for {0} Row(s)", [rows.length]),
			__("Apply")
		);
	});
}

// Fields worth setting once for a whole abstract: the supplier, the fuel type
// and the rate rarely vary inside one period. Their definitions are copied
// from POL Entry rather than restated, so the dialog cannot drift from the row.
const BULK_FIELDS = ["supplier", "fuel_type", "rate", "driver"];

function bulk_fields(grid, frm) {
	const fields = BULK_FIELDS.map((fieldname) => {
		const df = grid.get_docfield(fieldname);
		return {
			fieldname,
			label: df.label,
			fieldtype: df.fieldtype,
			options: df.options,
			default: fieldname === "driver" ? frm.doc.driver : null,
		};
	});
	fields.push({
		fieldtype: "HTML",
		options: `<p class="text-muted small">${__(
			"Only the fields you fill in are applied. The rest of each row is left as it is."
		)}</p>`,
	});
	return fields;
}

function selected_or_all(grid) {
	// Frappe returns the ticked rows, or nothing when none are ticked - in
	// which case the driver means the whole table.
	const selected = grid.get_selected_children();
	return selected && selected.length ? selected : grid.grid_rows.map((r) => r.doc);
}

function apply_to_rows(frm, rows, values) {
	const fields = Object.keys(values).filter((f) => values[f]);
	if (!fields.length) return;

	for (const row of rows) {
		for (const field of fields) {
			frappe.model.set_value(row.doctype, row.name, field, values[field]);
		}
		// Rate feeds the amount, but never over an amount already approved by
		// hand - the same rule the row-level handler and the server apply.
		if (values.rate && !row.amount_overridden) {
			frappe.model.set_value(row.doctype, row.name, "total_amount",
				flt(row.litres) * flt(values.rate));
		}
	}
	frm.refresh_field("entries");
	frappe.show_alert({
		message: __("Applied {0} field(s) to {1} row(s).", [fields.length, rows.length]),
		indicator: "green",
	});
}
