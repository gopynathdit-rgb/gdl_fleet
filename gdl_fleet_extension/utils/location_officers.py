# Copyright (c) 2026, GDL and contributors
"""
Who approves a vehicle request, location by location.

Client requirement (3 Nov 2026): "create a user and a manager (MTO location
wise)" and "final MTO will be at head office".

So every operating location names one MTO who approves that location's
requests, and the head office MTO is the final authority - able to approve
anywhere, and the cover when a location's own MTO is away. That is one
approval per request, not two: the head office MTO is a wider permission, not
an extra step.

The mapping lives in GDL Fleet Settings as data, never in code, because GDL
reassigns managers without a developer.
"""

import frappe
from frappe import _
from frappe.utils import cint

# Roles that may always approve, whatever the location table says. These are
# the administrator seats, not an operating MTO.
OVERRIDE_ROLES = ("System Manager", "Fleet Administrator")


def get_officers() -> list:
	"""Every configured location row. Empty when GDL has not set any up yet."""
	settings = frappe.get_cached_doc("GDL Fleet Settings")
	return settings.get("location_officers") or []


def enforcement_is_on() -> bool:
	return bool(cint(frappe.db.get_single_value("GDL Fleet Settings", "enforce_location_mto")))


def get_mto_for_location(location: str | None) -> str | None:
	"""The MTO who approves for this location."""
	if not location:
		return None
	for row in get_officers():
		if row.location == location:
			return row.mto
	return None


def get_head_office_mto() -> str | None:
	"""The final MTO. None when no row is ticked Head Office."""
	for row in get_officers():
		if cint(row.is_head_office):
			return row.mto
	return None


def get_head_office_location() -> str | None:
	for row in get_officers():
		if cint(row.is_head_office):
			return row.location
	return None


def get_approvers_for_location(location: str | None) -> list[str]:
	"""Everyone entitled to approve for this location, best match first.

	The location's own MTO comes first because that is who should act; the
	head office MTO follows as the final authority and the cover.
	"""
	approvers = []
	own = get_mto_for_location(location)
	if own:
		approvers.append(own)
	head = get_head_office_mto()
	if head and head not in approvers:
		approvers.append(head)
	return approvers


def may_approve(location: str | None, user: str | None = None) -> bool:
	"""Is this user allowed to approve for this location?"""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	if not enforcement_is_on():
		return True

	user_roles = set(frappe.get_roles(user))
	if user_roles.intersection(OVERRIDE_ROLES):
		return True

	approvers = get_approvers_for_location(location)
	if not approvers:
		# Nothing is configured AT ALL - no MTO for this location and no head
		# office either. Refusing here would stop the fleet working the day the
		# module goes live, so this falls back to the role check the workflow
		# already applies.
		return True

	# A location with no MTO of its own is covered by the head office MTO,
	# which is already in `approvers`. That is the final authority doing what
	# it is there for, not a gap.
	return user in approvers


def validate_approver(location: str | None, user: str | None = None, doctype: str | None = None):
	"""Throw unless this user may approve for this location."""
	user = user or frappe.session.user
	if may_approve(location, user):
		return

	approvers = get_approvers_for_location(location)
	frappe.throw(
		_(
			"{0} is approved by the manager for {1}. That is {2}. "
			"Ask them to approve it, or have the head office MTO act if they are away."
		).format(
			_(doctype) if doctype else _("This request"),
			frappe.bold(location or _("this location")),
			frappe.bold(", ".join(approvers)),
		),
		title=_("Not the Approver for This Location"),
	)


def describe_coverage() -> dict:
	"""What is configured, for the settings form and for tests."""
	officers = get_officers()
	locations = frappe.get_all("Location", filters={"is_group": 0}, pluck="name")
	covered = {row.location for row in officers}
	heads = [row.location for row in officers if cint(row.is_head_office)]
	return {
		"locations": len(locations),
		"covered": sorted(covered),
		"uncovered": sorted(set(locations) - covered),
		"head_office": heads,
		"enforced": enforcement_is_on(),
	}


# ----------------------------------------------------------------------
# Which fleet a user draws on
# ----------------------------------------------------------------------
def sites_for_user(user: str | None = None) -> list[str] | None:
	"""The locations whose vehicles this user may be offered.

	None means "no restriction" and is deliberately the fallback everywhere
	below. A site list is a filter on a dropdown, not a security boundary, and
	returning [] for an unmapped user would empty the vehicle list on day one
	for everybody GDL has not got round to mapping - the same reasoning
	may_approve() uses when nothing is configured.

	Resolution order, most specific first:

	  1. The administrator seats, and the head office MTO. The head office MTO
	     is the FINAL authority - "final MTO will be at head office" - so
	     confining them to head office vehicles would take away the one thing
	     that role exists for.
	  2. GDL Fleet Settings -> Location Officers. Every location MTO is already
	     named there, so they are scoped without anyone configuring anything.
	  3. frappe's own User Permission on Location. This is where a plain
	     requester gets their site: it is standard, GDL maintains it in the
	     desk, and it needs no field of ours.
	"""
	user = user or frappe.session.user

	if user == "Administrator" or not enforcement_is_on():
		return None

	if set(frappe.get_roles(user)).intersection(OVERRIDE_ROLES):
		return None

	if get_head_office_mto() == user:
		return None

	own = [row.location for row in get_officers() if row.mto == user and row.location]
	if not own:
		own = frappe.get_all(
			"User Permission",
			filters={"user": user, "allow": "Location"},
			pluck="for_value",
		)

	if not own:
		return None

	return expand_sites(own)


def expand_sites(sites: list[str]) -> list[str]:
	"""A group location stands for the sites beneath it.

	GDL's locations are a tree. Somebody mapped to a region must reach the
	depots inside it, or the mapping offers them nothing.
	"""
	out = set()
	for site in sites:
		out.add(site)
		if frappe.db.get_value("Location", site, "is_group"):
			out.update(frappe.get_all(
				"Location", filters={"name": ("descendants of", site), "is_group": 0},
				pluck="name"))
	return sorted(out)
