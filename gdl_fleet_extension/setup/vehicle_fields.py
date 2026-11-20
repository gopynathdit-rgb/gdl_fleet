# Copyright (c) 2026, GDL and contributors
"""
Phase 2 - extension of the STANDARD ERPNext Vehicle DocType.

Nothing here edits erpnext core. Every change is either a Custom Field or a
Property Setter, both of which are versioned records owned by this app.

Standard fields deliberately REUSED instead of duplicated:
    license_plate    -> Registration Number (and the document name)
    chassis_no       -> Chassis Number
    color            -> Colour
    insurance_company-> Insurance Company
    policy_no        -> Insurance Policy Number
    start_date       -> Insurance Start Date
    end_date         -> Insurance Expiry
    last_odometer    -> Current Odometer
    employee         -> Responsible Employee
    make / model / fuel_type / uom / acquisition_date / vehicle_value / company
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

VEHICLE_CUSTOM_FIELDS = {
	"Vehicle": [
		# --- GDL identification -------------------------------------------------
		{
			# Third column in the header. GDL: "make this proper alignment like
			# split 3 column and need look good" - it read Registration/Make on
			# the left and Model/Company on the right, leaving a gap under Make.
			# Registration | Make and Model | Company instead.
			"fieldname": "gdl_head_cb2",
			"fieldtype": "Column Break",
			"insert_after": "model",
		},
		{
			# Third columns. GDL asked for every section across the top of the
			# Vehicle form to read in three: "Site and Accounting Dimensions
			# also make 3 column and Details also Insurance Details,
			# Additional Details make 3 column".
			"fieldname": "gdl_organisation_cb2",
			"fieldtype": "Column Break",
			"insert_after": "cost_center",
		},
		{
			"fieldname": "gdl_details_cb2",
			"fieldtype": "Column Break",
			"insert_after": "chassis_no",
		},
		{
			"fieldname": "gdl_insurance_cb2",
			"fieldtype": "Column Break",
			"insert_after": "policy_no",
		},
		{
			"fieldname": "gdl_additional_cb2",
			"fieldtype": "Column Break",
			"insert_after": "color",
		},
		{
			"fieldname": "gdl_identification_section",
			"label": "GDL Fleet Identification",
			"fieldtype": "Section Break",
			"insert_after": "company",
		},
		{
			"fieldname": "gdl_vehicle_id",
			"label": "Vehicle ID",
			"fieldtype": "Data",
			"insert_after": "gdl_identification_section",
			"unique": 1,
			"set_only_once": 0,
			"in_standard_filter": 1,
			"in_list_view": 1,
			"description": "Stable internal GDL fleet identifier. Auto-generated if left blank. "
			"Immutability is enforced in gdl_fleet_extension.overrides.vehicle so that vehicles "
			"created before this app was installed can still be backfilled.",
		},
		{
			"fieldname": "vehicle_type",
			"label": "Vehicle Type",
			"fieldtype": "Link",
			"options": "Fleet Vehicle Type",
			"insert_after": "gdl_vehicle_id",
			"in_standard_filter": 1,
			"reqd": 1,
		},
		{
			"fieldname": "vehicle_status",
			"label": "Vehicle Status",
			"fieldtype": "Select",
			"options": "Active\nUnder Maintenance\nUnavailable\nDisposed",
			"default": "Active",
			"insert_after": "vehicle_type",
			"read_only": 1,
			"in_standard_filter": 1,
			"in_list_view": 1,
			"description": "Fleet Mgmt.docx 4.1. Whether a vehicle is currently booked is "
			"derived from its Movement Orders, not stored here - see the Vehicle "
			"Availability report.",
		},
		{
			"fieldname": "gdl_identification_cb",
			"fieldtype": "Column Break",
			"insert_after": "vehicle_status",
		},
		{
			"fieldname": "ownership_type",
			"label": "Ownership Type",
			"fieldtype": "Select",
			"options": "GDL Owned\nLeased\nRented\nOther",
			"default": "GDL Owned",
			"insert_after": "gdl_identification_cb",
			"reqd": 1,
			"in_standard_filter": 1,
		},
		{
			"fieldname": "lessor",
			"label": "Lessor / Rental Supplier",
			"fieldtype": "Link",
			"options": "Supplier",
			"insert_after": "ownership_type",
			"depends_on": "eval:['Leased','Rented'].includes(doc.ownership_type)",
			"mandatory_depends_on": "eval:['Leased','Rented'].includes(doc.ownership_type)",
			"permlevel": 1,
		},
		{
			"fieldname": "asset",
			"label": "Asset",
			"fieldtype": "Link",
			"options": "Asset",
			"insert_after": "lessor",
			"description": "Links the vehicle to its Asset record so that standard Asset Maintenance, "
			"Asset Repair, Asset Movement and depreciation apply.",
			"permlevel": 1,
		},
		{
			"fieldname": "engine_no",
			"label": "Engine No",
			"fieldtype": "Data",
			"insert_after": "asset",
		},
		{
			"fieldname": "capacity",
			"label": "Capacity",
			"fieldtype": "Int",
			"insert_after": "engine_no",
			"description": "Passenger seats or load capacity.",
		},
		{
			"fieldname": "capacity_uom",
			"label": "Capacity UOM",
			"fieldtype": "Link",
			"options": "UOM",
			"insert_after": "capacity",
			"description": "Seats, Tonne, Litre and so on.",
		},
		{
			# Deliberately NOT part of "Capacity" above, which is passenger seats
			# or load. This is the fuel tank, and it sits beside Fuel Type and
			# Fuel UOM in Additional Details where somebody looking for it will
			# actually look.
			"fieldname": "fuel_tank_capacity",
			"label": "Fuel Tank Capacity",
			"fieldtype": "Float",
			"insert_after": "uom",
			"description": "A full tank, in the Fuel UOM above.",
		},
		{
			# Third column of GDL Fleet Identification, which was three fields
			# against seven.
			"fieldname": "gdl_identification_cb2",
			"fieldtype": "Column Break",
			"insert_after": "engine_no",
		},
		{
			"fieldname": "manufacturing_year",
			"label": "Manufacturing Year",
			"fieldtype": "Int",
			"insert_after": "engine_no",
		},
		# --- Organisation -------------------------------------------------------
		{
			"fieldname": "gdl_organisation_section",
			"label": "Site and Accounting Dimensions",
			"fieldtype": "Section Break",
			"insert_after": "manufacturing_year",
		},
		{
			"fieldname": "site",
			"label": "Site",
			"fieldtype": "Link",
			"options": "Location",
			"insert_after": "gdl_organisation_section",
			"in_standard_filter": 1,
			"description": "Standard ERPNext Location is the GDL Site master. Must be a leaf node.",
		},
		{
			"fieldname": "department",
			"label": "Department",
			"fieldtype": "Link",
			"options": "Department",
			"insert_after": "site",
		},
		{
			"fieldname": "gdl_organisation_cb",
			"fieldtype": "Column Break",
			"insert_after": "department",
		},
		{
			"fieldname": "cost_center",
			"label": "Cost Center",
			"fieldtype": "Link",
			"options": "Cost Center",
			"insert_after": "gdl_organisation_cb",
		},
		{
			"fieldname": "project",
			"label": "Project",
			"fieldtype": "Link",
			"options": "Project",
			"insert_after": "cost_center",
		},
		# --- Odometer -----------------------------------------------------------
		{
			"fieldname": "opening_odometer",
			"label": "Opening Odometer",
			"fieldtype": "Int",
			"insert_after": "last_odometer",
			"description": "Reading when the vehicle entered GDL's fleet records.",
		},
		{
			"fieldname": "min_mileage",
			"label": "Minimum Required Mileage (KM/L)",
			"fieldtype": "Float",
			"precision": "2",
			"insert_after": "expected_monthly_km",
			"description": "Fleet Management Final 25-Sept, mileage chart. Actual km/l is "
			"compared against this. Leave at 0 for vehicles where fuel efficiency does "
			"not apply, such as an EV - they are excluded from deviation monitoring.",
		},
		{
			"fieldname": "expected_monthly_km",
			"label": "Expected Monthly KM",
			"fieldtype": "Int",
			"insert_after": "opening_odometer",
			"description": "Overrides the vehicle-type mileage norm for deviation analysis.",
		},
		# --- Registration and compliance ---------------------------------------
		{
			"fieldname": "gdl_compliance_section",
			"label": "Registration and Compliance",
			"fieldtype": "Section Break",
			"insert_after": "policy_no",
		},
		{
			"fieldname": "registration_expiry",
			"label": "Registration Expiry",
			"fieldtype": "Date",
			"insert_after": "gdl_compliance_section",
		},
		{
			# HIDDEN, not deleted - the same duplication as
			# `insurance_renewal_date` below, and removed for the same reason.
			# A renewal date is the "renew by" date, by GDL's own definition,
			# and a registration must be renewed by the day it expires. This
			# and `registration_expiry` therefore always printed the same
			# value, side by side on one screen.
			#
			# Registration Expiry is the one kept.
			#
			# The column and its data stay. Clearing the tick brings it back.
			"fieldname": "registration_renewal_date",
			"label": "Registration Renewal Date",
			"fieldtype": "Date",
			"insert_after": "registration_expiry",
			"hidden": 1,
		},
		{
			"fieldname": "gdl_compliance_cb",
			"fieldtype": "Column Break",
			"insert_after": "registration_renewal_date",
		},
		{
			"fieldname": "inspection_expiry",
			"label": "Inspection Expiry",
			"fieldtype": "Date",
			"insert_after": "gdl_compliance_cb",
		},
		{
			# HIDDEN, not deleted. GDL's client, looking at the Vehicle form:
			# "There are 2 Insurance Renewals. u can remove one."
			#
			# They were right - this and `end_date` (Insurance Expiry) are the
			# same fact. GDL had already defined a renewal date as the
			# "renew by" date, and the day a policy must be renewed by is the
			# day it expires, so the two always printed the same value in two
			# places on one screen.
			#
			# Insurance Expiry is the one kept: it sits in Insurance Details
			# with the company and the policy number, which is where somebody
			# looks for it. This one sat under Registration and Compliance.
			#
			# The column and its data stay. Clearing the tick brings it back.
			"fieldname": "insurance_renewal_date",
			"label": "Insurance Renewal Date",
			"fieldtype": "Date",
			"insert_after": "inspection_expiry",
			"hidden": 1,
		},
		# --- Documents ----------------------------------------------------------
		{
			"fieldname": "gdl_documents_section",
			"label": "Vehicle Documents",
			"fieldtype": "Section Break",
			"insert_after": "insurance_renewal_date",
			"collapsible": 1,
		},
		{
			"fieldname": "documents",
			"label": "Documents",
			"fieldtype": "Table",
			"options": "Fleet Vehicle Document",
			"insert_after": "gdl_documents_section",
		},
		# --- Driver -------------------------------------------------------------
		{
			"fieldname": "driver",
			"label": "Assigned Driver",
			"fieldtype": "Link",
			"options": "Driver",
			"insert_after": "employee",
			"in_standard_filter": 1,
		},
	]
}

# (doctype, fieldname, property, value, property_type) - fieldname None = DocType level
VEHICLE_PROPERTY_SETTERS = [
	# Approved decision 2: license_plate IS the registration number.
	("Vehicle", "license_plate", "label", "Registration Number", "Data"),
	("Vehicle", "employee", "label", "Responsible Employee", "Data"),
	# The standard Insurance Details section already carries the policy period.
	("Vehicle", "start_date", "label", "Insurance Start Date", "Data"),
	("Vehicle", "end_date", "label", "Insurance Expiry", "Data"),
	("Vehicle", "last_odometer", "label", "Current Odometer (KM)", "Data"),
	# Allow an opening-odometer correction; standard sets this only once.
	("Vehicle", "last_odometer", "set_only_once", "0", "Check"),
	# GDL fuel types beyond the four standard options.
	(
		"Vehicle",
		"fuel_type",
		"options",
		"Petrol\nDiesel\nNatural Gas\nElectric\nHybrid\nCNG\nLPG\nOther",
		"Text",
	),
	# Superseded by the `site` Link to Location.
	("Vehicle", "location", "hidden", "1", "Check"),
	("Vehicle", "location", "label", "Location (deprecated - use Site)", "Data"),
	("Vehicle", None, "search_fields", "gdl_vehicle_id,make,model", "Data"),
]


GDL_MODULE = "GDL Fleet"


def setup_vehicle_customisations():
	"""Idempotent: safe to run on install and on every migrate."""
	fields = {
		doctype: [dict(df, module=GDL_MODULE) for df in dfs]
		for doctype, dfs in VEHICLE_CUSTOM_FIELDS.items()
	}
	create_custom_fields(fields, ignore_validate=True, update=True)

	for doctype, fieldname, prop, value, property_type in VEHICLE_PROPERTY_SETTERS:
		upsert_property_setter(doctype, fieldname, prop, value, property_type)

	reflow_vehicle_header()

	frappe.clear_cache(doctype="Vehicle")


def reflow_vehicle_header():
	"""Three columns across the top of the Vehicle form.

	GDL: "make this proper alignment like split 3 column and need look good".
	ERPNext ships the header as license_plate, make, BREAK, model, company -
	the break falls between Make and Model, so Make sat alone with a gap under
	it while Model and Company stacked on the right.

	    Registration | Make, Model | Company
	    Vehicle ID, Type, Status | Ownership, Lessor, Asset | Engine, Capacity...

	Every move goes through the field_order property setter, including the two
	custom Column Breaks. insert_after cannot do it: Meta.sort_fields
	deliberately relocates a Section or Column Break to the END of its
	section, so a break aimed at the middle of one lands at the far end -
	which is exactly where gdl_head_cb2 went on the first attempt, leaving an
	empty third column. field_order is read before any of that and is the one
	thing sort_fields does not second-guess.

	Computed from the live order rather than written out, so a field ERPNext
	adds or drops in a later version needs no change here.
	"""
	import json

	meta = frappe.get_meta("Vehicle")
	order = [f.fieldname for f in meta.fields]
	present = set(order)

	# (field to move, the field it must sit immediately BEFORE)
	# (field to move, the field it must sit immediately BEFORE)
	#
	# The header starts with license_plate, which frappe does NOT render on a
	# saved record - it is the document's name and shows in the breadcrumb
	# instead. Putting the first break after it therefore left an empty first
	# column on every existing vehicle, which is what GDL photographed. Make
	# shares the first column with it so that column always has something in
	# it, and Model moves beside rather than under it.
	moves = [
		("column_break_3", "model"),
		("gdl_head_cb2", "company"),
		("gdl_identification_cb2", "capacity"),
		# Site | Department | Cost Center, Project
		("gdl_organisation_cb", "department"),
		("gdl_organisation_cb2", "cost_center"),
		# odometers | mileage and purchase | the rest
		("column_break_8", "min_mileage"),
		("gdl_details_cb2", "vehicle_value"),
		# company | policy | the period
		("column_break_15", "policy_no"),
		("gdl_insurance_cb2", "start_date"),
		# fuel | carbon check and colour | the body
		("column_break_21", "carbon_check_date"),
		("gdl_additional_cb2", "wheels"),
	]

	changed = False
	for fieldname, before in moves:
		if fieldname not in present or before not in present:
			continue
		if order.index(fieldname) + 1 == order.index(before):
			continue		# already there
		order.remove(fieldname)
		order.insert(order.index(before), fieldname)
		changed = True

	if changed:
		upsert_property_setter("Vehicle", None, "field_order",
		                       json.dumps(order), "Text")


def upsert_property_setter(doctype, fieldname, prop, value, property_type):
	"""make_property_setter() always inserts, so it throws on the second migrate."""
	name = "-".join(filter(None, [doctype, fieldname or "", prop])) if fieldname else f"{doctype}-{prop}"
	existing = frappe.db.exists("Property Setter", name)

	if existing:
		ps = frappe.get_doc("Property Setter", existing)
		if ps.value != value:
			ps.value = value
			ps.flags.ignore_permissions = True
			ps.flags.validate_fields_for_doctype = False
			ps.save()
		return

	ps = make_property_setter(
		doctype,
		fieldname,
		prop,
		value,
		property_type,
		for_doctype=fieldname is None,
		validate_fields_for_doctype=False,
	)
	frappe.db.set_value("Property Setter", ps.name, "module", GDL_MODULE, update_modified=False)


def backfill_vehicle_ids():
	"""Give a Vehicle ID to any Vehicle that predates this app."""
	from frappe.model.naming import make_autoname

	names = frappe.get_all(
		"Vehicle",
		filters=[["gdl_vehicle_id", "in", ["", None]]],
		pluck="name",
		order_by="creation asc",
	)
	for name in names:
		frappe.db.set_value(
			"Vehicle", name, "gdl_vehicle_id", make_autoname("GDL-VEH-.#####"), update_modified=False
		)

	return len(names)
