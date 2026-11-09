# Copyright (c) 2026, GDL and contributors
"""
Fleet role permissions on the STANDARD DocTypes this app extends, and the
permission levels that keep money away from the roles that do not need it.

DEF-001: the custom DocTypes carry permissions in their own JSON; the standard
ones cannot, because this app must never edit another app's files. Nothing ever
granted GDL's roles access to Vehicle, Driver, Vehicle Log, Asset Maintenance Log
or Asset Repair. A Fleet Driver could not record a Vehicle Log and no fleet role
at all could record a service.

Two things to know before changing anything here.

1. add_permission() rather than shipping DocPerm rows. Vehicle Log already carries
   Custom DocPerm rows, and once a DocType has any, frappe reads Custom DocPerm and
   ignores DocPerm entirely - a DocPerm shipped by this app would be silently
   discarded on exactly the DocType the driver needs most. add_permission() writes
   Custom DocPerm, and on a DocType with none it copies the standard rows across
   first, so ERPNext's own permissions survive.

2. PRESERVING rows. Raising a field to permlevel 1 removes it from every role
   without a level-1 row - including Delivery Manager, Delivery User and
   Manufacturing User, which belong to other modules. The rows marked "preserve"
   below exist for no other reason than to leave those roles exactly as they were.
   Delete one and you silently take access away from someone outside the fleet.

Fleet Manager's level-0 rows are never touched: it is a standard ERPNext role.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.permissions import add_permission, update_permission_property
from frappe.permissions import rights as ALL_RIGHTS

MODULE = "GDL Fleet"

# doctype -> permlevel -> role -> rights
FLEET_PERMISSIONS = {
    "Vehicle": {
        0: {
            "Fleet Administrator":    ["read", "write", "create"],
            "Fleet Approver":         ["read"],
            "Fleet Driver":           ["read"],
            "Fleet Maintenance User": ["read"],
            "Fleet Store User":       ["read"],
            "Fleet HR Approver":      ["read"],
            "Fleet User":             ["read"],
        },
        1: {
            "Fleet Administrator": ["read", "write"],
            # preserve - these three hold level 0 today and must not lose
            # vehicle_value, asset or lessor when those move to level 1
            "Fleet Manager":       ["read", "write"],
            "Delivery Manager":    ["read", "write"],
            "Delivery User":       ["read"],
        },
    },
    "Driver": {
        0: {
            "Fleet Administrator":    ["read", "write", "create"],
            "Fleet Approver":         ["read"],
            "Fleet Driver":           ["read"],
            "Fleet Maintenance User": ["read"],
        },
    },
    "Vehicle Log": {
        0: {
            # no cancel for the driver: cancelling recomputes the vehicle
            # odometer, which is a correction, not a daily action
            "Fleet Driver":        ["read", "write", "create", "submit"],
            "Fleet Administrator": ["read", "write", "create", "submit", "cancel", "amend"],
            "Fleet Approver":      ["read"],
            # OBS-003: a maintenance user judging whether a service is due needs
            # to see how the vehicle has actually been running. Read only - they
            # record services, not journeys.
            "Fleet Maintenance User": ["read"],
        },
        # GDL: a driver recording the day's kilometres has no use for the site,
        # cost centre, department, project or task. Those are how FINANCE files
        # the journey, not how the driver records it, and they sat as five empty
        # boxes between the driver and the odometer reading.
        #
        # Every role below already reached these fields at level 0. Raising the
        # fields takes them from anyone without a level-1 row, so each of those
        # roles is listed again here to keep exactly what it had. Fleet Driver
        # is the one deliberately absent - that is the whole change.
        1: {
            "Fleet Administrator":    ["read", "write"],
            "Fleet Manager":          ["read", "write"],   # preserve - standard role
            "Fleet Approver":         ["read"],
            "Fleet Maintenance User": ["read"],
        },
    },
    "Asset Maintenance Log": {
        0: {
            "Fleet Driver":           ["read", "write", "create", "submit"],
            "Fleet Maintenance User": ["read", "write", "create", "submit"],
            "Fleet Administrator":    ["read", "write", "create", "submit", "cancel", "amend"],
            "Fleet Manager":          ["read"],
            # OBS-005: MTOs no longer hold Fleet Manager, so they need sight of
            # a service record in their own right. Level 0 only - the costs stay
            # at level 1, which is the whole point of removing Fleet Manager.
            "Fleet Approver":         ["read"],
        },
        1: {
            "Fleet Maintenance User": ["read", "write"],
            "Fleet Administrator":    ["read", "write"],
            "Fleet Manager":          ["read"],
            "Manufacturing User":     ["read", "write"],   # preserve
        },
        2: {
            "Fleet Administrator":    ["read", "write"],
            "Fleet Maintenance User": ["read"],
            "Fleet Manager":          ["read"],
            "Manufacturing User":     ["read", "write"],   # preserve
        },
    },
    "Asset Repair": {
        0: {
            "Fleet Maintenance User": ["read", "write", "create", "submit"],
            "Fleet Administrator":    ["read", "write", "create", "submit", "cancel"],
            "Fleet Manager":          ["read"],
            # OBS-004: a driver should be able to see a breakdown logged against
            # a vehicle they drive. Read only - recording a repair stays with
            # the maintenance user.
            "Fleet Driver":           ["read"],
        },
    },
    # A Supplier link that nobody may look up is a form nobody can fill in.
    #
    # POL Entry.supplier is the routing key for a fuel claim, and Asset
    # Maintenance Log.service_provider is the workshop that did the work. Both
    # are Link fields on Supplier, and frappe refuses a link lookup without
    # "select" on the target - so a driver picking a fuel provider, and a
    # maintenance user naming a workshop, both got "Insufficient Permission for
    # Supplier" and could go no further.
    #
    # "select" rather than "read" on purpose. It is the narrow right frappe
    # provides for exactly this: the field can look a supplier up and show it,
    # and the role still gets no Supplier list, report or export. Read is
    # implied BY select, never the other way round, so this grants the least
    # that makes the form work.
    #
    # The POL dropdown is narrowed further in the form itself - only the two
    # configured fuel providers are offered. The workshop list is not narrowed;
    # a service can be done by any supplier.
    "Supplier": {
        0: {
            "Fleet Driver":           ["select"],
            "Fleet Maintenance User": ["select"],
            "Fleet Approver":         ["select"],
            "Fleet HR Approver":      ["select"],
            # The administrator configures which suppliers are the fuel
            # providers, so they do get the list itself.
            "Fleet Administrator":    ["select", "read"],
        },
    },
}

# ---------------------------------------------------------------------------
# Link lookups
#
# A Link field is dead to a role that cannot "select" its target. Frappe refuses
# the lookup before any form-level filter runs, and the user is shown
# "Insufficient Permission for <doctype>" with no way forward. This was not one
# bug: a driver could not pick a fuel provider, a Location or a Service Type; an
# MTO could not pick a Location, Cost Center, Project, Department, Task or
# Employee on a movement order request. Every fleet role was blocked somewhere
# on a form it is supposed to fill.
#
# The list below is measured, not guessed: for each role, every EDITABLE and
# VISIBLE Link field on every doctype that role may write, whose target the role
# could not reach. Read-only and hidden links are excluded - they never trigger
# a lookup, so granting for them would be reach without purpose.
#
# "select" only. It lets a field resolve and display a link and nothing else:
# no list, no report, no export, no create, no write. Read is implied BY select,
# never the reverse.
#
# COST, worth knowing before adding to this list: add_permission() calls
# setup_custom_perms(), which copies a doctype's standard DocPerm rows into
# Custom DocPerm the first time anything is added. From then on frappe reads
# Custom DocPerm for that doctype and ignores DocPerm - so a future ERPNext
# change to its STANDARD permissions will not reach this site. That now applies
# to the core doctypes named here. frappe.permissions.reset_perms(doctype)
# undoes it for any one of them.
LINK_SELECT = {
    # --- the service record and the fuel abstract ---------------------------
    "Location":                ["Fleet Driver", "Fleet User", "Fleet Approver",
                                "Fleet HR Approver", "Fleet Maintenance User",
                                "Fleet Store User", "Fleet Administrator"],
    "Vehicle Service Item":    ["Fleet Driver", "Fleet Maintenance User",
                                "Fleet Administrator"],
    "Movement Order":          ["Fleet Driver"],
    # --- accounting and HR dimensions, present on nearly every form ---------
    "Cost Center":             ["Fleet Driver", "Fleet User", "Fleet Approver",
                                "Fleet HR Approver", "Fleet Maintenance User",
                                "Fleet Store User", "Fleet Administrator"],
    "Project":                 ["Fleet Driver", "Fleet User", "Fleet Approver",
                                "Fleet HR Approver", "Fleet Maintenance User",
                                "Fleet Store User", "Fleet Administrator"],
    "Department":              ["Fleet Driver", "Fleet User", "Fleet Approver",
                                "Fleet HR Approver", "Fleet Administrator"],
    "Task":                    ["Fleet Driver", "Fleet User", "Fleet Approver",
                                "Fleet Administrator"],
    "Employee":                ["Fleet Driver", "Fleet User", "Fleet Approver",
                                "Fleet Administrator"],
    "Driver":                  ["Fleet User", "Fleet HR Approver", "Fleet Store User"],
    "User":                    ["Fleet User", "Fleet Approver", "Fleet Administrator"],
    "Fleet Vehicle Type":      ["Fleet Approver"],
    # --- parts, tyres and repairs -------------------------------------------
    "Item":                    ["Fleet Store User", "Fleet Maintenance User",
                                "Fleet Administrator"],
    "Warehouse":               ["Fleet Store User", "Fleet Maintenance User",
                                "Fleet Administrator"],
    "UOM":                     ["Fleet Administrator"],
    "Serial and Batch Bundle": ["Fleet Maintenance User", "Fleet Administrator"],
    "Expense Claim":           ["Fleet Store User", "Fleet Maintenance User",
                                "Fleet Administrator"],
    "Asset":                   ["Fleet Maintenance User", "Fleet Administrator"],
    "Account":                 ["Fleet Maintenance User", "Fleet Administrator"],
    "Purchase Invoice":        ["Fleet Maintenance User", "Fleet Administrator"],
    "Company":                 ["Fleet Maintenance User", "Fleet Administrator"],
    "Address":                 ["Fleet Administrator"],
}

for _doctype, _roles in LINK_SELECT.items():
    _level0 = FLEET_PERMISSIONS.setdefault(_doctype, {}).setdefault(0, {})
    for _role in _roles:
        _level0[_role] = sorted(set(_level0.get(_role, [])) | {"select"})


# Doctypes where the rights listed above are the WHOLE grant, not a floor.
#
# add_permission() creates a row with read=1, and Custom DocPerm's own default
# adds export=1 - so asking for "select" alone quietly produced a role that
# could browse AND export the supplier ledger. For the doctypes named here every
# right not listed above is forced to 0, so the grant is what it says it is.
#
# Only rows for the roles listed above are touched. A role that already had a
# row keeps it untouched: this never reaches outside the fleet.
EXACT_RIGHTS = {"Supplier"} | set(LINK_SELECT)

# ALL_RIGHTS is frappe's own `rights` tuple, imported under another name on
# purpose: the loop below binds `rights` to each role's own list, so importing
# it as `rights` silently shadowed it and the grant stayed as wide as ever.

# Standard fields whose permlevel this app raises. GDL's own custom fields carry
# their permlevel on the Custom Field record itself; a standard field cannot, so
# it needs a Property Setter.
STANDARD_FIELD_PERMLEVELS = {
    "Vehicle": {"vehicle_value": 1},
}


def setup_fleet_permissions():
    """Idempotent and additive. Grants what is missing; never revokes."""
    granted, already, skipped = [], [], []

    for doctype, levels in FLEET_PERMISSIONS.items():
        if not frappe.db.exists("DocType", doctype):
            skipped.append(f"{doctype} (not installed)")
            continue

        for permlevel, roles in levels.items():
            for role, rights in roles.items():
                if not frappe.db.exists("Role", role):
                    skipped.append(f"{doctype}/{role} (role missing)")
                    continue

                created = add_permission(doctype, role, permlevel)

                wanted = set(rights)
                if doctype in EXACT_RIGHTS:
                    # Grant exactly these. Run every time, so a row created
                    # before this rule existed corrects itself on migrate.
                    expected = {r: (1 if r in wanted else 0) for r in ALL_RIGHTS}
                else:
                    expected = {r: 1 for r in wanted}

                changed = False
                for right, want in expected.items():
                    current = frappe.db.get_value(
                        "Custom DocPerm",
                        {"parent": doctype, "role": role, "permlevel": permlevel},
                        right,
                    )
                    if int(current or 0) != want:
                        update_permission_property(doctype, role, permlevel, right, want)
                        changed = True

                (granted if (created or changed) else already).append(
                    f"{doctype}[{permlevel}]/{role}"
                )

    for doctype, fields in STANDARD_FIELD_PERMLEVELS.items():
        if not frappe.db.exists("DocType", doctype):
            continue
        for fieldname, permlevel in fields.items():
            if frappe.get_meta(doctype).get_field(fieldname) is None:
                skipped.append(f"{doctype}.{fieldname} (field missing)")
                continue
            if frappe.get_meta(doctype).get_field(fieldname).permlevel == permlevel:
                already.append(f"{doctype}.{fieldname}")
                continue

            make_property_setter(
                doctype, fieldname, "permlevel", permlevel, "Int",
                for_doctype=False, validate_fields_for_doctype=False,
            )
            frappe.db.set_value(
                "Property Setter",
                {"doc_type": doctype, "field_name": fieldname, "property": "permlevel"},
                "module", MODULE,
            )
            granted.append(f"{doctype}.{fieldname} -> permlevel {permlevel}")

    if granted:
        frappe.clear_cache()

    return {"granted": granted, "already_present": already, "skipped": skipped}


def permission_report():
    """What each role can do, per level. Used by the regression tests."""
    report = {}
    for doctype in FLEET_PERMISSIONS:
        if not frappe.db.exists("DocType", doctype):
            continue
        report[doctype] = {}
        for p in frappe.get_meta(doctype).permissions:
            # "select" belongs here: it is the only right the Supplier rows
            # carry, so a report without it shows them as empty.
            rights = [k for k in ("select", "read", "write", "create", "submit",
                                  "cancel", "amend", "delete", "import") if p.get(k)]
            report[doctype].setdefault(p.permlevel, {})[p.role] = rights
    return report
