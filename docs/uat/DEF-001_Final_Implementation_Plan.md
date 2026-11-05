# DEF-001 — Final Implementation Plan

**Status: NOT APPLIED.** No application file created or edited, no database record changed,
no migration run. Supersedes `DEF-001_Proposed_Fix.md`.

---

## 1. Files to change — seven, none of them standard

| # | File | Action | Why |
|---|---|---|---|
| 1 | `setup/fleet_permissions.py` | **New** | The 33 permission rows + the one standard-field permlevel, idempotent |
| 2 | `setup/vehicle_fields.py` | Edit 2 dicts | `permlevel: 1` on `asset`, `lessor` |
| 3 | `setup/maintenance_purchasing_fields.py` | Edit ~16 dicts | `permlevel: 1` on bill/cost, `2` on the purchasing trail |
| 4 | `setup/maintenance_fields.py` | Edit ~5 dicts | `permlevel: 1` on `labour_cost`, `parts_cost`, `total_cost`, `cost_center`, `project` |
| 5 | `gdl_fleet/doctype/fleet_service_item/fleet_service_item.json` | Edit 2 fields | `permlevel: 1` on `cost`, `invoice_reference` — **closes the child-grid hole** |
| 6 | `setup/install.py` | +2 lines | Call `setup_fleet_permissions()` after `create_roles()` |
| 7 | `hooks.py` | 1 line | Fixture wildcard fix |
| 8 | `patches/v1_5/apply_field_permlevels.py` + `patches.txt` | **New** | `create_custom_fields()` does not update an existing field's permlevel — a patch must |
| 9 | `tests/test_fleet_permissions.py` | **New** | The 18 regression tests |

**Zero standard ERPNext / HRMS / Frappe files touched.**

---

## 2. Why a patch is needed as well (#8)

`frappe.custom.doctype.custom_field.custom_field.create_custom_fields()` **creates missing
fields and leaves existing ones alone**. Every field in question already exists on staging,
so editing the setup dicts alone would change nothing on an installed site — it would only
affect a fresh install. The patch applies the permlevel to the Custom Field records that are
already there.

`vehicle_value` is a **standard erpnext field**, so it cannot be changed by editing a Custom
Field. It needs a **Property Setter**, which `setup_fleet_permissions()` creates — the same
mechanism the app already uses for its 16 existing label and option overrides.

---

## 3. The permission module

```python
# gdl_fleet_extension/setup/fleet_permissions.py
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
        },
    },
    "Asset Maintenance Log": {
        0: {
            "Fleet Driver":           ["read", "write", "create", "submit"],
            "Fleet Maintenance User": ["read", "write", "create", "submit"],
            "Fleet Administrator":    ["read", "write", "create", "submit", "cancel", "amend"],
            "Fleet Manager":          ["read"],
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
        },
    },
}

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

                changed = False
                for right in rights:
                    current = frappe.db.get_value(
                        "Custom DocPerm",
                        {"parent": doctype, "role": role, "permlevel": permlevel},
                        right,
                    )
                    if not current:
                        update_permission_property(doctype, role, permlevel, right, 1)
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
            rights = [k for k in ("read", "write", "create", "submit", "cancel", "amend",
                                  "delete", "import") if p.get(k)]
            report[doctype].setdefault(p.permlevel, {})[p.role] = rights
    return report
```

### `setup/install.py`

```python
from gdl_fleet_extension.setup.fleet_permissions import setup_fleet_permissions   # new

def setup():
    create_roles()
    setup_fleet_permissions()     # <-- immediately after; a permission needs its role
    create_site_locations()
    ...
```

### `hooks.py` — the fixture wildcard

```python
# before - "Fleet %" also matches the STANDARD "Fleet Manager" role
{"dt": "Role", "filters": [["role_name", "like", "Fleet %"]]},

# after - the ten roles this app actually creates, listed literally.
# NOT imported from setup.roles: hooks.py is read very early in the boot and
# importing an app module from it invites a circular import.
{"dt": "Role", "filters": [["role_name", "in", [
    "Fleet Administrator", "Fleet User", "Fleet Driver", "Fleet Validator",
    "Fleet Reviewer", "Fleet Approver", "Fleet Maintenance User",
    "Fleet Store User", "Fleet Finance User", "Fleet HR Approver",
]]]},
```

**Verified:** `"Fleet Manager"` is **not** in that list, so it can no longer be exported
into GDL's fixtures.

### `patches/v1_5/apply_field_permlevels.py`

```python
"""create_custom_fields() creates missing fields and leaves existing ones alone,
so the permlevel changes in the setup modules reach a fresh install but not a
site that already has the fields. This applies them once to what is there."""

import frappe

PERMLEVELS = {
    "Asset Maintenance Log": {
        1: ["service_provider", "labour_cost", "parts_cost", "total_cost",
            "bill_no", "bill_date", "bill_attachment", "cost_center", "project"],
        2: ["bill_status", "submitted_by", "submission_date", "approved_by",
            "rejection_reason", "purchase_order", "purchase_invoice",
            "purchasing_status", "purchasing_message", "payment_status"],
    },
    "Vehicle": {1: ["asset", "lessor"]},
}

def execute():
    changed = 0
    for doctype, levels in PERMLEVELS.items():
        for permlevel, fieldnames in levels.items():
            for fieldname in fieldnames:
                name = frappe.db.get_value(
                    "Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
                if not name:
                    continue
                if frappe.db.get_value("Custom Field", name, "permlevel") == permlevel:
                    continue
                frappe.db.set_value("Custom Field", name, "permlevel", permlevel)
                changed += 1
    if changed:
        frappe.clear_cache()
    print(f"  Applied permlevel to {changed} custom field(s).")
```

`Fleet Service Item.cost` and `.invoice_reference` are fields of a **GDL DocType**, so the
JSON edit alone is enough — `bench migrate` syncs it.

---

## 4. Verification that the change is additive

To be run **before and after** applying, and diffed:

```python
# read-only snapshot of every permission on the five doctypes
{(dt, p.role, p.permlevel): [k for k in PERM_TYPES if p.get(k)]
 for dt in FLEET_PERMISSIONS
 for p in frappe.get_meta(dt).permissions}
```

**Pass criterion:** every key present in the *before* snapshot is present in the *after*
snapshot with an **identical or larger** rights list. Any key that disappears, or any
rights list that shrinks, fails the change.

Covered by regression test **RT-10**.

---

## 5. v16 compatibility — verified on this site

| API | Present | Signature as used |
|---|---|---|
| `frappe.permissions.add_permission` | ✅ | `(doctype, role, permlevel=0, ptype=None)` |
| `frappe.permissions.update_permission_property` | ✅ | `(doctype, role, permlevel, ptype, value=None, validate=True, if_owner=0)` |
| `frappe.permissions.reset_perms` | ✅ | `(doctype)` — rollback |
| `frappe.permissions.setup_custom_perms` | ✅ | `(parent)` — called internally by `add_permission` |
| `make_property_setter` | ✅ | already used 16 times by this app |
| Child-table permlevel honoured | ✅ | `Document.get_permlevel_access` and `reset_values_if_no_permlevel_access` both present |

Versions: frappe **16.32.0**, erpnext **16.33.0**, hrms **16.17.0**.

---

## 6. The 18 regression tests — reviewed

Unchanged from `DEF-001_Regression_Test_Plan.md` except where the permlevel decisions add
coverage:

| # | Test | Change |
|---|---|---|
| RT-01…RT-09 | The nine you specified | unchanged |
| RT-10 | **Nothing revoked** — before/after snapshot | **now the most important test**, because permlevels are subtractive |
| RT-11 | Fleet Manager level-0 rows byte-identical to ERPNext's | unchanged |
| RT-12 | Idempotent — second run grants nothing | unchanged |
| RT-13 | Survives `bench migrate` | unchanged |
| RT-14 | No `delete` for any GDL role | unchanged |
| RT-15 | No `import` for any GDL role | unchanged |
| RT-16 | Movement Order Request permlevel 1 unchanged | unchanged |
| RT-17 | `if_owner` on Movement Order Request unchanged | unchanged |
| RT-18 | Live matrix equals the specification | extended to all three levels |

### Four tests added for the permlevel work

| # | Test | Asserts |
|---|---|---|
| **RT-19** | Fleet Driver cannot read or write any level-1 field on Asset Maintenance Log | Load a log as the driver → `labour_cost`, `parts_cost`, `bill_no`, `bill_attachment` all absent or unwritable |
| **RT-20** | **Fleet Driver cannot write `cost` in the service-items grid** | The child-table hole. Set `service_items[0].cost` as the driver, save, reload → value unchanged |
| **RT-21** | Delivery Manager, Delivery User and Manufacturing User keep every field they had | The preserving rows do their job |
| **RT-22** | The bill process still completes | Driver records the service → Maintenance User enters the bill and submits → approver approves. End to end, as named users |

**RT-20 and RT-22 are the two that would catch a wrong implementation.** RT-20 proves the
restriction is real rather than cosmetic; RT-22 proves it did not break the business.

---

## 7. Risk

| Risk | Level | Mitigation |
|---|---|---|
| A role silently loses a field | **Medium** → **Low** | 5 preserving rows + RT-10 + RT-21; before/after snapshot diffed |
| Driver can still edit costs in the grid | **Medium** → **Low** | Child-table fields moved; RT-20 proves it |
| Bill process breaks | **Medium** → **Low** | `submit_bill()` checks doctype write, not field write — verified in source; RT-22 proves it |
| Affects other ERPNext modules | **Low** | Only Delivery and Manufacturing roles gain preserving rows; net access identical |
| Lost on upgrade | **None** | Custom DocPerm and Property Setters survive; re-asserted every migrate |
| Rollback | — | `reset_perms()` per DocType, revert the patch, or restore the backup |

**Blast radius:** permissions and field visibility only. No business document, no schema,
no accounting.

---

## 8. Application sequence — on your approval

1. `bench --site gdl-staging.localhost backup`
2. Capture the **before** permission snapshot (§4)
3. Make the nine changes
4. Run the regression suite on **development** — expect 606 + ~25 passing
5. `bench --site erpnext16.localhost migrate`, re-run the full suite
6. `bench --site gdl-staging.localhost migrate`
7. Capture the **after** snapshot and diff — **must be additive only**
8. Re-run RT-01…RT-22 on staging as named users
9. Update `GDL_Fleet_Handbook.html` Part 7 for the changed bill process
10. Update `GDL_Fleet_02_Business_Process_Guide.md` §I and the role table

Steps 9 and 10 are not optional. The documentation currently describes a process that this
change alters.

---

## 9. Two things I need you to confirm

| # | Point | Why it needs you |
|---|---|---|
| **1** | **The bill is now entered by the Maintenance User, not the driver.** Decision 1 makes this unavoidable — a driver who cannot touch cost fields cannot enter a bill. | It is a real change to how GDL works, and the handbook says otherwise today |
| **2** | **Five preserving rows are added for Delivery Manager, Delivery User and Manufacturing User.** Without them those roles lose fields they have now. | Decision 2 says do not affect other modules. These rows *prevent* an effect — but they do add rows to standard roles. If you would rather not, the alternative is to leave the fields at level 0, which means decisions 1 and 3 cannot be delivered. |

**Still not applied. Awaiting your approval.**
