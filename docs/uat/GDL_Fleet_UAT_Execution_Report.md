# GDL Fleet — UAT Execution Report

**Site:** `gdl-staging.localhost` · **Last updated:** 4 November 2026
**Rounds completed:** 2 · **Phases 2–5 (user-wise functional UAT):** still blocked

---

## 1. Headline

Two rounds of permission testing have run, totalling **28 tests: 27 PASS, 1 FAIL**.

The single failure was **DEF-001 (High)** — found in round 1, fixed, and **verified closed
in round 2**. No High or Medium defect remains open.

**No user-wise functional UAT has run and no screenshot has been captured**, for reasons
that have not changed: five fleet roles are assigned to nobody, no fleet account has a
password, and there is no browser automation on this machine. All 96 user-wise cases
remain Blocked.

Staging has never had a business record created, modified or deleted by this work.

---

## 2. Results across both rounds

| | Round 1 (4 Nov, pre-fix) | Round 2 (4 Nov, post-fix) | Total |
|---|---|---|---|
| Executed | 12 | 16 | **28** |
| Passed | 11 | 16 | **27** |
| **Failed** | **1** | **0** | **1** |
| Blocked | 204 | 4 | — |
| Screenshots | 0 | 0 | **0** |

### Round 1 — environment and permission audit *(read-only)*

| # | Test | Result | Evidence |
|---|---|---|---|
| R-01 | Site, database, app versions | PASS | `gdl_fleet_extension` 1.0.0; frappe 16.32.0, erpnext 16.33.0, hrms 16.17.0 |
| R-02 | Safety state | PASS | `mute_emails=1`, `pause_scheduler=1`, `developer_mode=0` |
| R-03 | Company and locations | PASS | GreenDigital Limited (BTN); 10 locations |
| R-04 | User and role inventory | PASS *(with finding)* | 17 enabled users; **5 fleet roles have no holder** |
| **R-05** | **Permission matrix per named user** | **FAIL** | **→ DEF-001** |
| R-06 | Permission level 1 — allocation | PASS | Fleet Approver write at permlevel 1; Fleet User read only |
| R-07 | Location-MTO approval authority | PASS | Each MTO their own site; Head Office anywhere |
| R-08 | Workflows, states, transitions | PASS | 3 active, as designed |
| R-09 | Notification configuration | PASS | 14 / 3 / expiry+1 enabled; two rungs disabled |
| R-10 | POL vs blueprint page 8 | PASS | **All 7 figures exact** |
| R-11 | Dashboard cards and charts | PASS | Vehicles Active = 14, matches the table |
| R-12 | Database-resident scripts | PASS | 0 Client Scripts, 0 Server Scripts |

### Round 2 — post-fix role-wise permission testing *(read-only)*

| # | Test | Role | Tier | Result |
|---|---|---|---|---|
| 1–5 | DocType perms · level-1 blocked · level-2 blocked · child-table blocked · can create **and update** service records | Fleet Driver | B | **PASS** ×5 |
| 6–8 | DocType perms · can enter supplier/invoice/cost · cannot edit the approval trail | Fleet Maintenance User | B | **PASS** ×3 |
| 9–10 | DocType perms · Vehicle readable, sensitive fields blocked | Fleet User | **A** | **PASS** ×2 |
| 11–12 | DocType perms, no delete · full access to all three levels | Fleet Administrator | B | **PASS** ×2 |
| 13–15 | Every field retained | Delivery Manager, Delivery User, Manufacturing User | B | **PASS** ×3 |
| 16 | No standard permission row changed | standard roles | — | **PASS** |

Full detail: `DEF-001_Role_Permission_Test_Report.md`.

> **Evidence tiers.** Only **test 9–10** reached tier A — evaluation through a real
> logged-in account (`jigmeling.user@gdl.test`, whose only role is Fleet User). The other
> fourteen are tier B: computed from permission metadata using frappe's own rule.
> Deterministic and exact, but **no human has exercised them**, because the roles are
> assigned to nobody.

---

## 3. The defect, and its closure

### DEF-001 (High) — fleet roles had no permissions on standard DocTypes

Found by evaluating permissions **per named role** rather than as Administrator — which is
precisely why the brief forbids testing as Administrator. It had survived 606 automated
tests and three rounds of manual testing, because every one ran as Administrator or as an
account that also held `Fleet Manager` — **a standard ERPNext role** that already ships
with access to Vehicle, Driver and Vehicle Log.

**Remediation applied to staging 4 Nov 2026.** Backup taken and verified first
(`20261104_202923-gdl-staging_localhost-database.sql.gz`, 1.6 MiB, gzip-verified, 943 tables).

| Check | Expected | Actual | |
|---|---|---|---|
| Permission rows added | 33 | 33 | PASS |
| Rows modified | 0 | 0 | PASS |
| Rows removed | 0 | 0 | PASS |
| Field permlevel changes | 24 | 24 | PASS |
| Access revocations | 0 | 0 | PASS |
| Standard files changed | 0 | 0 | PASS |

Migration exit code 0, zero tracebacks. Staging state **byte-identical** to the dev state
the tests ran against. **632 tests passing.**

**Status: CLOSED.**

---

## 4. Why the functional UAT is still blocked

Unchanged since round 1. Fixing DEF-001 removed a *permission* obstacle, not an
*access* one.

| Blocker | Detail | Owner |
|---|---|---|
| **A — No credentials** | All 14 `@gdl.test` accounts have no password. The brief forbids setting one. Only Administrator (forbidden for permission tests) and one real person's account can log in. | GDL |
| **B — No browser automation** | No Chrome extension connected; no Playwright, Selenium, Puppeteer or Cypress; **no browser binary on this machine**. `wkhtmltoimage` exists and was deliberately not used — it renders HTML, so its output would be fabricated evidence. | You |
| **C — Five roles have no holder** | Fleet Driver, HR Approver, Store User, Maintenance User, Administrator. Suites C–G have no operator. | GDL |
| **D — Master data and configuration** | Drivers (1), Employees (1), no BOD/STCBL suppliers, blank Bill Approver Role, Purchasing Company, Maintenance Service Item, Default Maintenance Team, no stock items. | GDL |

### Blocked suites

| Suite | Role | Blocked by | Change since round 1 |
|---|---|---|---|
| A — Fleet Employee | Fleet User | A, B | — |
| B — Location MTO | Fleet Approver | A, B | — |
| C — Fleet Administrator | Fleet Administrator | A, B, C | **DEF-001 removed** |
| D — Fleet Driver | Fleet Driver | A, B, C, D | **DEF-001 removed** |
| E — HR Approver | Fleet HR Approver | A, B, C | — |
| F — Maintenance | Fleet Maintenance User | A, B, C, D | **DEF-001 removed** |
| G — Store User | Fleet Store User | A, B, C, D + stock approval | — |
| H — Fleet Manager | Fleet Manager | A, B | — |
| Negative / permission | all | A, B, C | — |

Three suites are now one blocker lighter. **None is unblocked.**

---

## 5. Acceptance criteria

| Criterion | Round 1 | Round 2 |
|---|---|---|
| Correct users can access the correct modules | ❌ Not demonstrated — DEF-001 said several could not | ⚠️ **Rules verified, not exercised.** Tier B for 5 of 6 roles |
| Unauthorized users are blocked | ⚠️ Partly | ✅ **Verified at the permission layer** — 16 tests, incl. field and child-table level |
| Users can complete their assigned processes | ❌ | ❌ — no account can log in |
| Workflows move to the correct next stage | ❌ | ❌ |
| Vehicle and driver carry between documents | ❌ | ❌ |
| Calculations match expected values | ✅ R-10, exact | ✅ unchanged |
| Reports show correct results | ❌ | ❌ |
| Dashboard data is accurate | ✅ R-11 | ✅ unchanged |
| Validation messages are understandable | ❌ | ❌ |
| **No existing staging data changed** | ✅ | ✅ **confirmed again** |
| Every executed UI test has screenshot evidence | n/a — none executed | n/a |
| Every defect documented | ✅ | ✅ |
| Every blocked test has a clear reason | ✅ | ✅ |

**This report still cannot be presented to GDL management as evidence of a working system.**
It establishes that the environment is sound, the calculations are right, the approval
routing is right, the dashboard is accurate and **the permission model is now correct and
enforced to field and child-table level**. It does not show a single user completing a
single process.

---

## 6. Defects

| ID | Severity | Status |
|---|---|---|
| DEF-001 | High | ✅ **CLOSED** |
| OBS-001 | Low | ✅ **CLOSED** |
| OBS-002 | Info | Open — licence alert reuses the renewal setting |
| OBS-003 | Info | Open *(new)* — Maintenance User has no Vehicle Log access |
| OBS-004 | Info | Open *(new)* — Fleet Driver has no Asset Repair access |

OBS-003 and OBS-004 both **match the approved permission matrix** and need a design
confirmation, not a fix. Full detail in `GDL_Fleet_Defect_Register.md`.

---

## 7. Recommendations

**Immediate — GDL**

1. **Assign the five unheld roles** to real users. This is now the single largest blocker:
   the permission model is correct but nobody can exercise it.
2. **Approve credentials** for at least one Fleet User, two MTOs at different sites, the
   Head Office MTO, one Fleet Driver, one Fleet HR Approver.
3. **Answer OBS-002, OBS-003 and OBS-004** — three short decisions.

**Then**

4. Approve a browser route, or accept manual capture per `screenshots/README.md`.
5. Create drivers, employees and the two fuel suppliers; fill the four blank settings.
6. Separate written approval for stock movement, and for Purchase Invoice / Payment Entry.

**A note on sequencing.** Round 2 proves the permission *rules* are right. Fifteen of
sixteen results are tier B, so the next round should be run **through logged-in accounts**,
which needs items 1 and 2 above. Repeating tier-B testing would add nothing.
