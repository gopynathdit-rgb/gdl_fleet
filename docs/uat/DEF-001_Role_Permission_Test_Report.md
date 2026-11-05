# DEF-001 — Role-wise Permission Test Report

**Site:** `gdl-staging.localhost` · **Date:** 4 November 2026
**Method:** read-only. No migration, no record created or modified, no role assigned, no
password set, no transaction.

---

## 1. Evidence tiers — read this before the results

Permissions were evaluated two ways, and the report says which applies to each result.

| Tier | Method | Strength | When used |
|---|---|---|---|
| **A — user-level** | `frappe.has_permission(doctype, ptype, user=<real account>)` | **Strongest.** Evaluated through an actual user and their actual roles. | Only where a real account holds the role under test **and nothing else** |
| **B — role-level** | Computed from `frappe.get_meta(doctype).permissions` using frappe's own rule — ptype flags from permlevel-0 rows (`perm.role in roles and cint(perm.permlevel) == 0`), field access from the permlevel sets | Deterministic and exact, but not evaluated through a session | Where no single-role holder exists |

### Which roles could be tested at which tier

| Role | Enabled holders | Single-role holder | Tier |
|---|---|---|---|
| **Fleet User** | 14 | `jigmeling.user@gdl.test` | **A** |
| Fleet Driver | **0** | — | B |
| Fleet Maintenance User | **0** | — | B |
| Fleet Administrator | **0** | — | B |
| Delivery Manager | 1 | — *(also holds other roles)* | B |
| Delivery User | 1 | — *(also holds other roles)* | B |
| Manufacturing User | 1 | — *(also holds other roles)* | B |

> **Why only one role reaches tier A.** Five fleet roles are assigned to nobody, and the
> three standard roles are held by accounts that also hold other roles — a user with two
> roles cannot tell you which one granted access. The brief forbids assigning roles or
> creating accounts, so tier B is the ceiling for those six. Each affected result is
> marked **PASS (tier B)** rather than plain PASS, and the end-to-end confirmation is
> listed as **BLOCKED** in section 8.

---

## 2. Fleet Driver

> **The decision-1 requirement:** can enter and submit service information, cannot access
> or modify financial fields.

### DocType permissions — tier B

| DocType | Read | Write | Create | Submit | Cancel | Amend | Delete | Verdict |
|---|---|---|---|---|---|---|---|---|
| Vehicle | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **PASS** — read-only, as specified |
| Driver | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **PASS** |
| **Vehicle Log** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | **PASS** — records daily KM; **no cancel**, by design |
| **Asset Maintenance Log** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | **PASS** — creates *and updates* service records |
| Asset Repair | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **PASS** — not in the approved matrix |

Permission levels: **read `[0]`, write `[0]`** — level 0 only.

### Field-level access to restricted financial fields — tier B

| Group | Fields | Visible to driver | Writable | Verdict |
|---|---|---|---|---|
| Level 1 — money and bill | 9 | **0 of 9** | **0 of 9** | **PASS** |
| Level 2 — approval trail | 10 | **0 of 10** | **0 of 10** | **PASS** |

### Child-table restriction — tier B

| Field | Level | Driver visible | Driver writable | Verdict |
|---|---|---|---|---|
| `Fleet Service Item.cost` | 1 | ❌ | ❌ | **PASS** |
| `Fleet Service Item.invoice_reference` | 1 | ❌ | ❌ | **PASS** |

This is the hole that would have defeated the whole change — cost sits *inside* the
service-items grid, so restricting only the parent fields would have left a driver able to
type costs into the table.

### Evidence — the live record, field by field

Against `ACC-AML-2026-00001` (read only, not modified). Fleet Driver readable levels `[0]`:

| Field | Level | Driver sees |
|---|---|---|
| `vehicle` | 0 | **YES** |
| `odometer` | 0 | **YES** |
| `completion_date` | 0 | **YES** |
| `service_items` | 0 | **YES** |
| `service_provider` | 1 | no — stripped |
| `labour_cost` | 1 | no — stripped |
| `parts_cost` | 1 | no — stripped |
| `bill_no` | 1 | no — stripped |
| `bill_attachment` | 1 | no — stripped |
| `bill_status` | 2 | no — stripped |
| `approved_by` | 2 | no — stripped |
| `purchase_invoice` | 2 | no — stripped |
| `payment_status` | 2 | no — stripped |

**A driver sees what the vehicle had done to it, and nothing about what it cost.**

---

## 3. Fleet Maintenance User

| DocType | Read | Write | Create | Submit | Cancel | Amend | Delete | Verdict |
|---|---|---|---|---|---|---|---|---|
| Vehicle | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **PASS** |
| Driver | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **PASS** |
| Vehicle Log | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **PASS** — not in the approved matrix *(see §7)* |
| **Asset Maintenance Log** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | **PASS** |
| **Asset Repair** | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | **PASS** |

Permission levels on Asset Maintenance Log: **read `[0,1,2]`, write `[0,1]`**.

### Can they enter supplier, invoice and cost details?

| Requirement | Result | Verdict |
|---|---|---|
| Enter `service_provider` | writable (level 1) | **PASS** |
| Enter `bill_no`, `bill_date`, `bill_attachment` | writable | **PASS** |
| Enter `labour_cost`, `parts_cost` | writable | **PASS** |
| Enter `cost` inside the service-items grid | writable | **PASS** |
| **All 9 level-1 fields** | **9 of 9 writable** | **PASS** |
| **Level-2 approval trail** | **10 visible, 0 writable** | **PASS** — can see status, cannot set it |

Exactly the intended split: the maintenance user records the money, the system records the
decision.

---

## 4. Fleet User

**Tier A — real user evidence.** `jigmeling.user@gdl.test`, whose only role is `Fleet User`:

| DocType | Read | Write | Create | Submit | Cancel | Amend | Delete | Verdict |
|---|---|---|---|---|---|---|---|---|
| **Vehicle** | **✅** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **PASS** — decision 3 delivered |
| Driver | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **PASS** |
| Vehicle Log | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **PASS** |
| Asset Maintenance Log | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **PASS** |
| Asset Repair | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **PASS** |

### Sensitive Vehicle fields — tier B

| Field | Level | Visible to Fleet User | Verdict |
|---|---|---|---|
| `vehicle_value` | 1 | ❌ | **PASS** |
| `asset` | 1 | ❌ | **PASS** |
| `lessor` | 1 | ❌ | **PASS** |

Permission levels on Vehicle: **read `[0]`** only. An employee can look up the vehicle
allocated to them; they cannot see what it cost, its asset-register link or its lessor.

---

## 5. Fleet Administrator

| DocType | Read | Write | Create | Submit | Cancel | Amend | Delete | Levels r/w | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **Vehicle** | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | **❌** | `[0,1]` / `[0,1]` | **PASS** |
| **Driver** | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | **❌** | `[0]` / `[0]` | **PASS** |
| Vehicle Log | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **❌** | `[0]` / `[0]` | **PASS** — corrects and cancels |
| Asset Maintenance Log | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **❌** | `[0,1,2]` / `[0,1,2]` | **PASS** |
| Asset Repair | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | **❌** | `[0]` / `[0]` | **PASS** |

**No delete anywhere** — records are cancelled and amended, never deleted. All three
sensitive Vehicle fields visible and writable, as the master owner.

---

## 6. Standard Delivery and Manufacturing roles

> The five preservation rows exist for exactly one purpose: to stop these roles losing
> fields that moved above level 0.

| Role | DocType | Levels r/w | Sensitive fields still visible | Verdict |
|---|---|---|---|---|
| **Delivery Manager** | Vehicle | `[0,1]` / `[0,1]` | `vehicle_value`, `asset`, `lessor` — **all 3** | **PASS** |
| **Delivery User** | Vehicle | `[0,1]` / `[]` | `vehicle_value`, `asset`, `lessor` — **all 3** | **PASS** |
| **Manufacturing User** | Asset Maintenance Log | `[0,1,2]` / `[0,1,2]` | **9 of 9** level-1, **10 of 10** level-2 | **PASS** |

Delivery Manager keeps write (it had write at level 0); Delivery User keeps read only
(it never had write). **Neither gained anything.**

### Did any standard row change?

Compared against the genuine pre-migration snapshot:

```
level-0 rows checked for Fleet Manager, Delivery Manager,
Delivery User and Manufacturing User : 10
rows changed                         : NONE
```

**PASS — existing standard-role access is unchanged.**

---

## 7. Two observations, neither a defect

| # | Observation | Assessment |
|---|---|---|
| **OBS-003** | **Fleet Maintenance User has no access to Vehicle Log.** They can service a vehicle but not look at its daily running. | Matches the approved matrix — Vehicle Log was granted to Driver, Administrator and Approver only. Raise if a maintenance user should see mileage history when judging a service. |
| **OBS-004** | **Fleet Driver has no access to Asset Repair.** Breakdowns are Maintenance User and Administrator only. | Matches the approved matrix. Consistent with the driver recording routine visits, not breakdowns. |

Both are design decisions already approved, recorded here only so nobody re-discovers them
as surprises.

---

## 8. Results summary

| # | Test | Role | Tier | Result |
|---|---|---|---|---|
| 1 | DocType read/write/create/submit/delete | Fleet Driver | B | **PASS** |
| 2 | Level-1 financial fields blocked | Fleet Driver | B | **PASS** |
| 3 | Level-2 approval trail blocked | Fleet Driver | B | **PASS** |
| 4 | Child-table `cost` / `invoice_reference` blocked | Fleet Driver | B | **PASS** |
| 5 | Can create **and update** service records | Fleet Driver | B | **PASS** |
| 6 | DocType permissions | Fleet Maintenance User | B | **PASS** |
| 7 | Can enter supplier, invoice and cost | Fleet Maintenance User | B | **PASS** |
| 8 | Cannot edit the approval trail | Fleet Maintenance User | B | **PASS** |
| 9 | DocType permissions | Fleet User | **A** | **PASS** |
| 10 | Vehicle readable, sensitive fields blocked | Fleet User | A/B | **PASS** |
| 11 | DocType permissions, no delete | Fleet Administrator | B | **PASS** |
| 12 | Full access to all three levels | Fleet Administrator | B | **PASS** |
| 13 | Delivery Manager keeps every field | standard | B | **PASS** |
| 14 | Delivery User keeps every field | standard | B | **PASS** |
| 15 | Manufacturing User keeps every field | standard | B | **PASS** |
| 16 | No standard permission row changed | standard | — | **PASS** |

**16 PASS · 0 FAIL · 0 not run**

### Blocked — cannot be closed by permission evaluation alone

| # | What is blocked | Why |
|---|---|---|
| B-1 | Confirming through a **logged-in session** that a Fleet Driver creates a service record and sees greyed-out cost fields | No account holds Fleet Driver; the brief forbids assigning roles |
| B-2 | The same for Fleet Maintenance User and Fleet Administrator | No holder |
| B-3 | **Screenshot evidence** of any of the above | No browser automation on this machine, and no passwords |
| B-4 | End-to-end bill process by named users | Needs B-1, B-2 and a test transaction, which the brief forbids |

---

## 9. Conclusion

Every permission rule DEF-001 was meant to establish is **in force on staging and behaves
as specified**. The driver/money separation is real and reaches inside the service-items
grid. No standard role lost anything.

**What this report does not prove** is that a person can log in and do the job. Fifteen of
the sixteen results are tier B — the rule is correct, but no human has exercised it,
because five of the roles tested are assigned to nobody. Until GDL assigns those roles and
credentials exist, that gap stays open.

**No defects found. Staging unmodified.**
