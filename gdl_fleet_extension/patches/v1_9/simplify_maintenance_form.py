# Copyright (c) 2026, GDL and contributors
"""Cut the service record back to what the final document asks for.

2.1.1.4 Vehicle Maintenance Management lists the fields a service record holds.
Asset Maintenance Log carried those plus twenty-four others: ERPNext's own
asset-maintenance scaffolding, and a service-bill approval and purchasing cycle
that nobody had asked for.

The purchasing cycle is switched off here as well as hidden. Leaving it running
behind a hidden field would be worse than leaving it on screen - it would keep
failing where nobody could see it. It fails today: raising a purchase order
needs a Service Item and a Purchasing Company, and neither has ever been set,
so every completed record stops at

    purchasing_status  : Pending
    purchasing_message : Cannot raise a purchase order: Service Item missing.

The switch is only moved where it is still at its shipped default with nothing
configured behind it - that is, where it has never been able to run. If GDL has
set a Service Item, somebody meant to use it and the choice stands.

Nothing is deleted. The fields, their data and their code are all still there.
"""

import frappe

from gdl_fleet_extension.setup.maintenance_simplification import setup_simple_maintenance_form


def execute():
	setup_simple_maintenance_form()
	stand_down_purchasing()
	frappe.db.commit()


def stand_down_purchasing():
	get = lambda f: frappe.db.get_single_value("GDL Fleet Settings", f)

	if not get("maintenance_po_on_completion"):
		return

	if get("maintenance_service_item"):
		print("  Purchasing left on: a Service Item is configured.")
		return

	frappe.db.set_single_value("GDL Fleet Settings", "maintenance_po_on_completion", 0)
	frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
	print("  Purchasing on completion switched off - it had no Service Item to use.")

	stale = frappe.get_all("Asset Maintenance Log",
	                       filters={"purchasing_status": "Pending"}, pluck="name")
	for name in stale:
		frappe.db.set_value("Asset Maintenance Log", name,
		                    {"purchasing_status": "Not Required", "purchasing_message": ""},
		                    update_modified=False)
	if stale:
		print(f"  Cleared the stuck purchasing note on {len(stale)} record(s).")
