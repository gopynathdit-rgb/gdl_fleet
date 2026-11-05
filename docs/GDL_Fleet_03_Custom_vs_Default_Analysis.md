# GDL Fleet — Custom vs Default Technical Analysis

**Audit date:** 4 November 2026 · **Application:** `gdl_fleet_extension` v1.0.0
**Evidence:** DocType `module` and owning app read from the database; custom fields and
property setters filtered on `module = "GDL Fleet"`; hooks read from
`frappe.get_hooks(app_name="gdl_fleet_extension")`.

## Classification key

| Term | Meaning |
|---|---|
| **DEFAULT** | Ships with Frappe/ERPNext/HRMS v16. Verified by reading the DocType's owning app, not by the blueprint's claim. |
| **CONFIGURATION** | Standard functionality switched on or populated with data. No new code. |
| **CUSTOM** | A DocType, report or module written for GDL. |
| **CUSTOM EXTENSION** | A standard DocType with GDL fields and GDL logic attached. |
| **PARTIALLY IMPLEMENTED** | Works, but part of the requirement is absent. |
| **NOT IMPLEMENTED** | Absent. |
| **NEEDS VERIFICATION** | Could not be confirmed from code or staging data. |

---

## 1. Who owns the base DocTypes

The blueprint repeatedly calls things "standard". Verified against the installed source:

| DocType | Module | Owning app | Verdict |
|---|---|---|---|
| Vehicle | Setup | **erpnext** | DEFAULT — note: *erpnext*, not hrms as often assumed |
| Driver | Setup | **erpnext** | DEFAULT |
| Vehicle Log | HR | **hrms** | DEFAULT |
| Vehicle Service Item | HR | **hrms** | DEFAULT |
| Asset Maintenance / Task / Log | Assets | **erpnext** | DEFAULT |
| Asset Repair | Assets | **erpnext** | DEFAULT |
| Maintenance Schedule / Visit | Maintenance | **erpnext** | DEFAULT — **present but unused** |
| Stock Entry, Serial No | Stock | **erpnext** | DEFAULT |
| Expense Claim | HR | **hrms** | DEFAULT |
| Purchase Order / Invoice, Payment Entry | Accounts | **erpnext** | DEFAULT |
| Location, Cost Center, Department, Project | — | **erpnext** | DEFAULT |

**The blueprint's "Frappe HR ships a native Fleet Management module" is accurate but
thin.** What HRMS actually provides is Vehicle Log and Vehicle Service Item — a trip log
and a service-item list. Vehicle and Driver come from erpnext. There is no native renewal
register, no movement order, no POL, no driver-assignment history and no fleet workflow.
Everything GDL's blueprint describes as policy sits on top.

---

## 2. Custom DocTypes (17)

| DocType | Type | Submittable | Business purpose | Status |
|---|---|---|---|---|
| **Movement Order Request** | txn | yes | Employee asks for a vehicle; MTO allocates and accepts | CUSTOM |
| **Movement Order** | txn | yes | Approved authority to travel | CUSTOM |
| **Driver Assignment** | txn | yes | Dated driver-to-vehicle history | CUSTOM |
| **Renewal Register** | txn | yes | Insurance, registration, fitness, emission, permit, road tax | CUSTOM |
| **POL Abstract** | txn | yes | Periodic fuel statement and claim | CUSTOM |
| **Fleet Part Issue** | txn | yes | Spare part and tyre issuance | CUSTOM |
| **Vehicle Tyre** | txn | no | One tyre's life, fitted to removed | CUSTOM |
| **Fleet Vehicle Type** | master | no | Car/SUV/Bus/Pickup with defaults | CUSTOM |
| **GDL Fleet Settings** | single | no | Every threshold in the system | CUSTOM |
| POL Entry | child | — | One fuel supply line | CUSTOM |
| Movement Order Passenger | child | — | Named officials travelling | CUSTOM |
| Fleet Part Issue Item | child | — | Issued part, serial, tyre position | CUSTOM |
| Fleet Service Item | child | — | One job in a service visit | CUSTOM |
| Fleet Vehicle Document | child | — | Attachments on the vehicle | CUSTOM |
| GDL Fleet Maintenance Rule | child | — | Service interval, km and months | CUSTOM |
| GDL Fleet Fuel Account | child | — | Fuel expense account per company | CUSTOM |
| GDL Fleet Location Officer | child | — | Requester and MTO per site | CUSTOM |

No custom DocType duplicates a standard one. Each exists because ERPNext has no equivalent.

---

## 3. Standard DocTypes extended — 101 custom fields

| DocType | Fields | What the extension adds | Status |
|---|---|---|---|
| **Asset Maintenance Log** | 32 | Vehicle, odometer, location, service provider, the maintenance-items table, costs, **the whole service-bill and purchasing cycle** (bill no/date/attachment, bill status, approver, purchase order, purchase invoice, payment status) | CUSTOM EXTENSION |
| **Vehicle** | 30 | GDL vehicle ID, vehicle type, status, ownership, engine no, capacity, manufacturing year, site/department/cost centre/project, opening odometer, min mileage, registration & inspection expiry, documents table | CUSTOM EXTENSION |
| **Vehicle Log** | 19 | Driver, movement order, usage type, start/destination, place to travel, **opening odometer and distance travelled**, dimensions | CUSTOM EXTENSION |
| **Asset Repair** | 10 | Vehicle, odometer, location, service provider, maintenance category, next service date/km | CUSTOM EXTENSION |
| **Asset Maintenance Task** | 4 | Interval km, service item, next due odometer, last completion odometer | CUSTOM EXTENSION |
| **Driver** | 4 | Site, default vehicle | CUSTOM EXTENSION |
| **Asset Maintenance** | 1 | Vehicle | CUSTOM EXTENSION |
| **Purchase Invoice** | 1 | `pol_abstract` link, so a fuel claim traces back | CUSTOM EXTENSION |

### Property setters (16) — relabelling, not rebuilding

GDL's vocabulary is applied to standard fields rather than new fields being created:

| Standard field | Relabelled to |
|---|---|
| `Vehicle.license_plate` | Registration Number |
| `Vehicle.last_odometer` | Current Odometer (KM) |
| `Vehicle.end_date` / `start_date` | Insurance Expiry / Insurance Start Date |
| `Vehicle.employee` | Responsible Employee |
| `Vehicle Log.odometer` | Closing Odometer |
| `Asset Maintenance Log.completion_date` | Service Date |
| `Asset Repair.failure_date` | Repair / Failure Date |

`Vehicle.location` is **hidden** and relabelled *(deprecated — use Site)*, because the
custom `site` field points at the GDL location tree instead. Fuel type options are
extended to the blueprint's list.

---

## 4. Python logic

| File | Attached by | What it does |
|---|---|---|
| `overrides/vehicle.py` | `doc_events` → `Vehicle.validate` | Allots and freezes the GDL vehicle ID; validates manufacturing year, leaf site, asset link uniqueness and opening odometer |
| `overrides/vehicle_log.py` | **`override_doctype_class`** | Replaces HRMS's `VehicleLog` class. Sets opening odometer, validates the range, warns on abnormal mileage, and **recomputes the vehicle odometer from live readings instead of subtracting** — HRMS's own method is defective on cancellation |
| `overrides/asset_maintenance.py` | `doc_events` on Asset Maintenance Log and Asset Repair | Vehicle from asset, total cost, odometer validation, next-due sync, and the service-bill purchasing cycle |
| `utils/fleet_purchase_automation.py` | `doc_events` on Purchase Invoice and Payment Entry, plus the daily job | Raises purchasing documents from approved bills; reads payment status back |
| `utils/pol.py` | called by POL Abstract | Every POL figure, in `Decimal`. Verified against the blueprint's page-8 sheet |
| `utils/location_officers.py` | called by MOR and MO validate | Resolves who may approve for a site |
| `utils/mileage_deviation.py`, `utils/tyre.py`, `utils/parts.py`, `utils/odometer.py` | reports and controllers | Deviation classification, tyre band and cost per km, parts consumption and replacement intervals |

**`override_doctype_class` on Vehicle Log is the only class replacement in the app** and
deserves attention at every ERPNext upgrade — it subclasses HRMS's controller.

---

## 5. Workflows — CONFIGURATION, created from code

The standard Frappe Workflow engine; the three workflows are data, created idempotently by
`setup/workflows.py` so they are reproducible across environments.

| Workflow | DocType | States | Approval |
|---|---|---|---|
| GDL Movement Order Request Review | Movement Order Request | Draft → Pending Review → Accepted / Rejected / Cancelled | Fleet Approver (the site MTO) or Fleet Administrator |
| GDL Movement Order Approval | Movement Order | Draft → Pending Approval → Approved → Dispatched → Completed | Fleet Approver |
| GDL POL Approval | POL Abstract | Draft → Submitted → Approved / Rejected / Cancelled | Fleet HR Approver |

`allow_self_approval` is set per action, not globally: **1** on Submit/Resubmit/Dispatch/
Complete/Cancel (the originator acting on their own document) and **0** on Accept/Reject
and on the POL Approve. The Movement Order's Approve is 1 because the decision was already
taken when the MTO accepted the request.

The retired five-stage states (Pending Validation, Pending Review, Pending MTO/CEO,
Pending FAS) **still exist** so a part-approved order is never stranded; they are
unreachable while the chain is Simple.

---

## 6. Notifications — CONFIGURATION

Twelve standard Notification records, created by `setup/notifications.py`. **The app
registers no scheduler job for them** — frappe's own `trigger_daily_alerts` drives them,
which is the correct arrangement.

| Alert | Trigger | Days | State |
|---|---|---|---|
| Renewal Due (First / Second) | Days Before `expiry_date` | 14 / 3 | enabled |
| Renewal Due (Third / Final) | Days Before `expiry_date` | 7 / 3 | **disabled** |
| Renewal Expired | Days After | 1 | enabled |
| Driving Licence Expiry | Days Before | 14 | enabled |
| Maintenance Due / Overdue | Days Before / After `due_date` | 14 / 1 | enabled |
| Movement Request Pending Review / Accepted / Rejected | Value Change | — | enabled |
| Movement Order Pending Approval | Value Change | — | enabled |

Recipients are **roles or document fields only** — no user is hard-coded into an alert.

---

## 7. Scheduled and background jobs

```
scheduler_events.daily = [
  gdl_fleet_extension.utils.fleet_purchase_automation.daily_fleet_purchasing
]
```

**One job.** It raises purchase orders for expiring insurance policies, and does nothing at
all while `Raise Purchase Order When Insurance Expires` is off — which it is. Everything
else is form-driven or driven by frappe's own alert job.

---

## 8. Reports — 18, all CUSTOM Script Reports

| Report | Source DocType |
|---|---|
| Fleet Register, Vehicle Availability, Vehicle Utilization, Cost by Vehicle | Vehicle |
| Driver Assignment History | Driver Assignment |
| Movement Request Status | Movement Order Request |
| Movement Order Register | Movement Order |
| Insurance and Renewal Due | Renewal Register |
| Service Due | Asset Maintenance |
| Service History | Asset Repair *(reads Asset Maintenance Log too)* |
| POL Summary Register, POL Supplier and Book Balance, Fuel Consumption and Performance, Mileage Deviation Dashboard | POL Abstract |
| Tyre Mileage Report, Tyre Cost Analysis | Vehicle Tyre |
| Parts Consumption, Part Replacement History | Fleet Part Issue |

All are Script Reports (Python + a JS filter file), role-restricted, and read live
documents. None stores an aggregate, so no report can drift from the records beneath it.

---

## 9. Dashboard — CONFIGURATION

Standard Number Card and Dashboard Chart records (`setup/dashboard.py`).

> **Technical note for maintainers:** both DocTypes take their **record name from their own
> title** — Dashboard Chart through `autoname: field:chart_name`. Code that assumes a
> separate id will create duplicates on every migrate. The builder keys on the title and
> refuses to touch a record belonging to another module.

---

## 10. Roles and permissions

Eleven custom roles. Current assignment on staging:

| Role | Users | Note |
|---|---|---|
| Fleet User | 14 | Every fleet account |
| Fleet Manager | 9 | Read-everything |
| Fleet Approver | 7 | **The location MTOs** |
| Fleet Administrator, Fleet Driver, Fleet HR Approver, Fleet Store User, Fleet Maintenance User | 0 | **Not yet assigned to anyone** |
| Fleet Validator, Fleet Reviewer, Fleet Finance User | 0 | Only used by the dormant five-stage chain |

**Finding:** with Fleet Driver, Fleet HR Approver, Fleet Store User, Fleet Maintenance User
and Fleet Administrator held by nobody, those processes cannot be performed by any named
user today — only by Administrator, who bypasses permissions and therefore proves nothing
in testing.

### Field-level permissions

`Movement Order Request.vehicle`, `.driver` and `.assignment_remarks` sit at **permlevel 1**.
Read is granted to all fleet roles; **write only to Fleet Administrator, Fleet Approver and
System Manager**. This is what stops a requester allocating their own vehicle.

---

## 11. Accounting integration — CONFIGURATION of a standard feature

**Vehicle is registered as an ERPNext Accounting Dimension** (`setup/accounting_dimension.py`).
A `vehicle` field is therefore present on GL Entry, Purchase Invoice, Expense Claim, Stock
Entry, Journal Entry and every other dimension-bearing DocType.

This is why *Cost by Vehicle* reports real money without a separate fleet ledger, and why
the standard General Ledger and Budget Variance reports can be filtered by vehicle. It is
the most valuable single piece of configuration in the implementation.

---

## 12. What is deliberately absent

| Not present | Why that is correct |
|---|---|
| Client Scripts in the database | All client logic is in versioned `.js` files |
| Server Scripts in the database | All server logic is in versioned `.py` files |
| Hard-coded thresholds | Every one is a field in GDL Fleet Settings |
| Hard-coded users in alerts | Recipients are roles or document fields |
| A fleet-specific stock ledger | Stock moves through standard Stock Entry |
| A fleet-specific cost ledger | Vehicle is an accounting dimension |

---

## 13. Components that need verification

| Component | Why |
|---|---|
| `Driving Licence Expiry` alert at 14 days | Follows the renewal first-rung setting. Confirm that is intended — a licence is not a policy. |
| Asset Repair requiring `asset` | Breakdowns need the vehicle linked to a fixed Asset. Only 3 Assets exist against 14 vehicles. |
| `gdl` and `gdl_custom_app` | Two other GDL apps are installed. Their interaction with fleet was not audited; nothing in `gdl_fleet_extension` references them. |
| Print Format "POL Abstract" | Exists; not rendered during this read-only audit. |
