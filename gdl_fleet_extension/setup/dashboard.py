# Copyright (c) 2026, GDL and contributors
"""
The fleet dashboard - Business Blueprint item 10, "Reports & Dashboard:
Query/Script Reports + Workspace", and GAP item 4, "Mileage Report/Dashboard".

Fifteen reports answer precise questions. None of them answers the one a
manager opens the desk to ask: is anything wrong this morning? These cards and
charts do, and each one is a doorway to the report that explains it.

Standard frappe Number Cards and Dashboard Charts, built from filters on real
documents. No stored aggregates, so nothing can drift out of step with the
records underneath.

Idempotent and additive: a card GDL has retitled, recoloured or filtered
differently is left exactly as they set it.
"""

import frappe

MODULE = "GDL Fleet"

# Both Number Card and Dashboard Chart take their RECORD NAME from their own
# title - Dashboard Chart through `autoname: field:chart_name`. There is no
# separate id to namespace, so a card is identified by the title GDL reads on
# screen, and anything already carrying that name is left alone rather than
# overwritten: it may belong to another app on the same site.
FLEET_ROLES = ("Fleet Manager", "Fleet Administrator", "Fleet Approver", "System Manager")


# ---------------------------------------------------------------------------
# Number cards - the "is anything wrong" row
# ---------------------------------------------------------------------------
NUMBER_CARDS = [
	{
		"label": "Vehicles Active",
		"document_type": "Vehicle",
		"function": "Count",
		"filters_json": '[["Vehicle","vehicle_status","=","Active",false]]',
		"color": "#29CD42",
	},
	{
		"label": "Off Road",
		"document_type": "Vehicle",
		"function": "Count",
		"filters_json":
			'[["Vehicle","vehicle_status","in",["Under Maintenance","Unavailable"],false]]',
		"color": "#FF5858",
	},
	{
		"label": "Renewals Due",
		"document_type": "Renewal Register",
		"function": "Count",
		"filters_json":
			'[["Renewal Register","renewal_status","in",["Due Soon","Expired"],false],'
			'["Renewal Register","docstatus","=",1,false]]',
		"color": "#FFC107",
	},
	{
		"label": "Requests Awaiting a Manager",
		"document_type": "Movement Order Request",
		"function": "Count",
		"filters_json":
			'[["Movement Order Request","workflow_state","=","Pending Review",false]]',
		"color": "#5E64FF",
	},
	{
		"label": "Mileage Outside Tolerance",
		"document_type": "POL Abstract",
		"function": "Count",
		"filters_json":
			'[["POL Abstract","mileage_status","in",["Below Tolerance","Above Tolerance"],false],'
			'["POL Abstract","docstatus","<",2,false]]',
		"color": "#FF8C00",
	},
]


# ---------------------------------------------------------------------------
# Charts - the trends behind the cards
# ---------------------------------------------------------------------------
DASHBOARD_CHARTS = [
	{
		"chart_name": "Fleet by Site",
		"chart_type": "Group By",
		"document_type": "Vehicle",
		"group_by_type": "Count",
		"group_by_based_on": "site",
		"number_of_groups": 10,
		"type": "Bar",
		"color": "#5E64FF",
	},
	{
		"chart_name": "Fleet by Status",
		"chart_type": "Group By",
		"document_type": "Vehicle",
		"group_by_type": "Count",
		"group_by_based_on": "vehicle_status",
		"number_of_groups": 5,
		"type": "Donut",
		"color": "#29CD42",
	},
	{
		"chart_name": "Distance Travelled",
		"chart_type": "Sum",
		"document_type": "Vehicle Log",
		"based_on": "date",
		"value_based_on": "distance_travelled",
		"timespan": "Last Year",
		"time_interval": "Monthly",
		"timeseries": 1,
		"type": "Bar",
		"color": "#449CF0",
	},
	{
		"chart_name": "Fuel Spend",
		"chart_type": "Sum",
		"document_type": "POL Abstract",
		"based_on": "period_to",
		"value_based_on": "total_amount_stcbl",
		"timespan": "Last Year",
		"time_interval": "Monthly",
		"timeseries": 1,
		"type": "Line",
		"color": "#FF8C00",
		"filters_json": '[["POL Abstract","docstatus","=",1,false]]',
	},
	{
		"chart_name": "Movement Orders",
		"chart_type": "Count",
		"document_type": "Movement Order",
		"based_on": "departure_datetime",
		"timespan": "Last Quarter",
		"time_interval": "Weekly",
		"timeseries": 1,
		"type": "Bar",
		"color": "#7575FF",
	},
]


# ---------------------------------------------------------------------------
def create_number_cards():
	created, skipped, foreign = [], [], []
	for spec in NUMBER_CARDS:
		name = spec["label"]
		owner_module = frappe.db.get_value("Number Card", name, "module")
		if owner_module == MODULE:
			skipped.append(name)
			continue
		if owner_module is not None:
			foreign.append(f"{name} (belongs to {owner_module})")
			continue
		if not frappe.db.exists("DocType", spec["document_type"]):
			continue

		doc = frappe.get_doc({
			"doctype": "Number Card",
			"type": "Document Type",
			"is_public": 1,
			"is_standard": 0,
			"module": MODULE,
			"show_percentage_stats": 0,
			"filters_json": "[]",
			**spec,
		})
		add_roles(doc)
		doc.flags.ignore_permissions = True
		doc.insert()
		created.append(name)
	return {"created": created, "already_present": skipped, "not_ours": foreign}


def create_dashboard_charts():
	created, skipped, foreign = [], [], []
	for spec in DASHBOARD_CHARTS:
		name = spec["chart_name"]
		owner_module = frappe.db.get_value("Dashboard Chart", name, "module")
		if owner_module == MODULE:
			skipped.append(name)
			continue
		if owner_module is not None:
			foreign.append(f"{name} (belongs to {owner_module})")
			continue
		if not frappe.db.exists("DocType", spec["document_type"]):
			continue
		# A chart whose source field has been renamed or removed would fail on
		# every desk load, so it is simply not created.
		meta = frappe.get_meta(spec["document_type"])
		for key in ("based_on", "value_based_on", "group_by_based_on"):
			fieldname = spec.get(key)
			if fieldname and not meta.get_field(fieldname):
				break
		else:
			doc = frappe.get_doc({
				"doctype": "Dashboard Chart",
				"is_public": 1,
				"is_standard": 0,
				"module": MODULE,
				# Mandatory on Dashboard Chart. "no filters" still has to be
				# said explicitly, or the insert fails and takes the whole
				# after_migrate hook down with it.
				"filters_json": "[]",
				**spec,
			})
			add_roles(doc)
			doc.flags.ignore_permissions = True
			doc.insert()
			created.append(name)
	return {"created": created, "already_present": skipped, "not_ours": foreign}


def add_roles(doc):
	"""Fleet roles only - these read operational data, not public figures."""
	if not doc.meta.get_field("roles"):
		return
	for role in FLEET_ROLES:
		if frappe.db.exists("Role", role):
			doc.append("roles", {"role": role})


def setup_dashboard():
	"""The dashboard is a convenience, not a prerequisite.

	It runs inside after_migrate alongside role, workflow and field setup. A
	chart that cannot be built - a renamed field, a doctype an app has not
	installed yet - must not abort the migrate and leave the rest of the
	module half configured, so each half is attempted independently and a
	failure is reported rather than raised.
	"""
	result = {}
	for key, builder in (("number_cards", create_number_cards),
	                     ("charts", create_dashboard_charts)):
		try:
			result[key] = builder()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title="GDL Fleet: dashboard setup failed",
				message=frappe.get_traceback(),
			)
			result[key] = {"created": [], "already_present": [], "not_ours": [],
			               "failed": True}
	return result
