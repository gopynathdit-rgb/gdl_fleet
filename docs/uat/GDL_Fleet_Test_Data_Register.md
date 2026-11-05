# GDL Fleet — Test Data Register

**Opened:** 4 November 2026 · **Site:** `gdl-staging.localhost`

---

## 1. Records created by UAT

**None. No record has been created, modified or deleted.**

| UAT Ref | DocType | Document ID | Created by | Test case | Status | Submitted | Linked to | Cleanup |
|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — |

*(Empty on purpose. Phase 1 was read-only; Phase 2 is blocked. This table is filled only
when testing is approved and executed.)*

---

## 2. Naming convention — to apply when testing is approved

Every UAT record will carry **`UAT-GDL-`** in a visible text field so it can be found by
search and told apart from GDL's own data at a glance.

| DocType | Where the prefix goes | Example |
|---|---|---|
| Movement Order Request | `purpose` | `UAT-GDL-REQ-001 — UAT travel request` |
| Movement Order | `remarks` | `UAT-GDL-MO-001` |
| Vehicle Log | `place_to_travel` | `UAT-GDL-LOG-001` |
| POL Abstract | `remarks` | `UAT-GDL-POL-001` |
| Driver Assignment | `purpose` | `UAT-GDL-DA-001` |
| Renewal Register | `remarks` | `UAT-GDL-REN-001` |
| Asset Maintenance Log | `description` | `UAT-GDL-SVC-001` |
| Fleet Part Issue | `remarks` | `UAT-GDL-FPI-001` |

**Naming series are left standard.** Changing one would be a configuration change, which
the brief forbids. The prefix goes in the content instead.

---

## 3. Pre-existing records — for separation, not for modification

These existed before UAT. Listed so that any later record is demonstrably new, and so that
anyone reviewing can see what must **not** be touched.

| DocType | Count before UAT | Note |
|---|---|---|
| Vehicle | 14 | The blueprint fleet. **Do not modify.** |
| Fleet Vehicle Type | 4 | Bus, Car, Pickup, SUV |
| Location | 10 | GDL's own sites |
| Vehicle Service Item | 17 | — |
| Driver | 1 | **Do not modify.** |
| Employee | 1 | **Do not modify.** |
| Driver Assignment | 1 | — |
| Movement Order Request | 1 | `MOR-2026-00001`, owned by Administrator, state Accepted |
| Movement Order | 1 | — |
| Vehicle Log | 1 | — |
| POL Abstract | 1 | — |
| Asset Maintenance Log | 1 | — |
| Supplier | 3 | BOD and STCBL are **not** among them |
| Asset | 3 | — |
| Warehouse | 9 | — |
| Item | 7 | — |
| Renewal Register | 0 | — |
| Fleet Part Issue | 0 | — |
| Vehicle Tyre | 0 | — |
| Asset Repair | 0 | — |
| Asset Maintenance | 0 | — |
| Stock Entry | 0 | — |

Re-run these counts after any UAT round. Any change to a figure that UAT did not
deliberately cause is itself a finding.

---

## 4. Cleanup policy

**Nothing is deleted automatically.** The brief requires test records to survive for review.

When GDL is ready to dispose of them:

| Document state | How to remove | Why not simply delete |
|---|---|---|
| Draft | Delete | Nothing was posted |
| Submitted, no financial effect | **Cancel**, then delete | Cancel preserves the audit trail |
| Submitted with a Stock Entry | Cancel the Fleet Part Issue — it cancels the linked Stock Entry | Stock must reverse through the ledger |
| Submitted with a Purchase Invoice | **Do not delete.** Refer to Accounts | An accounting document is not the implementer's to remove |

**Recommended:** take a database backup immediately before any UAT round that creates
records. Restoring is cleaner than unpicking.

---

## 5. Credentials

**No credential is recorded in this document, and none should ever be.**

No password was set, reset or read during this audit. The fourteen `@gdl.test` accounts
have no password; that is recorded as a blocker in the Master Plan, not worked around.
