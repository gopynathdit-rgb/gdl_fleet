# GDL Fleet — Testing and Validation

**Audit date:** 4 November 2026 · **System:** `gdl-staging.localhost`
**Rule observed:** this audit was read-only. No record was created, modified or deleted; no
migration was run. Everything below is either an observation of existing state, a result
from the automated suite, or a **proposed** test awaiting approval.

---

## 1. What is verified, and how

### 1.1 The automated suite — 606 tests, all passing

The application carries its own test suite, run on the development site (which has the
`GDL (Demo)` company the fixtures require). It covers, among other things:

| Area | Representative coverage |
|---|---|
| POL calculation | The blueprint's page-8 sheet reproduced figure by figure |
| POL coupon balance | Carry-forward, draft exclusion, per-vehicle isolation, out-of-order periods |
| Mileage deviation | Both tolerance ends, the EV exclusion, configurability |
| Driver assignment | Overlapping Primary refused; Temporary/Relief allowed to overlap |
| Vehicle Log | Duplicate day, negative distance, abnormal warning, cancel-recalculates |
| Movement request/order | Availability, double booking, one order per request, both creation paths |
| Location MTO | Own site yes, other site no, head office anywhere, one step not two |
| Workflows | State sets, self-approval per action, role gates |
| Parts and tyres | One tyre per row, serial rules, stock entry raised, cost carried |
| Reports | Every report executed; grouped columns match the grouping |
| Dashboard | Every card and chart executed; filters point at fields that exist |

> **Caveat the brief asked for.** The suite runs on the **development** site, not staging —
> its fixtures hard-code the company `GDL (Demo)` and a location tree that staging does not
> have. So the suite proves the **code** is correct; it does not prove **GDL's staging
> configuration** is correct. That gap is what section 3 is for.

### 1.2 Verified live on staging during this audit (read-only)

| Check | Method | Result |
|---|---|---|
| POL matches the blueprint | Ran `compute_abstract()` on the page-8 inputs | **All 7 figures exact** |
| Dashboard reads the real fleet | Executed each Number Card | Vehicles Active **14**; others 0 |
| Charts render | Executed each Dashboard Chart | Fleet by Site returns all 7 sites |
| Workflows active | Read Workflow records | 3 active, states and roles as designed |
| Reminder ladder | Read Notification records | 14 / 3 enabled; 7 / 3 disabled; expiry+1 enabled |
| Permission levels | Read DocPerm rows | MOR vehicle/driver at permlevel 1; write to Administrator, Approver, System Manager only |
| No DB-resident scripts | Queried Client Script and Server Script | **0 of each** |
| App identity | Read installed apps | `gdl_fleet_extension` 1.0.0; `gdl_fleet_management` **not installed** |

---

## 2. Staging database observations

**No personal data is reproduced below.** Counts and configuration only.

### 2.1 Record counts

| DocType | Records | Can the process be verified from staging data? |
|---|---|---|
| Vehicle | 14 | **Yes** — the full blueprint fleet |
| Fleet Vehicle Type | 4 | Yes |
| Location | 10 | Yes |
| Vehicle Service Item | 17 | Yes |
| Driver | 1 | Barely — one record |
| Employee | 1 | Barely |
| Driver Assignment | 1 | Barely |
| Movement Order Request | 1 | Barely |
| Movement Order | 1 | Barely |
| Vehicle Log | 1 | Barely |
| POL Abstract | 1 | Barely — **no second abstract, so carry-forward is unproven on staging** |
| Asset Maintenance Log | 1 | Barely |
| Supplier | 3 | **BOD and STCBL are not among them** |
| Asset | 3 | For 14 vehicles — Asset Repair not usable fleet-wide |
| **Renewal Register** | **0** | **No** |
| **Fleet Part Issue** | **0** | **No** |
| **Vehicle Tyre** | **0** | **No** |
| **Asset Repair** | **0** | **No** |
| **Asset Maintenance** | **0** | **No** |
| **Stock Entry** | **0** | **No** |

### 2.2 Processes that cannot be verified from existing staging transactions

Stated plainly, as the brief requires:

1. **Insurance and renewal** — 0 Renewal Register records. Status transitions, previous-renewal
   history and the alert ladder are unproven against GDL data.
2. **Spare parts issuance** — 0 Fleet Part Issue records. The Stock Entry integration has
   never run on this database.
3. **Tyre lifecycle** — 0 Vehicle Tyre records. No tyre has been fitted, removed or costed.
4. **Breakdown repair** — 0 Asset Repair records.
5. **Preventive maintenance scheduling** — 0 Asset Maintenance plans.
6. **POL coupon carry-forward** — only 1 abstract exists, so the opening-balance mechanism
   has not run on staging (it is proven by automated test on dev).
7. **Fuel claim to supplier invoice** — BOD and STCBL suppliers absent.
8. **Service bill approval and purchasing** — approver role blank; no bill has ever been approved.

### 2.3 Configuration observations

| Setting | Value | Note |
|---|---|---|
| Movement Order Approval | `Simple` | Two-stage chain live |
| Only the Location MTO May Approve | on | 7 sites configured, Head Office = final MTO |
| Renewal reminders | 14 / 3 / 0 / 0 | Third and Final switched off |
| Mileage tolerance | 10% | HR approval on |
| Tyre target / tolerance | 20,000 km / 20% | Matches the blueprint |
| Booking lead time | 24 h, Require Reason | Emergency bypasses |
| Carry Forward Fuel Book Balance | on | — |
| POL abstract requires attachment | on | — |
| Maintenance rules | 12 | All 6 blueprint intervals present |
| Fuel account rows | 1 — GreenDigital Limited | Correct: one company owns vehicles |
| **Bill Approver Role** | **blank** | **Blocks every service bill** |
| **BOD / STCBL Supplier** | **blank** | **Blocks every fuel claim** |
| **Purchasing Company / Service Item** | **blank** | Blocks purchasing documents |
| **Default Maintenance Team** | **blank** | Blocks preventive plans |
| Insurance PO on expiry | off | Dormant by design |

### 2.4 Role assignment

| Role | Users |
|---|---|
| Fleet User | 14 |
| Fleet Manager | 9 |
| Fleet Approver *(the location MTOs)* | 7 |
| **Fleet Administrator** | **0** |
| **Fleet Driver** | **0** |
| **Fleet HR Approver** | **0** |
| **Fleet Store User** | **0** |
| **Fleet Maintenance User** | **0** |
| Fleet Validator / Reviewer / Finance User | 0 *(dormant chain only)* |

> **Finding.** Five operating roles are held by nobody. Those processes have no named
> operator. Testing them as Administrator proves nothing, because Administrator bypasses
> permission checks entirely.

### 2.5 Environment isolation

`mute_emails: 1` and `pause_scheduler: 1` on the staging site. Deliberate — this database
came from a real system and must not contact real people. **Consequence:** no notification
will be delivered during testing, and the daily insurance job will not run. Test the alert
*configuration* instead of its delivery.

---

## 3. Proposed tests — awaiting approval

**None of the following has been executed.** Each would create or modify records. Approve
individually or as a group.

### 3.1 Low risk — creates drafts only, deletable

| # | Test | Creates | Proves |
|---|---|---|---|
| P-01 | Create a draft Renewal Register expiring in 10 days | 1 draft | Status computes as Due Soon; notice window honoured |
| P-02 | Create a second POL Abstract for a vehicle that has an approved one | 1 draft | **Opening Book Balance carries from the previous closing** — the one blueprint requirement unproven on staging |
| P-03 | Create a draft Movement Order Request at under 24 h notice | 1 draft | Short-notice reason enforced; allocation priority computed |
| P-04 | Open each of the 18 reports with filters | nothing | All filter panels render *(regression test for the 4 repaired reports)* |

### 3.2 Medium risk — submits documents, cancellable but permanent

| # | Test | Creates | Proves |
|---|---|---|---|
| P-05 | Full request → order → dispatch → complete as named users | 1 MOR, 1 MO | The whole approval chain, location-MTO enforcement |
| P-06 | Attempt to approve another site's request | nothing | Refusal names the correct MTO |
| P-07 | Two overlapping orders for one vehicle | 2 MO | Double booking refused |
| P-08 | Two Vehicle Logs for one vehicle on one day | 2 logs | Duplicate refused; odometer updates |
| P-09 | Cancel an earlier Vehicle Log | — | Odometer **recalculates**, does not go backwards |

### 3.3 Higher risk — touches stock or accounting

| # | Test | Creates | Risk |
|---|---|---|---|
| P-10 | Issue a part and a tyre | Fleet Part Issue + **Stock Entry** | Moves real stock; needs items and opening stock first |
| P-11 | Approve a service bill end to end | **Purchase Invoice** | Creates an accounting document; needs the approver role and purchasing settings |
| P-12 | Raise a fuel claim | **Purchase Invoice ×2** | Creates accounting documents; needs BOD and STCBL suppliers |

> **Recommendation.** Run 3.1 and 3.2 on staging. Run 3.3 only after GDL confirms that
> staging accounting documents are acceptable — or run them on a separate copy. Creating a
> Purchase Invoice in a database restored from production is not a decision for the
> implementer to take alone.

### 3.4 Prerequisites before the proposed tests

1. Set passwords for `jamjee.user@`, `jamjee.mto@`, `dochula.mto@`, `headoffice.mto@`.
2. Create at least 2 Drivers with licence numbers, linked to Employees.
3. Assign Fleet Driver, Fleet HR Approver, Fleet Administrator to real users.
4. For 3.3 only: BOD and STCBL suppliers; bill approver role; purchasing company and
   service item; stock items with opening stock.

---

## 4. The full UAT script set

A separate document, **GDL Fleet Test Scripts**, carries **120 numbered test cases** across
14 suites, each with the user to run as, ordered steps and the exact expected result.
44 of them are negative tests — they pass when the system *refuses* you.

23 are marked **Blocked** against the missing prerequisites listed above. About 90 are
runnable once passwords are set.

---

## 5. Defects found and fixed immediately before this audit

Recorded so the audit trail is complete. All are covered by regression tests.

| # | Defect | Impact had it reached production |
|---|---|---|
| 1 | Four reports registered their filters under the wrong report name | Cost by Vehicle, Fuel Consumption, Service Due and Service History showed **no filters at all** |
| 2 | `allow_self_approval` was 0 on *every* transition, including submission | **No user could submit their own vehicle request.** The module would have been unusable on day one |
| 3 | Only Fleet Administrator had write at permlevel 1 | **An MTO's vehicle allocation was silently dropped**, and the order was raised with no vehicle |
| 4 | `cint(x) or 7` in two places | A reminder set to 0 **reverted on every migrate** |
| 5 | Vehicle and driver missing from `REQUEST_FIELD_MAP` | An order created by picking the request on a blank form had **no vehicle or driver** |
| 6 | Dashboard Chart autonames from `chart_name` | Duplicate-entry error aborting `after_migrate` entirely |

Defects 2, 3 and 5 were found by **driving the flow end to end as a named user**, not by
reading code or running the unit suite. That is the argument for executing the proposed
tests in section 3 rather than relying on the 606 automated ones.

---

## 6. Unverified functionality

| Item | Why it could not be verified |
|---|---|
| Notification **delivery** | Email muted, scheduler paused on staging |
| Insurance purchasing job | Switched off; would need settings and an expiring policy |
| POL Abstract print format | Exists; not rendered during a read-only audit |
| Expense Claim integration | Field exists, no automation, no records |
| Asset Repair at fleet scale | Only 3 Assets for 14 vehicles |
| Interaction with `gdl` and `gdl_custom_app` | Two other GDL apps are installed; not in scope. Nothing in `gdl_fleet_extension` references either |
| Behaviour under concurrent users | Single-user inspection only |
| Performance at volume | 14 vehicles and ~1 record per transaction type |

---

## 7. Recommendation

The code is well covered — 606 passing tests, no database-resident scripts, every threshold
configurable. **What is not evidenced is that GDL's own configuration and data work**, and
three of the six defects above were invisible to the unit suite.

Proposed sequence:

1. GDL supplies the prerequisites in §3.4.
2. Run proposed tests 3.1 and 3.2 on staging.
3. Run the 120-case UAT script set, recording Blocked where prerequisites are absent.
4. Decide on §3.3 separately, given it creates accounting documents in a database restored
   from production.

**No development should start until the four business decisions in document 04 are
answered** — the maintenance approach, the reminder ladder, the approval-chain depth
against the signed blueprint, and the Chairman's Office POL account.
