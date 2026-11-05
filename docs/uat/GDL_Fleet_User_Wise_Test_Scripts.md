# GDL Fleet — User-Wise Test Scripts

**Issued:** 4 November 2026 · **Site:** `gdl-staging.localhost`
**Status of every case below: NOT TESTED**, unless marked otherwise. Actual Result columns
are empty because nothing has been executed — see `GDL_Fleet_UAT_Execution_Report.md`.

> **Relationship to the existing suite.** `docs/GDL_Fleet_Test_Scripts.html` already holds
> **120 cases organised by function**. This document does **not** duplicate it. It
> re-organises testing **by user**, as the brief requires, and cross-references the
> existing case IDs (`FL-nn-nn`) wherever one already covers the same ground. Run both:
> this one proves *who* can do a thing, the other proves *what* the thing does.

**Before any of this runs**, the blockers in the Master Plan §4 must be cleared. Every case
is currently **Blocked** for want of a credential.

---

## Conventions

| Status | Meaning |
|---|---|
| Pass | The system did what Expected Result says |
| Fail | It did not — raise a defect |
| **Blocked** | Could not run; the blocker is named |
| Not Tested | In scope, not yet attempted |

**Negative cases are marked 🚫.** A negative case **passes when the system refuses you**.
If you get through, that is a defect however convenient it felt.

**Evidence rule.** Capture the whole browser window including the URL and the logged-in
user shown top-right. A cropped form proves nothing about *who* was acting.

---

## Suite A — Fleet Employee (`Fleet User`)

**Account:** `jamjee.user@gdl.test` · **Blocked by:** no password, no browser
**Existing coverage:** FL-05-01, FL-05-02, FL-05-09, FL-05-10, FL-14-01, FL-14-02

### TC-001 — Login and workspace

| Field | Details |
|---|---|
| Test Case ID | TC-001 |
| Module | Access / Workspace |
| User Role | Fleet User |
| Test Scenario | The employee can log in and reach the fleet workspace |
| Preconditions | Password set; `Fleet User` held |
| Test Data | — |
| Steps | 1. Log in as `jamjee.user@gdl.test`. 2. Open **GDL Fleet** from the home screen. 3. Note which cards are visible. |
| Expected Result | Workspace opens. The dashboard and Reports card are visible. Setup is not usable. |
| Actual Result | *(not tested)* |
| Status | **Blocked** — no password |
| Screenshot | `01_fleet_employee/TC-001_login.png` |
| Remarks | Capture the top-right user menu to prove the account |

### TC-002 — Create a Movement Order Request

| Field | Details |
|---|---|
| Test Case ID | TC-002 |
| Module | Movement |
| User Role | Fleet User |
| Test Scenario | Raise a vehicle request with travel detail and named passengers |
| Preconditions | TC-001 passed |
| Test Data | `UAT-GDL-REQ-001` in **Purpose** |
| Steps | 1. Movement → Movement Order Request → Add. 2. Confirm your name fills in as requester. 3. Set Site = Jamjee, Purpose = `UAT-GDL-REQ-001 …`, Usage, Priority = Routine. 4. Passenger Count = 2; name two people in **Passengers / Officials**. 5. Required Vehicle Type = Bus. 6. Travel date ≥ 48 h ahead; return date/time; Pickup Location; Destination. 7. **Save**. |
| Expected Result | Saves as Draft, numbered `MOR-2026-000nn`. Department fills from Employee. Lead Time Given and Allocation Priority compute. |
| Actual Result | *(not tested)* |
| Status | **Blocked** |
| Screenshot | `01_fleet_employee/TC-002_create_request.png` |
| Remarks | Record the document ID in the Test Data Register |

### TC-003 🚫 — The requester cannot allocate a vehicle

| Field | Details |
|---|---|
| Test Case ID | TC-003 |
| Module | Movement / Permissions |
| User Role | Fleet User |
| Test Scenario | Allocation fields are beyond the requester's reach |
| Preconditions | TC-002 saved |
| Test Data | `UAT-GDL-REQ-001` |
| Steps | 1. On the draft, find **Assigned Vehicle** and **Assigned Driver**. 2. Attempt to set them. 3. Save. |
| Expected Result | **Refused** — fields read-only or values dropped on save. They sit at permission level 1. |
| Actual Result | *(not tested)* |
| Status | **Blocked** — *permission layer already verified by R-06* |
| Screenshot | `09_negative_permission/TC-003_cannot_allocate.png` |
| Remarks | Passes only if allocation is impossible |

### TC-004 — Submit the request

| Field | Details |
|---|---|
| Test Case ID | TC-004 |
| Module | Movement / Workflow |
| User Role | Fleet User |
| Test Scenario | The employee can submit their own request |
| Preconditions | TC-002 |
| Test Data | `UAT-GDL-REQ-001` |
| Steps | 1. Open the draft. 2. Click **Submit for Review**. |
| Expected Result | State → **Pending Review**. |
| Actual Result | *(not tested)* |
| Status | **Blocked** |
| Screenshot | `01_fleet_employee/TC-004_submit.png` |
| Remarks | **Regression test.** This failed once — `allow_self_approval` was 0 on submission, so no user could send in their own request. Covered by FL-05-01. |

### TC-005 — Edit own draft

| Field | Details |
|---|---|
| Test Case ID | TC-005 |
| Module | Permissions |
| User Role | Fleet User |
| Test Scenario | A requester may edit their own draft |
| Preconditions | A draft owned by this user |
| Test Data | `UAT-GDL-REQ-002` |
| Steps | 1. Create a second draft. 2. Change the destination. 3. Save. |
| Expected Result | Saves. `Fleet User` holds write with **`if_owner = 1`**. |
| Actual Result | *(not tested)* |
| Status | **Blocked** |
| Screenshot | `01_fleet_employee/TC-005_edit_own_draft.png` |
| Remarks | — |

### TC-006 🚫 — Cannot open another employee's request

| Field | Details |
|---|---|
| Test Case ID | TC-006 |
| Module | Permissions |
| User Role | Fleet User |
| Test Scenario | `if_owner` keeps one employee out of another's request |
| Preconditions | A request owned by someone else exists — `MOR-2026-00001` (owner: Administrator) |
| Test Data | `MOR-2026-00001` — **read only, do not modify** |
| Steps | 1. Navigate to `/app/movement-order-request/MOR-2026-00001`. |
| Expected Result | **Not permitted.** Verified at the permission layer: `has_permission(doc, "read", jamjee.user)` → `False`. |
| Actual Result | *(not tested in UI; permission layer verified in R-05)* |
| Status | **Blocked** for UI evidence |
| Screenshot | `09_negative_permission/TC-006_other_employee_request.png` |
| Remarks | Do not modify this record |

### TC-007 🚫 — Cannot approve, TC-008 🚫 — Cannot create a Movement Order, TC-009 🚫 — Cannot dispatch

| Field | Details |
|---|---|
| Test Case IDs | TC-007, TC-008, TC-009 |
| Module | Permissions / Workflow |
| User Role | Fleet User |
| Test Scenario | The requester has no approval, creation or dispatch authority |
| Steps | TC-007: open your submitted request, look for Accept/Approve. TC-008: Movement → Movement Order → try to Add. TC-009: open an approved order, look for Dispatch. |
| Expected Result | None of the three is offered. Verified: `has_permission("Movement Order","create", jamjee.user)` → `False`; the workflow grants Fleet User only *Submit for Review*. |
| Actual Result | *(not tested in UI; permission layer verified)* |
| Status | **Blocked** for UI evidence |
| Screenshot | `09_negative_permission/TC-007..009_*.png` |
| Remarks | Covers FL-14-01, FL-14-02 |

### TC-010 — Report visibility

| Field | Details |
|---|---|
| Test Case ID | TC-010 |
| Module | Reports |
| User Role | Fleet User |
| Test Scenario | The employee sees only the reports their role allows |
| Steps | 1. Open the Reports card. 2. Attempt each of the 18. |
| Expected Result | Reports restricted to other roles are not listed or refuse to run. |
| Actual Result | *(not tested)* |
| Status | **Blocked** |
| Screenshot | `10_reports_dashboard/TC-010_user_report_visibility.png` |
| Remarks | — |

---

## Suite B — Location MTO (`Fleet Approver`)

**Accounts:** `jamjee.mto@`, `dochula.mto@`, `headoffice.mto@gdl.test`
**Existing coverage:** FL-05-03 … FL-05-08, FL-06-01 … FL-06-10

| ID | Scenario | User | Expected | Status | Screenshot |
|---|---|---|---|---|---|
| TC-015 | Open a pending request for own site | `jamjee.mto` | Opens; appears in Movement Request Status | Blocked | `02_location_mto/TC-015_review_request.png` |
| TC-016 | **Check Availability** | `jamjee.mto` | Lists only free vehicles of that type; excludes booked and off-road | Blocked | `02_location_mto/TC-016_check_availability.png` |
| TC-017 | Allocate vehicle and driver | `jamjee.mto` | **Saves** — permlevel 1 write. *Regression: this was silently dropped once.* | Blocked | `02_location_mto/TC-017_allocate.png` |
| TC-018 | Accept the request | `jamjee.mto` | State → Accepted, docstatus 1; Assigned By/On stamped | Blocked | `02_location_mto/TC-018_accept.png` |
| TC-019 🚫 | Accept **another site's** request | `dochula.mto` on a Jamjee request | **Refused**, naming the Jamjee MTO and the Head Office MTO. *Verified at the logic layer in R-07.* | Blocked | `09_negative_permission/TC-019_wrong_site.png` |
| TC-020 | Head Office MTO approves any site | `headoffice.mto` on a Dochula request | Accepted — final authority | Blocked | `02_location_mto/TC-020_head_office.png` |
| TC-021 🚫 | MTO accepts **their own** request | `jamjee.mto` | **Refused** — self-approval not allowed on the decision | Blocked | `09_negative_permission/TC-021_self_approval.png` |
| TC-022 | Create Movement Order from the button | `jamjee.mto` | Vehicle, driver, dates, **passengers** all carry | Blocked | `02_location_mto/TC-022_create_mo_button.png` |
| TC-023 | Create Movement Order from a blank form | `jamjee.mto` | **Identical result to TC-022.** *Regression: vehicle and driver were blank on this path.* | Blocked | `02_location_mto/TC-023_create_mo_form.png` |
| TC-024 🚫 | Second order from one request | `jamjee.mto` | Refused, naming the existing order | Blocked | `09_negative_permission/TC-024_duplicate_order.png` |
| TC-025 | Approve the Movement Order | `jamjee.mto` | Draft → Pending Approval → Approved, **two steps only** | Blocked | `02_location_mto/TC-025_approve_mo.png` |
| TC-026 🚫 | Double-book a vehicle | `jamjee.mto` | Refused, naming the clashing order | Blocked | `09_negative_permission/TC-026_double_booking.png` |
| TC-027 🚫 | Change GDL Fleet Settings | `jamjee.mto` | Read-only — settings belong to Fleet Administrator | Blocked | `09_negative_permission/TC-027_settings_denied.png` |

---

## Suite C — Fleet Administrator

**Blocked by:** no holder, no password.

> ✅ **DEF-001 was closed on 4 November 2026.** `Fleet Administrator` now holds read, write
> and create on Vehicle and Driver, and full rights on Vehicle Log — verified at the
> permission layer. This suite is no longer blocked by the defect; it is blocked only
> because **no user holds the role** and no account has a password.

| ID | Scenario | Expected | Status |
|---|---|---|---|
| TC-030 | Create a Vehicle | Saves; Vehicle ID allotted | Blocked — no holder |
| TC-031 🚫 | Change the Vehicle ID | Refused | Blocked |
| TC-032 🚫 | Future manufacturing year | Refused | Blocked |
| TC-033 | Attach a vehicle document | Saves | Blocked |
| TC-034 | Create a Driver + link Employee | Saves | Blocked — no holder |
| TC-035 | Driver Assignment (Primary) | Employee, location, licence auto-fill | Blocked |
| TC-036 🚫 | Overlapping Primary assignment | Refused, naming the clash | Blocked |
| TC-037 | Relief assignment overlapping a Primary | **Accepted** — overlap is the point | Blocked |
| TC-038 | Hand over: To Date + new assignment | Both survive; history shows the chain | Blocked |
| TC-039 | Renewal Register entry | Status computes from expiry | Blocked |
| TC-040 | Renew with Previous Renewal link | Old record → **Renewed**, untouched | Blocked |
| TC-041 | Dispatch and Complete an order | States move correctly | Blocked |
| TC-042 | Open GDL Fleet Settings | Read/write permitted | Blocked |

---

## Suite D — Fleet Driver

**Blocked by:** no holder, no password, no drivers.

> ✅ **DEF-001 closed.** Fleet Driver now holds read, write, create and submit on Vehicle Log
> and Asset Maintenance Log — and is blocked from every cost, bill and purchasing field,
> including `cost` inside the service-items grid. Verified; see
> `DEF-001_Role_Permission_Test_Report.md`.

| ID | Scenario | Expected | Status |
|---|---|---|---|
| TC-050 | Create a Vehicle Log | Opening odometer auto-fills; distance computes | Blocked — no holder |
| TC-051 🚫 | Second log, same vehicle and day | Refused | Blocked |
| TC-052 🚫 | Closing below opening | Refused | Blocked |
| TC-053 | Mileage above 500 km | **Warns, does not block** | Blocked |
| TC-054 | Vehicle odometer updates on submit | Current Odometer = closing | Blocked |
| TC-055 | Cancel an earlier log | Odometer **recalculates**, does not go backwards | Blocked |
| TC-056 | Create a POL Abstract | Driver, opening KM, tank balance, **opening book balance** auto-fill | Blocked |
| TC-057 | Add POL entries | Amount = litres × rate; editable | Blocked |
| TC-058 | BOD / STCBL kept separate | Separate amount, recoupment and balance | Blocked |
| TC-059 🚫 | Submit with no supplier bill | Refused | Blocked |
| TC-060 🚫 | Duplicate supply memo | Refused, naming the abstract | Blocked |
| TC-061 | Verify calculations vs blueprint | All seven figures match | **Verified by R-10** at the calculation layer |
| TC-062 🚫 | Driver approves own POL | Refused — self-approval not allowed | Blocked |

---

## Suite E — Fleet HR Approver

**Blocked by:** no holder, no password.

| ID | Scenario | Expected | Status |
|---|---|---|---|
| TC-070 | View a submitted POL Abstract | Opens; driver and vehicle detail visible | Blocked |
| TC-071 | Verify mileage and deviation | Deviation %, status and reason visible | Blocked |
| TC-072 | Approve a valid abstract | → Approved, docstatus 1 | Blocked |
| TC-073 | Closing balance carries forward | Next abstract opens at this closing figure | Blocked |
| TC-074 🚫 | Approve as an unauthorised user | Refused | Blocked |
| TC-075 | Approval history | Workflow history shows who and when | Blocked |

---

## Suite F — Fleet Maintenance User

**Blocked by:** no holder, no password, no maintenance team.

> ✅ **DEF-001 closed.** Fleet Maintenance User now holds read, write, create and submit on
> Asset Maintenance Log and Asset Repair, with write at level 1 so they can enter the
> supplier, bill and costs — and read-only at level 2, so they cannot edit the approval
> trail.

| ID | Scenario | Expected | Status |
|---|---|---|---|
| TC-080 | Create a service record | One form, no prerequisite | Blocked — no holder |
| TC-081 | Multiple service items in one visit | All recorded against one odometer | Blocked |
| TC-082 | Totals | Parts + labour = total | Blocked |
| TC-083 | Next service date and KM | From the 12 maintenance rules | Blocked |
| TC-084 🚫 | Odometer below last reading | Refused | Blocked |
| TC-085 | Service Due report | Due by date or km; overdue highlighted | Blocked |
| TC-086 | Asset Repair | Only where the vehicle is a fixed Asset (3 of 14) | Blocked |
| TC-087 🚫 | Change fleet settings | Refused | Blocked |

---

## Suite G — Fleet Store User

**Blocked by:** no holder, no password, no stock items — **and stock movement needs
separate written approval.**

| ID | Scenario | Expected | Status |
|---|---|---|---|
| TC-090 | Open Fleet Part Issue | Opens | Blocked |
| TC-091 🚫 | Tyre with quantity 2 | Refused — one tyre per row | Blocked *(validation only, no posting)* |
| TC-092 🚫 | Serialised item, no serial | Refused | Blocked *(validation only)* |
| TC-093 🚫 | Same serial twice | Refused | Blocked *(validation only)* |
| TC-094 | **Submit** a part issue | Stock Entry raised; Vehicle Tyre created with its cost | **Blocked — needs stock approval** |
| TC-095 | Remove a tyre | KM achieved; classified against 20,000 ±20% | Blocked |

> TC-091 to TC-093 are **non-posting validations** and could run without moving stock, once
> a credential and a stock item exist. TC-094 posts and needs your approval.

---

## Suite H — Fleet Manager (reports and dashboard)

**Blocked by:** no password for a Fleet-Manager-only account.
**Existing coverage:** FL-13-01 … FL-13-11

| ID | Scenario | Expected | Status |
|---|---|---|---|
| TC-100 | Dashboard | Vehicles Active **14**; others 0 | **Values verified by R-11**; UI blocked |
| TC-101 | The five charts | Fleet by Site shows all 7 sites | **Verified by R-11**; UI blocked |
| TC-102 | **Filters on the four repaired reports** | Cost by Vehicle, Fuel Consumption and Performance, Service Due, Service History **all show filters** | Blocked |
| TC-103 | Fleet Register | 14 vehicles with type, odometer, site, status | Blocked |
| TC-104 | Vehicle Availability | Booked vehicles excluded for the window | Blocked |
| TC-105 | Vehicle Utilization | KM/day, utilisation %, idle days | Blocked |
| TC-106 | Driver Assignment History | Assignments by effective period | Blocked |
| TC-107 | Movement Request Status | Pending/accepted/rejected + turnaround | Blocked |
| TC-108 | Movement Order Register | By vehicle, driver, department, period | Blocked |
| TC-109 | Insurance and Renewal Due | Days to expiry; expired highlighted | Blocked — **0 renewal records** |
| TC-110 | Service History / Service Due | Costs and due items | Blocked |
| TC-111 | POL Summary Register | Abstract totals and status | Blocked |
| TC-112 | POL Supplier / Book Balance | **Opening → Recoupment → Closing** | Blocked |
| TC-113 | Fuel Consumption and Performance | KM, fuel, KM/L | Blocked |
| TC-114 | Mileage Deviation Dashboard | BYD EV shows **Not Applicable** | Blocked |
| TC-115 | Tyre Mileage / Tyre Cost Analysis | Cost per km; grouped column matches grouping | Blocked — **0 tyres** |
| TC-116 | Parts Consumption / Replacement History | Drafts excluded; KM between fittings | Blocked — **0 issues** |
| TC-117 | Cost by Vehicle | Cost per km from the GL | Blocked |
| TC-118 | Export | CSV/Excel download works | Blocked |

**TC-102 is the highest-value case in this suite.** Those four reports showed **no filters
at all** until 3 November 2026. It is a pure regression check and needs no test data.

---

## Coverage against the brief's 32 functional areas

| Covered by a case here | Areas |
|---|---|
| Fully | 1–16, 21–24, 27–32 |
| Partly | 17–20 *(maintenance — blocked by DEF-001)*, 25–26 *(expenses/purchasing — needs accounting approval)* |
| **Not covered — nothing exists** | **SAP integration — NOT IMPLEMENTED, will not be simulated** |

---

## Summary

| | Count |
|---|---|
| User-wise cases defined | 96 |
| Executed | **0** |
| Blocked | **96** |
| Verified at the logic layer instead | 8 *(TC-003, 006, 007–009, 019, 061, 100, 101)* |

The eight noted above were confirmed read-only during Phase 1 — permission evaluation,
approval routing, POL arithmetic and dashboard values. That is genuine evidence of the
**rule**, but not of the **user experience**, and it carries no screenshot. They remain
Blocked for UAT sign-off purposes.
