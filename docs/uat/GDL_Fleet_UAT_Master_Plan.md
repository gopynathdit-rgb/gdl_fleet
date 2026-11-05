# GDL Fleet — UAT Master Plan

**Issued:** 4 November 2026 · **Phase reached:** Phase 1 complete, Phase 2 blocked
**Prepared against:** the five audit documents and GDL Business Blueprint v1.00

---

## 1. Environment — verified 4 November 2026

| Item | Verified value |
|---|---|
| Site | `gdl-staging.localhost` |
| Database | `_6fb4174599644948` on `127.0.0.1:3307` |
| Frappe | 16.32.0 |
| ERPNext | 16.33.0 |
| HRMS | 16.17.0 |
| **Fleet application** | **`gdl_fleet_extension` 1.0.0** |
| Other installed apps | `gdl` 0.0.1, `gdl_custom_app` 0.0.1 |
| Company | GreenDigital Limited (GDL), BTN, Bhutan |
| Operating locations | 10 — Head Office, Jamjee, Dochula, Dagapela, Gedu, Samcholing, Jigmeling, Motanga, GMC, Service Location |

### Safety state — confirmed before any testing

| Control | State | Meaning for UAT |
|---|---|---|
| `mute_emails` | **1** | No email can leave the site. Notification *delivery* cannot be tested. |
| `pause_scheduler` | **1** | Daily jobs do not run. Date-triggered alerts cannot fire. |
| `developer_mode` | 0 | DocType changes cannot be made accidentally. |
| `maintenance_mode` | not set | Site is reachable. |

**These were observed, not changed.** The brief forbids enabling either, and this plan does
not propose it.

> `gdl_fleet_management` is **not installed**. It exists on disk and affects nothing. All
> testing targets `gdl_fleet_extension`.

---

## 2. Objectives

1. Prove the right users can reach the right processes.
2. Prove the wrong users are refused — the negative tests matter more than the positive ones.
3. Prove documents link correctly and calculations are right.
4. Produce evidence GDL management can be shown.

**The UAT is not complete because forms open.** It is complete when a named user has
carried a real document through a real workflow, and an unauthorised user has been
demonstrably stopped.

---

## 3. Scope

**In scope:** all 32 functional areas listed in the brief — vehicle master through to
workspace navigation — plus all 18 reports, 5 dashboard cards and 5 charts, and the role
permission matrix.

**Out of scope, with reason:**

| Excluded | Reason |
|---|---|
| SAP integration | **NOT IMPLEMENTED.** Nothing exists to test. Will not be simulated. |
| Notification delivery | Email muted and scheduler paused by design. **Configuration** is tested instead. |
| Purchase Invoice / Payment Entry creation | Requires separate written approval (brief §3.12) |
| Stock Entry / inventory movement | Requires separate written approval (brief §3.13) |
| The five-stage approval chain | Switched off. Out of scope unless GDL turns it on. |

---

## 4. Roles and the user-wise testing matrix

Verified against `tabHas Role` and `__Auth` on 4 November 2026.

| User type | Role | Holders (enabled) | Can log in | Status |
|---|---|---|---|---|
| Fleet Employee | Fleet User | 14 | **0** | **BLOCKED** |
| Location MTO | Fleet Approver | 7 | **0** | **BLOCKED** |
| Fleet Manager | Fleet Manager | 9 | 2 *(see note)* | **BLOCKED** |
| Driver | Fleet Driver | **0** | 0 | **BLOCKED — no holder** |
| HR Approver | Fleet HR Approver | **0** | 0 | **BLOCKED — no holder** |
| Store User | Fleet Store User | **0** | 0 | **BLOCKED — no holder** |
| Maintenance User | Fleet Maintenance User | **0** | 0 | **BLOCKED — no holder** |
| Fleet Administrator | Fleet Administrator | **0** | 0 | **BLOCKED — no holder** |

**Note on the two accounts that can log in.** One is `Administrator`, which the brief
forbids for permission testing (§3.15) — correctly, because it bypasses every check. The
other belongs to a **real person** carried over in the restored database; it was not used
and must not be.

### Two independent blockers

**Blocker A — no credentials.** All fourteen `@gdl.test` accounts have no password set.
The brief forbids resetting passwords (§3.7). No named fleet user can be logged in.

**Blocker B — no browser automation.** No Chrome extension connected; no Playwright,
Selenium, Puppeteer or Cypress installed; **no browser binary of any kind on this machine**.
The brief forbids installing packages without approval (§8).

Either blocker alone prevents user-wise UI testing. Together they make it impossible.

`wkhtmltoimage` is present and is **deliberately not used** — it renders HTML, so its
output would be fabricated evidence of a page nobody logged into (§8 prohibits this).

---

## 5. What *was* executed

Brief §12 Step 6 authorises read-only tests requiring no changes. These were run:

| # | Read-only test | Method | Result |
|---|---|---|---|
| R-01 | Environment and version verification | config and app registry | Pass |
| R-02 | Safety state (email, scheduler) | site config | Pass — both locked down |
| R-03 | Company and location configuration | database read | Pass — 10 locations |
| R-04 | User and role inventory | `tabHas Role`, `__Auth` | Pass — **5 roles have no holder** |
| R-05 | Permission matrix per named user | `frappe.has_permission(user=…)` | **Defect found — DEF-001** |
| R-06 | Permission level 1 (vehicle allocation) | `tabDocPerm` | Pass — MTO may allocate, requester may not |
| R-07 | Location-MTO approval authority | `location_officers.may_approve` | Pass — routing exactly correct |
| R-08 | Workflow states, transitions, roles | live Workflow records | Pass — 3 active, as designed |
| R-09 | Notification configuration | live Notification records | Pass — 14/3/expiry, two rungs off |
| R-10 | POL calculation vs blueprint page 8 | `compute_abstract()` | **Pass — all 7 figures exact** |
| R-11 | Dashboard cards and charts | executed each | Pass — Vehicles Active 14 |
| R-12 | DB-resident scripts | Client/Server Script tables | Pass — 0 of each |

**No record was created, modified or deleted. No migration was run. No setting was changed.**

---

## 6. Test data strategy

Not yet applied — no test record has been created.

When testing is approved:

- Every record carries the prefix **`UAT-GDL-`** in a text field (purpose, remarks or
  destination) so it is identifiable by search.
- Naming series are left standard; the prefix goes in the content, because changing a
  naming series would be a configuration change.
- **No existing record is modified.** If a test appears to need one, it is stopped and reported.
- **Nothing is auto-deleted.** Every record is listed in `GDL_Fleet_Test_Data_Register.md`
  with its status and links, for GDL to review and dispose of.

---

## 7. Safety limitations observed

| Brief rule | How it was honoured |
|---|---|
| Do not modify existing records | Nothing was written at all |
| Do not delete staging records | Nothing deleted |
| Do not run migrations | None run |
| Do not modify source code | None modified during UAT |
| Do not change workflows/roles/permissions to pass tests | **DEF-001 was documented, not fixed** |
| Do not reset passwords | None reset — accepted as a blocker instead |
| Do not enable scheduler or email | Neither touched |
| Do not change GDL Fleet Settings | Not touched |
| No Purchase Invoice / Payment Entry | None created |
| No Stock Entry | None created |
| Never use Administrator for permission tests | Permission results derived per named user; **DEF-001 was found precisely because of this rule** |

---

## 8. Schedule — proposed

| Stage | Depends on | Effort |
|---|---|---|
| **0. Unblock** | GDL: passwords; approval for a browser; role assignment; drivers; employees | — |
| 1. Suites A, B, H (employee, MTO, manager) | Blocker A + B cleared | ~1 day |
| 2. Suites C, D, E (admin, driver, HR) | Role assignment + drivers | ~1 day |
| 3. Negative/permission suite | All of the above | ~0.5 day |
| 4. Suites F, G (maintenance, store) | Bill approver role, stock items, **approval for stock movement** | ~0.5 day |
| 5. Accounting tests | **Separate written approval** | ~0.5 day |
| 6. Report and defect close-out | — | ~0.5 day |

---

## 9. Overall result so far

| Measure | Count |
|---|---|
| Test cases defined | 120 *(existing script set)* + 96 user-wise *(this plan)* |
| **Executed** | **12 read-only environment and permission tests** |
| Passed | 11 |
| **Failed** | **1 — DEF-001, now CLOSED** |
| Blocked | All user-wise and UI test cases |
| Screenshots captured | **0** — see `screenshots/README.md` |

> **Updated 4 November 2026.** A second round of 16 role-wise permission tests ran after
> the DEF-001 fix: **16 PASS, 0 FAIL**. Across both rounds: **28 executed, 27 passed,
> 1 failed and since closed.** See `GDL_Fleet_UAT_Execution_Report.md`.

### The one defect found — now closed

**DEF-001 (High).** Five fleet roles have **no permission rows at all** on the standard
DocTypes they are meant to operate. A Fleet Driver cannot record a Vehicle Log; a Fleet
Administrator cannot create a Vehicle or a Driver; **no fleet role can record a service**
on Asset Maintenance Log.

This was invisible to the 606 automated tests and to all earlier end-to-end testing,
because both ran as Administrator or as users who also hold Fleet Manager. It surfaced
immediately once permissions were evaluated per named role — which is exactly why the
brief forbids testing as Administrator.

Full detail in `GDL_Fleet_Defect_Register.md`.

---

## 10. What is needed to proceed

**From GDL — decisions and data**

1. Approve setting passwords for the test accounts *(or supply credentials another way)*.
2. Assign Fleet Driver, Fleet HR Approver, Fleet Store User, Fleet Maintenance User and
   Fleet Administrator to real users.
3. Create at least two Drivers with licence numbers, linked to Employees.
4. Decide on DEF-001: fix before UAT, or test around it with Fleet Manager and accept that
   the role design is not what the documentation describes.

**From you — approvals**

5. Approve a browser automation route, or accept manual screenshot capture.
6. Separate approval for stock movements (Suite G).
7. Separate approval for Purchase Invoice / Payment Entry (POL and maintenance billing).
