# Copyright (c) 2026, GDL and contributors
"""
Approved decision C3: the STANDARD ERPNext Location DocType is the GDL Site
master. No Site DocType is created.

    GDL
    |-- Head Office
    `-- Farms
        |-- Jamjee Farm
        |-- Dochula Farm
        |-- Dagapela Farm
        |-- Gedu
        |-- Samcholing
        `-- Jigmeling

Vehicles and fleet documents link to the LEAF nodes. Reports roll up through the
standard nested-set tree, so "all farms" is a single filter.
"""

import frappe

GDL_ROOT = "GDL"
FARMS_GROUP = "Farms"

SITE_TREE = {
	GDL_ROOT: {"is_group": 1, "parent": None},
	"Head Office": {"is_group": 0, "parent": GDL_ROOT},
	FARMS_GROUP: {"is_group": 1, "parent": GDL_ROOT},
	"Jamjee Farm": {"is_group": 0, "parent": FARMS_GROUP},
	"Dochula Farm": {"is_group": 0, "parent": FARMS_GROUP},
	"Dagapela Farm": {"is_group": 0, "parent": FARMS_GROUP},
	"Gedu": {"is_group": 0, "parent": FARMS_GROUP},
	"Samcholing": {"is_group": 0, "parent": FARMS_GROUP},
	"Jigmeling": {"is_group": 0, "parent": FARMS_GROUP},
}

# Insert parents before children.
CREATION_ORDER = [
	GDL_ROOT,
	"Head Office",
	FARMS_GROUP,
	"Jamjee Farm",
	"Dochula Farm",
	"Dagapela Farm",
	"Gedu",
	"Samcholing",
	"Jigmeling",
]


def create_site_locations():
	"""Idempotent. Never renames or re-parents a Location that already exists.

	Seeds only a site that has no operating Locations of its own. A live GDL
	database already carries GDL's real sites under GDL's own names - Jamjee,
	Dochula, Dagapela - and seeding this tree on top of them produces a second
	set ("Jamjee Farm") that means the same place. Vehicles then split across
	two names for one farm and every per-site report under-reports.

	So: seed a fresh site, stay out of the way of a real one.
	"""
	if frappe.db.count("Location", {"is_group": 0}):
		return

	for location_name in CREATION_ORDER:
		if frappe.db.exists("Location", location_name):
			continue

		spec = SITE_TREE[location_name]
		frappe.get_doc(
			{
				"doctype": "Location",
				"location_name": location_name,
				"is_group": spec["is_group"],
				"parent_location": spec["parent"],
			}
		).insert(ignore_permissions=True)
