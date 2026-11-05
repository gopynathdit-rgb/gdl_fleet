# Copyright (c) 2026, GDL and contributors
"""Shared test fixtures that build real STANDARD ERPNext records."""

import frappe
from frappe.utils import nowdate

COMPANY = "GDL (Demo)"
ASSET_CATEGORY = "_Test GDL Vehicles"
ASSET_ITEM = "_Test GDL Vehicle Item"
MAINTENANCE_TEAM = "_Test GDL Fleet Team"
SPARE_ITEM = "_Test GDL Spare Part"
WAREHOUSE = "_Test GDL Store"


def company_exists():
	return frappe.db.exists("Company", COMPANY)


def get_account(account_type=None, root_type=None, name_like=None):
	filters = {"company": COMPANY, "is_group": 0, "disabled": 0}
	if account_type:
		filters["account_type"] = account_type
	if root_type:
		filters["root_type"] = root_type
	if name_like:
		filters["name"] = ("like", name_like)
	return frappe.db.get_value("Account", filters, "name")


def make_warehouse():
	name = f"{WAREHOUSE} - {frappe.get_cached_value('Company', COMPANY, 'abbr')}"
	if frappe.db.exists("Warehouse", name):
		return name
	wh = frappe.get_doc(
		{"doctype": "Warehouse", "warehouse_name": WAREHOUSE, "company": COMPANY}
	).insert(ignore_permissions=True)
	return wh.name


def make_asset_category():
	if frappe.db.exists("Asset Category", ASSET_CATEGORY):
		return ASSET_CATEGORY

	doc = frappe.get_doc(
		{
			"doctype": "Asset Category",
			"asset_category_name": ASSET_CATEGORY,
			"accounts": [
				{
					"company_name": COMPANY,
					"fixed_asset_account": get_account(account_type="Fixed Asset"),
					"accumulated_depreciation_account": get_account(
						account_type="Accumulated Depreciation"
					),
					"depreciation_expense_account": get_account(account_type="Depreciation"),
				}
			],
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def make_asset_item():
	if frappe.db.exists("Item", ASSET_ITEM):
		return ASSET_ITEM

	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": ASSET_ITEM,
			"item_name": ASSET_ITEM,
			"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
			"is_fixed_asset": 1,
			"is_stock_item": 0,
			"asset_category": make_asset_category(),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def make_asset(asset_name=None, purchase_amount=1500000):
	"""A real, submitted standard ERPNext Asset with depreciation switched off."""
	asset_name = asset_name or f"_Test GDL Asset {frappe.generate_hash(length=6)}"
	location = "Head Office"

	doc = frappe.get_doc(
		{
			"doctype": "Asset",
			"asset_name": asset_name,
			"item_code": make_asset_item(),
			"asset_category": ASSET_CATEGORY,
			"company": COMPANY,
			"location": location,
			"purchase_date": nowdate(),
			"available_for_use_date": nowdate(),
			"asset_type": "Existing Asset",
			"calculate_depreciation": 0,
			"net_purchase_amount": purchase_amount,
			"asset_quantity": 1,
			"maintenance_required": 1,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return doc


TEAM_USER = "fleet.tester@gdl.test"


def make_team_user():
	"""erpnext assigns maintenance tasks via User.email, so name must equal email."""
	if frappe.db.exists("User", TEAM_USER):
		return TEAM_USER

	doc = frappe.get_doc(
		{
			"doctype": "User",
			"email": TEAM_USER,
			"first_name": "Fleet",
			"last_name": "Tester",
			"send_welcome_email": 0,
			"enabled": 1,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def make_maintenance_team():
	if frappe.db.exists("Asset Maintenance Team", MAINTENANCE_TEAM):
		return MAINTENANCE_TEAM

	user = make_team_user()
	doc = frappe.get_doc(
		{
			"doctype": "Asset Maintenance Team",
			"maintenance_team_name": MAINTENANCE_TEAM,
			"company": COMPANY,
			"maintenance_manager": user,
			"maintenance_team_members": [
				{"team_member": user, "maintenance_role": "Fleet Maintenance User"}
			],
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def enable_serial_tracking():
	"""ERPNext 16 ships `enable_serial_and_batch_no_for_item` OFF by default.

	Without it, no serial-tracked item can be transacted at all. The app does NOT
	flip this automatically - it is a site-wide stock policy, so GDL enables it
	deliberately. Tests set it so serial behaviour can be exercised.
	"""
	if not frappe.db.get_single_value("Stock Settings", "enable_serial_and_batch_no_for_item"):
		frappe.db.set_single_value("Stock Settings", "enable_serial_and_batch_no_for_item", 1)
		frappe.clear_document_cache("Stock Settings", "Stock Settings")


def make_stock_item(item_code, is_stock_item=1, has_serial_no=0, serial_series=None):
	if has_serial_no:
		enable_serial_tracking()

	if frappe.db.exists("Item", item_code):
		return item_code

	values = {
		"doctype": "Item",
		"item_code": item_code,
		"item_name": item_code,
		"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
		"is_stock_item": is_stock_item,
		"stock_uom": "Nos",
		"has_serial_no": has_serial_no,
		"valuation_rate": 1000,
	}
	if has_serial_no and serial_series:
		values["serial_no_series"] = serial_series

	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


def receive_stock(item_code, qty, warehouse=None, rate=1000, serial_nos=None):
	"""Standard Stock Entry (Material Receipt) so there is real stock to issue."""
	warehouse = warehouse or make_warehouse()
	row = {"item_code": item_code, "qty": qty, "t_warehouse": warehouse, "basic_rate": rate}

	if serial_nos:
		# v16 accepts plain serial text when use_serial_batch_fields is set; ERPNext
		# builds the Serial and Batch Bundle itself.
		row["use_serial_batch_fields"] = 1
		row["serial_no"] = "\n".join(serial_nos)

	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": COMPANY,
			"items": [row],
		}
	)
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()
	return entry


def issue_stock(item_code, qty, warehouse=None, serial_nos=None, **kwargs):
	"""Standard Stock Entry (Material Issue) - the only way stock leaves."""
	warehouse = warehouse or make_warehouse()
	row = {"item_code": item_code, "qty": qty, "s_warehouse": warehouse}
	if serial_nos:
		row["use_serial_batch_fields"] = 1
		row["serial_no"] = "\n".join(serial_nos)

	values = {
		"doctype": "Stock Entry",
		"stock_entry_type": "Material Issue",
		"company": COMPANY,
		"items": [row],
	}
	values.update(kwargs)
	entry = frappe.get_doc(values)
	entry.flags.ignore_permissions = True
	entry.insert()
	entry.submit()
	return entry
