# GDL Fleet — Defect Register

**Opened:** 4 November 2026 · **Last updated:** 4 November 2026 (after the DEF-001 fix)
**Site:** `gdl-staging.localhost`

| ID | Severity | Title | Status |
|---|---|---|---|
| **DEF-001** | High | Fleet roles had no permissions on the standard DocTypes they operate | ✅ **CLOSED** — fixed and verified on staging |
| **OBS-001** | Low | Fleet User could not read the Vehicle master | ✅ **CLOSED** — resolved by the DEF-001 fix |
| **OBS-002** | Info | Driving Licence Expiry alert followed the renewal setting | ✅ **CLOSED** 4 Nov — own setting, 30 days |
| **OBS-003** | Info | Fleet Maintenance User had no access to Vehicle Log | ✅ **CLOSED** 4 Nov — read granted |
| **OBS-004** | Info | Fleet Driver had no access to Asset Repair | ✅ **CLOSED** 4 Nov — read granted |
| **OBS-005** | Info | Every MTO also held the standard `Fleet Manager` role, so saw all financial fields | ✅ **CLOSED** 4 Nov — role removed, rights replaced |

| Severity | Open | Closed | Total |
|---|---|---|---|
| High | 0 | 1 | 1 |
| Medium | 0 | 0 | 0 |
| Low | 0 | 1 | 1 |
| Info | 0 | 4 | 4 |
| **Total** | **0** | **6** | **6** |

**Every defect and observation raised in this UAT is closed.**

---

## DEF-001 — ✅ CLOSED

### Summary

| Field | Detail |
|---|---|
| **Severity / Priority** | High / High |
| **Found** | 4 Nov 2026, Phase 1 read-only permission matrix (test R-05) |
| **Fixed** | 4 Nov 2026 |
| **Verified on staging** | 4 Nov 2026 |
| **Status** | **CLOSED** |

### What was wrong

The application's custom DocTypes carried correct fleet-role permissions. Its extensions to
**standard** DocTypes did not — `setup/roles.py` created ten roles and granted them nothing.
A Fleet Driver could not record a Vehicle Log, a Fleet Administrator could not create a
Vehicle or Driver, and **no fleet role at all** could record a service.

It was masked by a coincidence: **`Fleet Manager` is a standard ERPNext/HRMS role** that
already ships with permissions on Vehicle, Driver and Vehicle Log, and every tester held it.

### Root cause

A gap of **omission**, not a bug. Nothing was wrong; something was absent. Full analysis in
`DEF-001_Root_Cause_Analysis.md`.

### Resolution

| File | Change |
|---|---|
| `setup/fleet_permissions.py` | **New** — 33 permission rows, declarative and idempotent |
| `setup/vehicle_fields.py` | `permlevel: 1` on `asset`, `lessor` |
| `setup/maintenance_fields.py` | `permlevel: 1` on the cost fields |
| `setup/maintenance_purchasing_fields.py` | `permlevel: 1` / `2` on bill and purchasing fields |
| `gdl_fleet/doctype/fleet_service_item/fleet_service_item.json` | `permlevel: 1` on `cost`, `invoice_reference` |
| `setup/install.py` | Call `setup_fleet_permissions()` after `create_roles()` |
| `hooks.py` | Fixture filter no longer matches the standard `Fleet Manager` |
| `patches/v1_5/apply_field_permlevels.py` | **New** — applies permlevels to existing fields |
| `tests/test_fleet_permissions.py` | **New** — 26 regression tests |

**No standard ERPNext, HRMS or Frappe file was modified** — all three report 0 changed files.

### Verification

| Check | Expected | Actual | |
|---|---|---|---|
| Permission rows added | 33 | **33** | PASS |
| Rows modified | 0 | **0** | PASS |
| Rows removed | 0 | **0** | PASS |
| Field permlevel changes | 24 | **24** | PASS |
| Access revocations | 0 | **0** | PASS |
| Standard files changed | 0 | **0** | PASS |

Tests: **632 passing** (606 existing + 26 new). Staging state byte-identical to the tested
dev state. Role-wise testing: **16 PASS, 0 FAIL** — see
`DEF-001_Role_Permission_Test_Report.md`.

### Two things found during the fix that would have defeated it

| # | Discovery | Why it mattered |
|---|---|---|
| 1 | **Vehicle Log already had Custom DocPerm rows.** Once a DocType has any, frappe reads Custom DocPerm and ignores DocPerm entirely. | A permission shipped via DocType JSON would have been **silently discarded on exactly the DocType the driver needs most**. The fix uses `add_permission()`, which writes Custom DocPerm. |
| 2 | **`cost` and `invoice_reference` live inside the service-items grid.** | Restricting only the parent fields would have left a driver with level-0 write able to type costs into the table. Frappe v16 honours permlevel on child-table fields, so both were moved. Test RT-20 proves it. |

### Residual

The fix changes **who enters the service bill** — a driver who cannot touch cost fields
cannot type a bill. The Maintenance User now records it. `GDL_Fleet_Handbook.html` Part 7
and `GDL_Fleet_02_Business_Process_Guide.md` §I were updated accordingly.

---

## OBS-001 — ✅ CLOSED

| Field | Detail |
|---|---|
| **Severity** | Low · **Status** | **CLOSED** 4 Nov 2026 |

**Was:** `Fleet User` had no permission row on `Vehicle`, so a requester could not open the
vehicle allocated to them.

**Resolved by:** your decision 3. `Fleet User` granted **read at level 0**, while
`vehicle_value`, `asset` and `lessor` moved to **level 1** and remain out of reach.

**Verified (tier A, through a real account):** `jigmeling.user@gdl.test`, whose only role is
Fleet User — `Vehicle` read `True`, write/create/delete `False`; all three sensitive fields
blocked.

---

## OBS-002 — ✅ CLOSED

| Field | Detail |
|---|---|
| **Severity** | Info · **Priority** | Low · **Status** | Open — business clarification |

**Description.** `GDL Fleet: Driving Licence Expiry` fires **14 days** ahead because it
reuses `renewal_notice_days`. Changing the insurance reminder silently changes the licence
reminder too.

**Why it matters.** A licence and an insurance policy have different renewal lead times — a
licence usually needs more notice.

**Resolved 4 Nov 2026.** The licence alert now has its own setting,
`licence_expiry_notice_days`, defaulting to **30 days** — a licence takes longer to replace
than a policy takes to renew. `renewal_notice_days` stays at 14 and the ladder is untouched.

Patch `v1_6.separate_licence_notice` re-points the existing alert and writes the setting
once; a site where someone has already chosen a value keeps their choice. Verified on
staging: licence 30, renewal 14, decoupled. A test sets `renewal_notice_days` to 7 and
asserts the licence figure does not move.

---

## OBS-003 — ✅ CLOSED

| Field | Detail |
|---|---|
| **Found** | Role-wise permission testing, test 6 |
| **Severity** | Info · **Status** | Open — design confirmation |

**Description.** `Fleet Maintenance User` has **no permission on Vehicle Log**. They can
service a vehicle but cannot look at its daily running.

**This matches the approved matrix** — Vehicle Log was granted to Fleet Driver, Fleet
Administrator and Fleet Approver only. Not a regression.

**Resolved 4 Nov 2026.** `Fleet Maintenance User` granted **read** on Vehicle Log —
`lvl0 ['read']`. They can see how a vehicle has been running when judging whether a service
is due; they still cannot record a journey. Verified on staging.

---

## OBS-004 — ✅ CLOSED

| Field | Detail |
|---|---|
| **Found** | Role-wise permission testing, test 1 |
| **Severity** | Info · **Status** | Open — design confirmation |

**Description.** `Fleet Driver` has **no permission on Asset Repair**. Breakdowns are
Maintenance User and Administrator only.

**This matches the approved matrix** and is consistent with the driver recording routine
visits rather than breakdowns. Note that Asset Repair also requires the vehicle to be a
fixed Asset — only 3 of 14 qualify — so it is of limited use either way today.

**Resolved 4 Nov 2026.** `Fleet Driver` granted **read** on Asset Repair —
`lvl0 ['read']`. A driver can see a breakdown logged against a vehicle they drive;
recording one stays with the maintenance user. Verified on staging.

Note the standing limitation: Asset Repair requires the vehicle to be a fixed Asset, and
only 3 of 14 qualify.

---

## OBS-005 — ✅ CLOSED

| Field | Detail |
|---|---|
| **Found** | User-level testing, 4 Nov 2026 |
| **Severity** | Info · **Status** | Open — role-assignment decision |

**Description.** All seven `*.mto` accounts hold **Approver, Manager and User**.
`Fleet Manager` is a **standard ERPNext role** with broad access, so every MTO reads Asset
Maintenance Log at levels `[0,1,2]` and Vehicle at `[0,1]` — including `vehicle_value`,
every cost field and the full purchasing trail.

**Not caused by the DEF-001 change.** Before it, Vehicle had no permission levels at all,
so anyone with read saw every field. The preservation row kept Fleet Manager exactly where
it was, per decision 2. The behaviour is unchanged.

**Why it matters.** If GDL expects a location MTO to approve vehicle requests *without*
seeing what each vehicle cost, that expectation is not met.

**Resolved 4 Nov 2026.** `Fleet Manager` removed from all seven MTO accounts, which now
hold `Fleet Approver` and `Fleet User` only.

**Correction to this entry as first written.** It claimed "Fleet Approver alone covers
everything the approval process needs." That was true of the *workflows* and wrong about
the job. Fleet Approver was on **none of the 18 reports** and could not manage renewals, so
removing Fleet Manager alone would have cost every MTO *Movement Request Status* and
*Vehicle Availability* — the two screens the handbook tells them to start from.

So the rights were granted to `Fleet Approver` in its own right **before** the role was
removed:

| Granted to Fleet Approver | Where |
|---|---|
| Read on all **18 fleet reports** | each report's JSON |
| Read, write, create, submit on **Renewal Register** | its DocType JSON |
| **Read** on Asset Maintenance Log — level 0 only | `setup/fleet_permissions.py` |

`setup/gdl_fleet_rollout.py` no longer grants Fleet Manager to MTOs, so a future rollout
cannot reintroduce it.

**Verified on staging.** `vehicle_value`, `asset`, `lessor`, `labour_cost`, `parts_cost`,
`bill_no` and `purchase_invoice` are all **HIDDEN** from an MTO. All 18 reports runnable,
renewals manageable, both approval workflows still actionable.

---

## Caveat on completeness

**Two suites have run:** the Phase 1 read-only permission matrix, and the post-fix role-wise
permission testing. Both examine **permissions**.

The functional, workflow and negative suites — 96 user-wise cases — **have not run**, because
five fleet roles are assigned to nobody and no fleet account has a password. The absence of
further defects says nothing about them.

DEF-001 was found in the first hour of the first suite. It would be unwise to read this
register as evidence the application is defect-free.
