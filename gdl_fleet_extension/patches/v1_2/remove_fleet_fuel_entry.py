"""Retire Fleet Fuel Entry.

`Fleet Management- Final. 25-Sept.docx` names only "Custom POL Abstract + POL
Entry child table" for POL Management, and never mentions a fuel entry document.
The per-fill details it asks for - Fuel Type, Quantity, Rate, Total Amount,
Odometer Reading, Fuel Station/Supplier, Driver - are now captured on POL Entry
itself, which is where the document places them.

Order of work:
  1. copy fuel type, odometer and driver onto any POL Entry that referenced a
     Fleet Fuel Entry, so no captured detail is lost;
  2. drop the link column;
  3. delete the records and the DocType.

The records were exported to
gdl_decommission_backup/fleet_fuel_entry_export.json before this patch ran.
"""

import frappe

DOCTYPE = "Fleet Fuel Entry"


def execute():
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	migrate_detail_onto_pol_entries()
	# ALTER is DDL; frappe refuses it while writes are pending, so the copy
	# above is committed first.
	frappe.db.commit()

	drop_link_column()
	frappe.db.commit()

	delete_records_and_doctype()
	frappe.db.commit()


def migrate_detail_onto_pol_entries():
	"""Carry the fill details the document wants onto the POL entry row."""
	if "fleet_fuel_entry" not in frappe.db.get_table_columns("POL Entry"):
		return

	rows = frappe.db.sql(
		"""select name, fleet_fuel_entry from `tabPOL Entry`
		   where ifnull(fleet_fuel_entry, '') != ''""",
		as_dict=True,
	)
	for row in rows:
		src = frappe.db.get_value(
			DOCTYPE, row.fleet_fuel_entry,
			["fuel_type", "odometer", "driver"], as_dict=True,
		)
		if not src:
			continue
		for field, value in src.items():
			if value and not frappe.db.get_value("POL Entry", row.name, field):
				frappe.db.set_value("POL Entry", row.name, field, value,
				                    update_modified=False)


def drop_link_column():
	if "fleet_fuel_entry" in frappe.db.get_table_columns("POL Entry"):
		frappe.db.sql("alter table `tabPOL Entry` drop column `fleet_fuel_entry`")


def delete_records_and_doctype():
	"""Remove the records and the DocType.

	The controller module has already been deleted from the app, so
	`frappe.delete_doc` cannot be used for the records themselves - it would try
	to import a module that no longer exists. The rows are removed directly and
	the DocType is then deleted, which drops the table.
	"""
	table = f"tab{DOCTYPE}"
	if frappe.db.sql("show tables like %s", (table,)):
		for linked in ("Version", "Comment", "Activity Log", "Document Follow",
		               "Email Unsubscribe", "Assignment Rule"):
			if not frappe.db.exists("DocType", linked):
				continue
			col = "ref_doctype" if linked == "Version" else "reference_doctype"
			if col in frappe.db.get_table_columns(linked):
				frappe.db.sql(f"delete from `tab{linked}` where {col} = %s", (DOCTYPE,))
		frappe.db.sql(f"delete from `{table}`")
		frappe.db.commit()

	if frappe.db.exists("DocType", DOCTYPE):
		developer_mode = frappe.conf.developer_mode
		try:
			frappe.conf.developer_mode = 1
			frappe.delete_doc("DocType", DOCTYPE, force=True, ignore_permissions=True)
		finally:
			frappe.conf.developer_mode = developer_mode
