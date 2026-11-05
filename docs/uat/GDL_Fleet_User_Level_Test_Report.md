# GDL Fleet — User-Level Testing Report

**Site:** `gdl-staging.localhost` · **Date:** 4 November 2026
**Scope:** every real fleet account on staging, evaluated individually
**Method:** read-only. No login, no record created or modified, no role assigned, no
password set.

---

## 1. What "user-level" can and cannot mean here

There are two different things people mean by user-level testing, and only one of them is
possible on this system today.

| | What it proves | Possible? |
|---|---|---|
| **Per-identity permission evaluation** — `frappe.has_permission(doctype, ptype, user=<account>)` for a named account, resolving that account's actual roles | What **this specific person** may do | ✅ **Yes** — this report |
| **Session-level operation** — logging in as that person and driving the interface | That they can actually **do the job**, and what the screen shows them | ❌ **No** |

**Why the second is impossible:** of the fourteen fleet accounts, **none has a password**,
and setting one is forbidden. The only two accounts that can log in are `Administrator`
(forbidden for permission testing, because it bypasses every check) and one real person's
account carried over in the restored database, which was not used.

So this report tells you **exactly what each named person is permitted to do**. It does not
show anyone doing it.

---

## 2. Role coverage — the hard constraint

| Role | Holders | Can log in | Single-role holder | User-level testable |
|---|---|---|---|---|
| Fleet User | 14 | 0 | 7 | ⚠️ per-identity only |
| Fleet Approver | 7 | 0 | 0 | ⚠️ per-identity only |
| Fleet Manager | 8 | 1 *(a real person)* | 1 | ⚠️ not used — real person's account |
| **Fleet Driver** | **0** | 0 | 0 | ❌ **no holder** |
| **Fleet Maintenance User** | **0** | 0 | 0 | ❌ **no holder** |
| **Fleet Administrator** | **0** | 0 | 0 | ❌ **no holder** |
| **Fleet HR Approver** | **0** | 0 | 0 | ❌ **no holder** |
| **Fleet Store User** | **0** | 0 | 0 | ❌ **no holder** |

**Five of eight operating roles are assigned to nobody.** No amount of testing closes that;
it needs GDL to assign them.

---

## 3. Per-user results — all 14 accounts

Legend: `R` read · `W` write · `C` create · `S` submit · `.` denied

### Masters and operations

| User | Fleet roles held | Vehicle | Driver | Vehicle Log | Asset Maint. Log | Asset Repair |
|---|---|---|---|---|---|---|
| `dagapela.mto` | Approver, Manager, User | `RWC.` | `R...` | `RWCS` | `R...` | `R...` |
| `dochula.mto` | Approver, Manager, User | `RWC.` | `R...` | `RWCS` | `R...` | `R...` |
| `gedu.mto` | Approver, Manager, User | `RWC.` | `R...` | `RWCS` | `R...` | `R...` |
| `headoffice.mto` | Approver, Manager, User | `RWC.` | `R...` | `RWCS` | `R...` | `R...` |
| `jamjee.mto` | Approver, Manager, User | `RWC.` | `R...` | `RWCS` | `R...` | `R...` |
| `jigmeling.mto` | Approver, Manager, User | `RWC.` | `R...` | `RWCS` | `R...` | `R...` |
| `samcholing.mto` | Approver, Manager, User | `RWC.` | `R...` | `RWCS` | `R...` | `R...` |
| `dagapela.user` | User | `R...` | `....` | `....` | `....` | `....` |
| `dochula.user` | User | `R...` | `....` | `....` | `....` | `....` |
| `gedu.user` | User | `R...` | `....` | `....` | `....` | `....` |
| `headoffice.user` | User | `R...` | `....` | `....` | `....` | `....` |
| `jamjee.user` | User | `R...` | `....` | `....` | `....` | `....` |
| `jigmeling.user` | User | `R...` | `....` | `....` | `....` | `....` |
| `samcholing.user` | User | `R...` | `....` | `....` | `....` | `....` |

### Fleet transactions

| User | Movement Request | Movement Order | POL Abstract | Renewal Register | Fleet Settings |
|---|---|---|---|---|---|
| **all 7 `*.mto`** | `RWCS` | `RWCS` | `R...` | `RWCS` | `R...` |
| **all 7 `*.user`** | `R.C.` | `R...` | `R...` | `R...` | `....` |

### Reading the two rows that matter

**The requester (`*.user`)** can read a vehicle and **create** a movement request — and
nothing else. No write on the order, no POL, no settings. Exactly the design.

**The MTO (`*.mto`)** can create and submit requests and orders, and manage renewals.
`POL Abstract` is `R...` — correct, an MTO is not a driver.

---

## 4. Field-level visibility per user

| User | Asset Maintenance Log read levels | Vehicle read levels |
|---|---|---|
| `*.mto` (all 7) | **`[0, 1, 2]`** | **`[0, 1]`** |
| `*.user` (all 7) | — *(no access at all)* | `[0]` |

**A requester sees a vehicle but not `vehicle_value`, `asset` or `lessor`.** Decision 3,
working as specified.

**An MTO sees everything, including costs and the approval trail** — see OBS-005 below.

---

## 5. The three fixes, verified on staging

### OBS-002 — licence alert decoupled ✅

| | Before | After |
|---|---|---|
| `licence_expiry_notice_days` | *(field did not exist)* | **30** |
| `renewal_notice_days` | 14 | **14** — unchanged |
| Licence alert fires at | 14 days *(inherited)* | **30 days** |
| Decoupled | ❌ | ✅ |

The renewal ladder is untouched: 14 / 3 / expiry+1 enabled, two rungs still off. Changing
the insurance reminder no longer moves the licence one — proven directly by a test that
sets `renewal_notice_days` to 7 and asserts the licence figure does not budge.

A licence now gets 30 days' notice because replacing one takes longer than renewing a
policy. Configurable; 0 switches it off.

### OBS-003 — Maintenance User can read Vehicle Log ✅

`Vehicle Log | Fleet Maintenance User | lvl0 ['read']` — read only. They can see how a
vehicle has been running when judging whether a service is due; they still cannot record a
journey.

### OBS-004 — Fleet Driver can read Asset Repair ✅

`Asset Repair | Fleet Driver | lvl0 ['read']` — read only. A driver can see a breakdown
logged against a vehicle they drive; recording one stays with the maintenance user.

### Migration result

| Check | Result |
|---|---|
| Permission rows added | **2** (the two above) |
| Rows removed | **0** |
| Rights revoked | **0** |
| Field permlevels changed | **none** |
| Migration errors | **0** |
| Backup | `20261104_230052-gdl-staging_localhost-database.sql.gz`, gzip-verified |

Tests: **639 passing** (632 + 7 new for these three fixes).

---

## 6. OBS-005 — new finding

> **Every MTO account also holds `Fleet Manager`, and therefore sees all financial fields.**

| Field | Severity | Status |
|---|---|---|
| ID | OBS-005 | Info — **role assignment, not a permission defect** |

The seven `*.mto` accounts hold **Approver, Manager and User**. `Fleet Manager` is a
**standard ERPNext role** with broad access, which is why they read Asset Maintenance Log
at levels `[0,1,2]` and Vehicle at `[0,1]` — including `vehicle_value`, every cost field
and the full purchasing trail.

**This is not caused by the DEF-001 change.** Before it, Vehicle had no permission levels
at all, so anyone with read saw every field. The preservation row kept Fleet Manager
exactly where it was, per your decision 2. The behaviour is unchanged.

**But it is worth knowing:** if GDL expects a location MTO to approve vehicle requests
*without* seeing what each vehicle cost, that expectation is not met — and the fix is not a
permission change. It is to **stop assigning `Fleet Manager` to MTO accounts**. `Fleet
Approver` alone gives them everything the approval process needs.

**Decision needed:** should MTOs hold Fleet Manager? If no, remove the role from the seven
accounts — a role-assignment change I have not made.

---

## 7. Results

| # | Test | Scope | Result |
|---|---|---|---|
| UL-01 | Per-identity permissions, 14 accounts × 10 DocTypes | all | **PASS** |
| UL-02 | Requester can create a request and nothing else | 7 `*.user` | **PASS** |
| UL-03 | Requester cannot allocate, approve or dispatch | 7 `*.user` | **PASS** |
| UL-04 | Requester reads Vehicle, blocked from commercial fields | 7 `*.user` | **PASS** |
| UL-05 | MTO can create and submit requests and orders | 7 `*.mto` | **PASS** |
| UL-06 | MTO cannot create a POL Abstract | 7 `*.mto` | **PASS** |
| UL-07 | Nobody can write GDL Fleet Settings | all 14 | **PASS** |
| UL-08 | OBS-002 — licence alert decoupled | config | **PASS** |
| UL-09 | OBS-003 — Maintenance User reads Vehicle Log | role | **PASS** |
| UL-10 | OBS-004 — Driver reads Asset Repair | role | **PASS** |
| UL-11 | No permission revoked by the change | all | **PASS** |

**11 PASS · 0 FAIL**

### Blocked

| # | Blocked | Why |
|---|---|---|
| B-1 | Any **session-level** test — logging in and operating the UI | No fleet account has a password |
| B-2 | Fleet Driver, Maintenance User, Administrator, HR Approver, Store User at any level beyond role metadata | **No account holds these roles** |
| B-3 | Screenshot evidence | No browser on this machine, and B-1 |
| B-4 | End-to-end process execution | Needs B-1, B-2 and a test transaction |

---

## 8. What this report establishes, and what it does not

**Established.** Every one of the fourteen real fleet accounts has exactly the permissions
its roles should give it. The requester/MTO split is correct and enforced to field level.
The three observations are fixed and verified on staging.

**Not established.** That anybody can log in. That the screen behaves as expected. That the
three roles fixed today work in practice — **because nobody holds them.**

The irony is worth stating plainly: OBS-003 and OBS-004 grant access to `Fleet Maintenance
User` and `Fleet Driver`, and **neither role is assigned to a single person**. The fixes are
correct and currently theoretical.

### To move past this

1. **Assign the five unheld roles** to real users — the single largest blocker.
2. **Issue credentials** for at least: one Fleet User, two MTOs at different sites, the Head
   Office MTO, one Fleet Driver, one Fleet HR Approver.
3. **Answer OBS-005** — should MTOs hold Fleet Manager?

Items 1 and 2 are GDL's. Until they land, further permission testing adds nothing: the rules
are proven right, and the next thing to prove needs a person.
