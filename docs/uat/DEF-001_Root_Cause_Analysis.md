# DEF-001 — Root Cause Analysis

**Defect:** Fleet roles have no permissions on the standard DocTypes they operate
**Severity:** High · **Status:** Open, not fixed
**Investigated:** 4 November 2026, read-only, on `gdl-staging.localhost`

---

## 1. Correction to the initial finding

The Phase 1 report named **four** roles as affected, including **Fleet Manager**. That was
partly wrong, and the correction changes the whole analysis.

> **`Fleet Manager` is a standard ERPNext / HRMS role. It is not a GDL role.**

Evidence:

| Check | Result |
|---|---|
| Appears in standard app source | `erpnext/setup/doctype/vehicle/vehicle.json`, `erpnext/setup/doctype/driver/driver.json`, `hrms/hr/doctype/vehicle_log/vehicle_log.json`, `hrms/hr/report/vehicle_expenses/vehicle_expenses.json` |
| Those apps modified locally? | **No** — `git status` clean on erpnext, hrms and frappe |
| Created on the site | **2026-10-01 10:10:25** — when the site was built |
| GDL's roles created | **2026-11-02 13:04** — when `gdl_fleet_extension` installed |
| Listed in `setup/roles.py` → `GDL_FLEET_ROLES` | **No** — that list has 10 roles and Fleet Manager is not one |

So the earlier statement that the app ships "11 custom roles" was wrong. It ships **10**.
The eleventh is ERPNext's own.

**Why this matters more than a counting error:** the only reason Vehicle, Driver and Vehicle
Log are reachable at all today is that ERPNext happens to ship a role with the same name GDL
would have chosen. It is a **name collision, not a design**. The nine users who can touch
those forms do so on a permission GDL never granted.

---

## 2. The defect, precisely stated

| DocType | Permissions in force from | Fleet roles with a row |
|---|---|---|
| Vehicle | DocPerm (erpnext JSON) | **Fleet Manager only** *(standard)* |
| Driver | DocPerm (erpnext JSON) | **Fleet Manager only** *(standard, read-only)* |
| Vehicle Log | **Custom DocPerm** | **Fleet Manager only** *(standard)* |
| Asset Maintenance Log | DocPerm (erpnext JSON) | **none at all** |
| Asset Repair | DocPerm (erpnext JSON) | **none at all** |

Against the custom DocTypes, which are correct:

| DocType | Fleet roles with a row |
|---|---|
| Movement Order Request | 7 |
| POL Abstract | 5 |
| Movement Order, Fleet Part Issue, Vehicle Tyre | 4 each |
| Driver Assignment, Renewal Register | 3 each |
| GDL Fleet Settings | 2 |

**Not one of GDL's ten roles has a single permission row on a single standard DocType.**

---

## 3. Root cause

### 3.1 Where permissions come from in this application

| Source | Covers | Status |
|---|---|---|
| Each custom DocType's own `.json` → `permissions[]` | The 17 custom DocTypes | ✅ Complete |
| `setup/roles.py` | Creating the 10 roles | ✅ Works |
| **Anything granting those roles access to standard DocTypes** | Vehicle, Driver, Vehicle Log, Asset Maintenance Log, Asset Repair | ❌ **Does not exist** |

### 3.2 The code

`setup/roles.py` is 34 lines. It creates roles and stops:

```python
def create_roles():
    """Idempotent: creates any missing GDL fleet role."""
    for role_name in GDL_FLEET_ROLES:
        if frappe.db.exists("Role", role_name):
            continue
        frappe.get_doc({
            "doctype": "Role", "role_name": role_name,
            "desk_access": 1, "is_custom": 1,
        }).insert(ignore_permissions=True)
```

There is no `add_permission`, no `update_permission_property`, no Custom DocPerm creation —
anywhere in the application. A search across every `.py` file returns only a retired patch
and a test file.

### 3.3 Why it was never noticed

| Factor | Effect |
|---|---|
| Custom DocTypes carry their own permissions | Most of the module works, hiding the gap |
| ERPNext ships a `Fleet Manager` role | Vehicle, Driver and Vehicle Log appear to work |
| The 9 MTO/manager accounts hold Fleet Manager | Every manual test passed |
| The 606 automated tests insert with `ignore_permissions=True` or run as Administrator | Standard practice — and it bypasses exactly this |
| Nobody holds Fleet Driver, Fleet Administrator, Fleet Maintenance User, Fleet Store User or Fleet HR Approver | The gap never surfaced in use |

**This is a gap of omission, not a bug in written code.** Nothing is wrong; something is
absent. That is why no test caught it — there was no code to test.

### 3.4 What it is *not*

Ruled out by inspection:

| Hypothesis | Verdict |
|---|---|
| Standard app JSON was edited | **No** — git clean on erpnext, hrms, frappe |
| A failed migration | **No** — permissions are not patched |
| Fixtures not loaded | **No** — the app ships no fixture files; `fixtures` in hooks is for *export* |
| Property setters interfering | **No** — the 16 property setters are labels and options only |
| Permission query conditions hiding records | **No** — the app registers none |
| `has_permission` hook denying access | **No** — the one hook at `hooks.py:23` is `has_app_permission`, which controls **workspace visibility**, not DocType access |
| User Permission restrictions | **No** — only 2 exist site-wide, on an unrelated account |
| `if_owner` | **Not here.** It is used on Movement Order Request for Fleet User, correctly, and plays no part in this defect |
| Permission levels | **Not here.** Permlevel 1 on Movement Order Request is correct and verified |

---

## 4. A second finding, discovered during this investigation

### Vehicle Log is already "customised" — and that changes how the fix must be written

`Vehicle Log` has **Custom DocPerm** rows. In Frappe, the moment a DocType has any Custom
DocPerm row, `meta.permissions` reads **Custom DocPerm and ignores DocPerm entirely**.

| DocType | Custom DocPerm rows | Consequence for a fix |
|---|---|---|
| Vehicle Log | 2 | **A DocPerm added by JSON would be silently ignored** |
| Vehicle, Driver, Asset Maintenance Log, Asset Repair | 0 | Adding the first Custom DocPerm row converts the DocType — frappe copies the existing standard rows across first |

The two Vehicle Log Custom DocPerm rows were not created by GDL: `Fleet Manager` carries a
creation stamp of **2016-09-03** (it ships that way in HRMS) and `Employee Self Service`
of 2026-10-01.

**Implication:** the fix must use `frappe.permissions.add_permission()`, which writes Custom
DocPerm, and must not rely on editing any JSON. Section 2 of the Proposed Fix explains why.

---

## 5. A latent risk worth fixing at the same time

`hooks.py` exports roles as fixtures with a wildcard:

```python
{"dt": "Role", "filters": [["role_name", "like", "Fleet %"]]},
```

That pattern matches **`Fleet Manager`** — a standard ERPNext role. Exporting a standard
role into GDL's fixtures means a future `bench migrate` on another site could overwrite
ERPNext's own role definition with GDL's exported copy.

Nothing has gone wrong yet because no fixture files have been exported. The filter should
name GDL's ten roles explicitly rather than match a prefix.

---

## 6. The most reliable way to install permissions consistently

| Option | Reliable? | Why |
|---|---|---|
| Edit standard app JSON | ❌ Never | Violates "do not modify standard ERPNext"; lost on every upgrade |
| Role Permission Manager by hand on each site | ❌ No | Not versioned; dev, staging and production drift; nothing in git |
| Fixture export of Custom DocPerm | ⚠️ Fragile | Snapshot of one site's state; conflicts on re-import; hides intent |
| **Code in `after_migrate`, declarative and idempotent** | ✅ **Yes** | Versioned, reviewable, identical on every site, re-asserts itself on every migrate |

The fourth is also how the rest of this application already works — workflows,
notifications, custom fields, maintenance rules and the dashboard are all built
idempotently from code in `setup/`. The permission grant is the one thing that was never
written. The fix should match the pattern already in use, not introduce a new one.

---

## 7. Impact

| Who | Cannot |
|---|---|
| Fleet Driver | Record daily KM — the single most frequent fleet task. Also cannot read Vehicle or Driver. |
| Fleet Administrator | Create or edit a Vehicle or a Driver — the role documented as owning the masters |
| Fleet Maintenance User | Record a service or a repair |
| Fleet Store User | Read Vehicle while issuing parts |
| Fleet HR Approver | Read Vehicle while approving a fuel claim |
| **Anyone** | Record a service on Asset Maintenance Log — no fleet role has access |

**Not currently visible in production** only because those five roles are assigned to
nobody, and the people doing the work hold `Fleet Manager`. It will surface the moment GDL
assigns roles as the handbook describes — i.e. at go-live.

---

## 8. Conclusion

A single omission: the application never granted its own roles access to the standard
DocTypes it extends. It has been masked by a coincidental name collision with an ERPNext
role and by every test running with elevated privilege.

The fix is additive, low-risk and about 120 lines in one new setup module. It is specified
in `DEF-001_Proposed_Fix.md` and **has not been applied**.
