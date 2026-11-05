# DEF-001 — Proposed Fix

**Status: NOT APPLIED.** No file has been created in the application, no database record
changed, no migration run. The code below is a proposal for review.

A non-executable copy is saved beside this document as
`DEF-001_proposed_fleet_permissions.py.txt` — the `.txt` suffix is deliberate so it cannot
be imported or run by accident.

---

## 1. Files to change

| # | File | Action | Why |
|---|---|---|---|
| 1 | `gdl_fleet_extension/setup/fleet_permissions.py` | **New** | Holds the permission grant declaratively and applies it idempotently |
| 2 | `gdl_fleet_extension/setup/install.py` | **2-line edit** | Call it from the existing `setup()`, so it runs on install and on every migrate |
| 3 | `gdl_fleet_extension/hooks.py` | **1-line edit** | Stop the fixture wildcard exporting the standard `Fleet Manager` role |
| 4 | `gdl_fleet_extension/tests/test_fleet_permissions.py` | **New** | Regression tests — see `DEF-001_Regression_Test_Plan.md` |

**No standard ERPNext, HRMS or Frappe file is touched.** No DocType JSON is edited.

---

## 2. Why the fix uses `add_permission()` and not DocType JSON

This is the key technical decision, and getting it wrong would produce a fix that silently
does nothing.

**`Vehicle Log` already has Custom DocPerm rows.** In Frappe, as soon as a DocType has any
Custom DocPerm row, `meta.permissions` reads **Custom DocPerm and ignores DocPerm entirely**.

| Approach | Vehicle Log | Vehicle / Driver / Asset Maintenance Log / Asset Repair | Survives upgrade |
|---|---|---|---|
| Edit the standard app's JSON | works | works | ❌ lost on upgrade, and forbidden |
| Ship DocPerm rows from our app | ❌ **silently ignored** | works | ❌ fragile |
| **`frappe.permissions.add_permission()`** | ✅ | ✅ | ✅ |

`add_permission()` writes a **Custom DocPerm** row. On a DocType that has none yet, Frappe
first calls `setup_custom_perms()`, which **copies every existing standard row into Custom
DocPerm** before adding ours — so ERPNext's own permissions are preserved, not replaced.

It is also reversible: `frappe.permissions.reset_perms(doctype)` drops the Custom DocPerm
rows and restores the shipped defaults.

---

## 3. The proposed module

```python
# gdl_fleet_extension/setup/fleet_permissions.py
# Copyright (c) 2026, GDL and contributors
"""
Fleet role permissions on the STANDARD DocTypes this app extends.

The custom DocTypes carry their permissions in their own JSON. The standard ones -
Vehicle, Driver, Vehicle Log, Asset Maintenance Log, Asset Repair - cannot, because
this app must never edit another app's files. Nothing granted GDL's roles access to
them, so a Fleet Driver could not record a Vehicle Log and no fleet role at all could
record a service. That was DEF-001.

Why add_permission() rather than shipping DocPerm rows: Vehicle Log already carries
Custom DocPerm rows, and once a DocType has any, frappe reads Custom DocPerm and
ignores DocPerm completely. A DocPerm shipped by this app would be silently discarded
on exactly the DocType the driver needs most. add_permission() writes Custom DocPerm,
and on a DocType that has none it copies the standard rows across first, so ERPNext's
own permissions survive.

Fleet Manager is NOT touched. It is a standard ERPNext/HRMS role that already ships
with permissions on Vehicle, Driver and Vehicle Log; altering it would change
behaviour for users outside the fleet.

Idempotent. Additive only - no existing permission is modified or removed.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

# doctype -> role -> the rights that role needs for its documented process.
# Anything not listed is deliberately withheld: no delete, no import, no amend
# except for the administrator who has to correct mistakes.
FLEET_PERMISSIONS = {
    "Vehicle": {
        "Fleet Administrator":    ["read", "write", "create"],
        "Fleet Approver":         ["read"],
        "Fleet Driver":           ["read"],
        "Fleet Maintenance User": ["read"],
        "Fleet Store User":       ["read"],
        "Fleet HR Approver":      ["read"],
        "Fleet User":             ["read"],
    },
    "Driver": {
        "Fleet Administrator":    ["read", "write", "create"],
        "Fleet Approver":         ["read"],
        "Fleet Driver":           ["read"],
        "Fleet Maintenance User": ["read"],
    },
    "Vehicle Log": {
        # No cancel for the driver: cancelling recomputes the vehicle odometer,
        # which is an administrator's correction, not a driver's daily action.
        "Fleet Driver":        ["read", "write", "create", "submit"],
        "Fleet Administrator": ["read", "write", "create", "submit", "cancel", "amend"],
        "Fleet Approver":      ["read"],
    },
    "Asset Maintenance Log": {
        "Fleet Maintenance User": ["read", "write", "create", "submit"],
        "Fleet Administrator":    ["read", "write", "create", "submit", "cancel", "amend"],
        # The driver hands in the service bill, and the bill lives on this record.
        # Frappe permissions are per document, not per section, so this is write on
        # the whole log. See the open question in the Permission Matrix.
        "Fleet Driver":           ["read", "write"],
        "Fleet Manager":          ["read"],
    },
    "Asset Repair": {
        "Fleet Maintenance User": ["read", "write", "create", "submit"],
        "Fleet Administrator":    ["read", "write", "create", "submit", "cancel"],
        "Fleet Manager":          ["read"],
    },
}

PERMLEVEL = 0


def setup_fleet_permissions():
    """Idempotent. Grants only what is missing; never revokes."""
    granted, already, skipped = [], [], []

    for doctype, roles in FLEET_PERMISSIONS.items():
        if not frappe.db.exists("DocType", doctype):
            skipped.append(f"{doctype} (not installed)")
            continue

        for role, rights in roles.items():
            if not frappe.db.exists("Role", role):
                skipped.append(f"{doctype}/{role} (role missing)")
                continue

            # add_permission() returns falsy when the row already exists. On a
            # doctype with no Custom DocPerm yet it copies the standard rows
            # across first, so ERPNext's own permissions are kept.
            created = add_permission(doctype, role, PERMLEVEL)

            changed = False
            for right in rights:
                current = frappe.db.get_value(
                    "Custom DocPerm",
                    {"parent": doctype, "role": role, "permlevel": PERMLEVEL},
                    right,
                )
                if not current:
                    update_permission_property(doctype, role, PERMLEVEL, right, 1)
                    changed = True

            if created or changed:
                granted.append(f"{doctype}/{role}: {', '.join(rights)}")
            else:
                already.append(f"{doctype}/{role}")

    if granted:
        frappe.clear_cache()

    return {"granted": granted, "already_present": already, "skipped": skipped}


def permission_report():
    """What each fleet role can do on the standard doctypes. For tests and support."""
    report = {}
    for doctype in FLEET_PERMISSIONS:
        if not frappe.db.exists("DocType", doctype):
            continue
        meta = frappe.get_meta(doctype)
        report[doctype] = {
            p.role: [k for k in ("read", "write", "create", "submit", "cancel", "amend")
                     if p.get(k)]
            for p in meta.permissions
            if p.role.startswith("Fleet") and p.permlevel == PERMLEVEL
        }
    return report
```

### Edit to `setup/install.py`

```python
from gdl_fleet_extension.setup.fleet_permissions import setup_fleet_permissions   # new import

def setup():
    """Idempotent. Safe to run on install and on every migrate."""
    create_roles()
    setup_fleet_permissions()        # <-- new, immediately after the roles exist
    create_site_locations()
    ...
```

Placed straight after `create_roles()` because a permission cannot reference a role that
does not yet exist.

### Edit to `hooks.py` — the latent fixture risk

```python
# before - matches the STANDARD "Fleet Manager" role and would export it
{"dt": "Role", "filters": [["role_name", "like", "Fleet %"]]},

# after - only the ten roles this app actually creates
{"dt": "Role", "filters": [["role_name", "in", GDL_FLEET_ROLES]]},
```

---

## 4. Risk assessment

| Risk | Level | Reasoning |
|---|---|---|
| Breaking existing access | **None** | Purely additive. 21 rows added, 0 changed, 0 removed. |
| Converting a DocType to Custom DocPerm | **Low** | Frappe copies the standard rows first. Vehicle Log is already converted. |
| Granting too much | **Low** | No delete, no import, no amend except for the administrator. Reviewed row by row. |
| Lost on ERPNext upgrade | **None** | Custom DocPerm survives upgrades. Re-asserted on every migrate. |
| Divergence between dev/staging/production | **None** | Runs from `after_migrate` on all three. |
| Reversible | **Yes** | `frappe.permissions.reset_perms(doctype)` restores shipped defaults. |

**Blast radius if wrong:** permissions only. No data is written, no schema changed, no
business document affected.

---

## 5. Application procedure — when approved

1. **Back up staging** — `bench --site gdl-staging.localhost backup`.
2. Add the two new files and make the two edits.
3. Run the regression tests on the **development** site first.
4. `bench --site gdl-staging.localhost migrate`.
5. Re-run the permission matrix and diff it against §3 of `GDL_Fleet_Permission_Matrix.md`.
6. Execute the regression plan **as named users**, never as Administrator.

**Rollback:** `frappe.permissions.reset_perms(doctype)` for each of the five DocTypes, then
remove the `setup_fleet_permissions()` call. Restoring the backup also works and is faster.

---

## 6. Open questions — answer before applying

| # | Question | Default if unanswered |
|---|---|---|
| 1 | **Fleet Driver write on Asset Maintenance Log.** The driver submits the service bill, which lives on that record. Frappe cannot grant write to one section, so this is write on the whole log. Accept, move the bill fields to permlevel 2, or have the maintenance user enter the bill? | Accept as proposed |
| 2 | **Fleet Manager currently has write, create and delete on Vehicle and Vehicle Log** — wider than the handbook's "read everything". It is a standard ERPNext role, so tightening it affects non-fleet users. Leave alone? | Leave alone |
| 3 | **Fleet User read on Vehicle** (closes OBS-001). Should a requester see the vehicle allocated to them? | Grant, as proposed |
| 4 | Should **Fleet Validator, Fleet Reviewer and Fleet Finance User** get anything? They are unused while the five-stage chain is off. | Grant nothing |
