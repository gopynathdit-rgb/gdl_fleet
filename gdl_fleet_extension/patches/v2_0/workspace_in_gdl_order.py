# Copyright (c) 2026, GDL and contributors
"""Rebuild the GDL Fleet menu in the order GDL asked for.

GDL wrote the list out: Vehicle, Driver Assignment, Insurance and Renewal,
Movement Order Request, Movement Order, Daily KM / Odometer Recording, POL
Management, Vehicle Service and Maintenance, Reports - "thats all", then
"hide others".

A Workspace is a document, so a site that already has one keeps whatever it
has; shipping a new JSON only reaches a fresh install. This replays it.

Nothing is deleted. The entries taken off the menu - Asset Maintenance, Asset
Repair and the three standard accounting reports - are DocTypes and reports
that still exist, still carry their permissions, and are still reachable by
search. Only the menu rows are gone.
"""

import json
import os

import frappe

WORKSPACE = "GDL Fleet"


def execute():
	if not frappe.db.exists("Workspace", WORKSPACE):
		return

	import gdl_fleet_extension
	path = os.path.join(os.path.dirname(gdl_fleet_extension.__file__),
	                    "gdl_fleet", "workspace", "gdl_fleet", "gdl_fleet.json")
	if not os.path.isfile(path):
		return

	with open(path, encoding="utf-8") as f:
		shipped_doc = json.load(f)
	shipped = shipped_doc["links"]

	doc = frappe.get_doc("Workspace", WORKSPACE)
	# BOTH have to match. Checking only the links let this return early with
	# the page layout still naming the old cards, which rendered a workspace
	# with eight of its ten cards missing.
	links_match = ([(l.type, l.label) for l in doc.links]
	               == [(l["type"], l["label"]) for l in shipped])
	content_match = (doc.content or "") == shipped_doc["content"]
	if links_match and content_match:
		return

	doc.links = []
	for row in shipped:
		doc.append("links", row)

	# The page layout names the cards it draws. A card with no block in
	# `content` never appears, so renaming the cards without this would empty
	# the workspace - a test caught exactly that.
	doc.content = shipped_doc["content"]
	doc.flags.ignore_permissions = True
	doc.save()
	frappe.clear_cache()
	frappe.db.commit()

	cards = [l["label"] for l in shipped if l["type"] == "Card Break"]
	print(f"  {WORKSPACE} menu rebuilt: {', '.join(cards)}")
