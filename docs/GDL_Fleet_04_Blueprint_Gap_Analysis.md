# GDL Fleet — Blueprint vs Developed Application: Gap Analysis

**Blueprint:** GDL Fleet Management Business Blueprint v1.00, October 2026
**Application:** `gdl_fleet_extension` v1.0.0 on `gdl-staging.localhost`
**Audit date:** 4 November 2026

A requirement is marked **Fully Implemented** only where the business logic and the
connections to other processes were verified, not merely where a DocType exists.

---

## 1. The blueprint's own functional-requirement table (section 4, items 1–11)

| No. | Blueprint requirement | Expected process | Actual implementation | Default/Custom | Status | Missing |
|---|---|---|---|---|---|---|
| 1 | Vehicle Master — "Standard Vehicle + custom fields" | Permanent vehicle identity and status | erpnext `Vehicle` + 30 custom fields + 12 property setters + validate hook | CUSTOM EXTENSION | **Fully Implemented** | Chassis/engine numbers and acquisition dates blank on staging (data) |
| 2 | Driver Assignment — "Custom DocType" | Date-effective driver-to-vehicle assignment | `Driver Assignment`, submittable, overlap rule on Primary | CUSTOM | **Fully Implemented** | — |
| 3 | Daily KM Log — "Vehicle Log / custom Daily KM Log" | Odometer trail and utilisation | hrms `Vehicle Log` + 19 fields + `GDLVehicleLog` class override | CUSTOM EXTENSION | **Fully Implemented** | — (blueprint permitted either; Vehicle Log was chosen) |
| 4 | Service & Maintenance — "Vehicle Log + Service child table" | Service history and due tracking | erpnext Asset Maintenance Log + `Fleet Service Item` child table | CUSTOM EXTENSION | **Fully Implemented** | Blueprint named the wrong parent DocType — see §3 |
| 5 | Insurance & Renewals — "Custom Renewal Register" | Policy details, expiry, reminders | `Renewal Register` + 5 Notifications | CUSTOM | **Fully Implemented** | 0 records on staging — unverified against GDL data |
| 6 | Movement Order Request — "Custom DocType + Workflow" | Employee request, accept/reject | `Movement Order Request` + workflow + location-MTO rule | CUSTOM | **Fully Implemented** | — |
| 7 | Movement Order — "Custom DocType" | Approved dispatch document | `Movement Order` + workflow | CUSTOM | **Fully Implemented** | — |
| 8 | Movement Approval — "Workflow" | Authorised approval before dispatch | `GDL Movement Order Approval`, 2 stages | CONFIGURATION | **Fully Implemented** | Blueprint's 5 stages built but switched off — **client decision, recorded** |
| 9 | Alerts — "Frappe Notification" | Renewal expiry alerts | 12 Notifications, frappe's own daily job | CONFIGURATION | **Fully Implemented** | Reminder ladder contradicts itself in the blueprint — see §4 |
| 10 | Reports & Dashboard | Analytics and fleet status | 18 Script Reports + 5 cards + 5 charts + workspace | CUSTOM / CONFIGURATION | **Fully Implemented** | — |
| 11 | POL Management — "Custom POL Abstract + POL Entry child table" | Fuel supply, recoupment, balances, efficiency | `POL Abstract` + `POL Entry`; page-8 example reproduced exactly | CUSTOM | **Fully Implemented** | Fuel suppliers not created — claim cannot be raised |

---

## 2. Master data requirements (blueprint §4.1–4.3)

| Blueprint field | Implementation | Default/Custom | Status |
|---|---|---|---|
| Vehicle Number (unique, mandatory) | `license_plate`, relabelled *Registration Number*, names the record | DEFAULT + property setter | Fully Implemented |
| Vehicle Type (Car, SUV, Bus, Truck, Utility) | `vehicle_type` → `Fleet Vehicle Type` master | CUSTOM | Fully Implemented |
| Make / Model / Chassis / Colour / Fuel Type / Acquisition Date | Standard Vehicle fields | DEFAULT | Fully Implemented |
| Engine Number, Capacity, Manufacturing Year | Custom fields | CUSTOM EXTENSION | Fully Implemented |
| Current Odometer | `last_odometer`, relabelled, maintained by Vehicle Log | DEFAULT + logic | Fully Implemented |
| Location | Custom `site` → `Location`; standard `location` hidden | CUSTOM EXTENSION | Fully Implemented |
| Vehicle Status (Active / Under Maintenance / Unavailable / Disposed) | `vehicle_status`, read-only, system-maintained | CUSTOM EXTENSION | Fully Implemented |
| Responsible driver / employee | Custom `driver` + standard `employee` | CUSTOM EXTENSION | Fully Implemented |
| Registration and insurance details, expiry dates | Standard insurance fields + custom registration/inspection expiry | CUSTOM EXTENSION | Fully Implemented |
| Cost Centre / Department / Project | Custom link fields | CUSTOM EXTENSION | Fully Implemented |
| Attachments | `documents` → `Fleet Vehicle Document` child table | CUSTOM | Fully Implemented |
| **Driver Assignment** — vehicle, location, driver, licence, dates, type, status, purpose | All present | CUSTOM | Fully Implemented |
| From Date ≤ To Date; no overlapping active Primary | Both enforced | CUSTOM | Fully Implemented |
| Active driver fetched into Movement Order, with temporary override | `get_active_driver()`, order preference Temporary → Relief → Primary | CUSTOM | Fully Implemented |
| **Renewal Register** — type, vehicle, location, certificate no, provider, dates, premium, attachment, status, previous renewal | All present | CUSTOM | Fully Implemented |

---

## 3. Maintenance — the one structural deviation

| Blueprint says | Implementation uses | Assessment |
|---|---|---|
| "Maintenance chart configured in ERPNext **Maintenance Schedule**" | `Asset Maintenance` + `Asset Maintenance Task` | Deviation |
| "Records stored in ERPNext **Log Book** with KM readings" | `Asset Maintenance Log` (+ `Asset Repair` for breakdowns) | Deviation — *"Log Book" is not an ERPNext DocType* |
| "Spare parts verification via ERPNext **Item Serial Number** tracking" | Standard `Serial No` via `Fleet Part Issue Item` | Matches |

**Evidence that the deviation is correct:** ERPNext's Maintenance module targets equipment
sold to customers. `Maintenance Visit` makes `customer` mandatory, and `Maintenance
Schedule` requires an items table and company. Applying it to GDL's own fleet would force a
Customer record and a sales item per vehicle before any oil change could be logged.
`Asset Maintenance Log` requires only `naming_series` and `maintenance_status` — a single
form with no prerequisites, which is the simple flow GDL asked for.

| No. | Requirement | Actual | Status |
|---|---|---|---|
| 3.1 | Service record: vehicle, location, date, odometer, service type, provider, description, parts, labour, total, invoice ref | All on Asset Maintenance Log + `Fleet Service Item` | Fully Implemented |
| 3.2 | Multiple maintenance items in one visit | `service_items` child table | Fully Implemented |
| 3.3 | Next service date **or** odometer | `next_due_date`, `next_due_odometer`, whichever falls first | Fully Implemented |
| 3.4 | "Service Due Soon" and "Service Overdue" lists | `Service Due` report + 2 Notifications | Fully Implemented |
| 3.5 | Maintenance chart (6 items in the blueprint table) | 12 rules seeded, including all 6 | Fully Implemented |
| 3.6 | Link maintenance expense to Cost Centre / Project | Custom fields on the log, carried to the purchase document | Fully Implemented |
| 3.7 | Maintenance history for the vehicle lifecycle | `Service History` report | Fully Implemented |
| 3.8 | Preventive **scheduling** | Asset Maintenance plans | **Needs Configuration** — `Default Maintenance Team` blank, 0 plans exist |
| 3.9 | Breakdown repair | `Asset Repair` | **Partially Implemented** — requires the vehicle to be a fixed Asset; only 3 Assets for 14 vehicles |

> **Decision required:** accept Asset Maintenance in writing. And decide whether breakdowns
> go through Asset Repair (needs every vehicle registered as an Asset) or through the
> maintenance log marked *Corrective* (no prerequisite).

---

## 4. Alerts — the blueprint contradicts itself

| Blueprint location | Stated value |
|---|---|
| §4.6 heading "Alerts 14 days Before Annual Renewal Expiry" | 14 |
| §4.6 narrative | 14 |
| §4.6 trigger detail, `Days Before` | **30** |
| §4.6 recommended escalation | 7, 3, on expiry |
| §5 report requirement "Insurance/Renewal Due" | **30 / 15 / 7** |

**Configured:** 14 and 3 days before, plus 1 day after expiry. Third (7) and Final (3)
rungs exist and are **disabled**.

| Status | **Business Clarification Required** |
|---|---|

The blueprint cannot be implemented as written. The live values follow the client's
instruction of 3 November 2026. Confirm or restate.

---

## 5. POL — verified against the blueprint's own example

Blueprint §4.10 and the page-8 POL Abstract for BG-1-A2397.

| Blueprint figure | Expected | Computed by the app | Status |
|---|---|---|---|
| Total (litres) | 154.81 | 154.81 | Fully Implemented |
| Total amount (STCBL) | 16,339.43 | 16,339.43 | Fully Implemented |
| Total Km | 1,079 | 1,079 | Fully Implemented |
| Previous / present tank balance | 40 / 60 | carried as entered | Fully Implemented |
| Fuel book balance (BOD) | 15,000.00 | 15,000.00 | Fully Implemented |
| Fuel book balance (STCBL) | 3,660.57 | 3,660.57 | Fully Implemented |
| Total fuel consumed | 134.81 | 134.81 | Fully Implemented |
| Performance per litre | 8.00 | 8.00 | Fully Implemented |
| Submitted By / Approved by (Driver → Head-HR) | POL workflow: Fleet Driver → Fleet HR Approver | Fully Implemented |

| No. | POL requirement | Actual | Status |
|---|---|---|---|
| 5.1 | Capture vehicle, location, date, fuel type, litres, rate, amount, odometer, supplier, driver | All on `POL Entry` / `POL Abstract` | Fully Implemented |
| 5.2 | "Fuel details filled in only after multiple fill-ups, once the recoupment amount has been reached" | Abstract accumulates many `POL Entry` rows per period | Fully Implemented |
| 5.3 | Two providers, BOD and STCBL, maintained separately | Separate amount, recoupment and balance columns throughout | Fully Implemented |
| 5.4 | **"where to-date amount should be maintained"** | Opening Book Balance carried from the previous approved abstract; closing = opening + recouped − spent | **Fully Implemented** *(added after the blueprint gap review)* |
| 5.5 | "fuel invoice and payment made based on the detailed amount claimed from each provider" | One Purchase Invoice per provider, linked back via `Purchase Invoice.pol_abstract` | **Needs Configuration** — BOD/STCBL suppliers do not exist |
| 5.6 | Fuel efficiency, comparison between vehicles, abnormal consumption | `Fuel Consumption and Performance`, `Mileage Deviation Dashboard` | Fully Implemented |
| 5.7 | Historical fuel records | Every abstract retained; cancel/amend, never delete | Fully Implemented |

---

## 6. Utilization, mileage and tyres

| No. | Requirement | Actual | Status |
|---|---|---|---|
| 6.1 | Mileage monitoring via Vehicle Log | Vehicle Log + POL Abstract | Fully Implemented |
| 6.2 | **"Deviation >10% requires HR approval workflow"** | Deviation computed both ways; beyond tolerance the abstract is **blocked until a Deviation Reason is entered**, then reviewed by HR on the existing POL chain | **Partially Implemented** |
| 6.3 | Mileage chart — 14 vehicles with Min Required | All 14 loaded with their minimums | Fully Implemented |
| 6.4 | Tyre target 20,000 km ±20% | `tyre_target_km` / `tyre_tolerance`; classification Below/Within/Above | Fully Implemented |
| 6.5 | Tyre issuance via Stock Entry | `Fleet Part Issue` raises a Material Issue | Fully Implemented |
| 6.6 | Tyre replacement tracking | `Vehicle Tyre`, fitted → removed with km achieved | Fully Implemented |
| 6.7 | **Tyre cost analysis** | `Tyre Cost Analysis` report, cost per km | Fully Implemented |
| 6.8 | Parts consumption | `Parts Consumption` report | Fully Implemented |
| 6.9 | Replacement history | `Part Replacement History` report, km and days between fittings | Fully Implemented |
| 6.10 | Serial number tracking | Standard `Serial No`, validated on issue | Fully Implemented |
| 6.11 | **"Expense tracking via ERPNext Accounts → SAP integration"** | Nothing exists | **Not Implemented** |

**On 6.2:** the blueprint asks for an *approval workflow*. What exists is a hard block plus
a flag on the existing approval. One approval, not two. If GDL wants a deviating abstract
routed to a different or additional approver, that is not built.

---

## 7. Reports (blueprint §5, items 1–13)

| # | Blueprint report | Implemented as | Filters | Status |
|---|---|---|---|---|
| 1 | Fleet Register | `Fleet Register` | yes | Fully Implemented |
| 2 | Vehicle Utilization | `Vehicle Utilization` | yes | Fully Implemented |
| 3 | Driver Assignment History | `Driver Assignment History` | yes | Fully Implemented |
| 4 | Service History / Maintenance Record History | `Service History` | yes | Fully Implemented |
| 5 | Service Due Report | `Service Due` | yes | Fully Implemented |
| 6 | Insurance/Renewal Due — "30/15/7-day" | `Insurance and Renewal Due` | yes | Fully Implemented *(see §4 on the ladder)* |
| 7 | Movement Request Status | `Movement Request Status` | yes | Fully Implemented |
| 8 | Movement Order Register | `Movement Order Register` | yes | Fully Implemented |
| 9 | Vehicle Availability | `Vehicle Availability` | yes | Fully Implemented |
| 10 | Cost by Vehicle | `Cost by Vehicle` | yes | Fully Implemented |
| 11 | POL Summary Register | `POL Summary Register` | yes | Fully Implemented |
| 12 | Fuel Consumption & Performance | `Fuel Consumption and Performance` | yes | Fully Implemented |
| 13 | POL Supplier / Book Balance | `POL Supplier and Book Balance` | yes | Fully Implemented |
| — | *(beyond blueprint)* | Mileage Deviation Dashboard, Tyre Mileage, Tyre Cost Analysis, Parts Consumption, Part Replacement History | yes | — |

**Note:** four of these reports — Cost by Vehicle, Fuel Consumption and Performance,
Service Due and Service History — registered their filter definitions under the wrong
report name and therefore **rendered no filters at all** until that was fixed on
3 November 2026. Re-test after any future change (test FL-13-02).

---

## 8. The blueprint's GAP and Custom Development table (§6)

| # | Blueprint GAP item | Actual | Status |
|---|---|---|---|
| 1 | Online booking / requisition (OFMS) with lead-time rules and allocation priority | `Movement Order Request` with `booking_lead_time_hours`, `lead_time_waiver_reason`, `allocation_priority` — **desk only, no portal** | **Fully Implemented** per the client's 3 Nov answer: *"it should be internal only"* |
| 2 | POL form — claim based on recoupment per provider, plus mileage | `POL Abstract` | Fully Implemented |
| 3 | Multi-level approval chain (User → Validate → Reviewer → MTO/CEO → FAS) | Built, **switched off**; live chain is 2 stages | **Business Clarification Required** — superseded by the client's 3 Nov instruction, recorded but not reconciled with the signed blueprint |
| 4 | Mileage Report / Dashboard, ±10% deviation and 20,000 km ±20% tyre tracking | `Mileage Deviation Dashboard`, `Tyre Mileage Report`, `Tyre Cost Analysis`, plus the workspace dashboard | Fully Implemented |
| 5 | Spare-part and tyre issuance/validation forms integrated with Stock Entry and Expense Claim | `Fleet Part Issue` → Stock Entry; `expense_claim` link present | **Partially Implemented** — the Stock Entry path is built and tested; the Expense Claim path has a field but **no records and no automation**, so it is unverified |
| 6 | Reports | 18 delivered | Fully Implemented |

---

## 9. Summary by status

| Status | Count | Items |
|---|---|---|
| **Fully Implemented** | 52 | The great majority of the blueprint |
| **Partially Implemented** | 4 | ±10% HR approval workflow (6.2); Asset Repair needing an Asset (3.9); Expense Claim integration (GAP 5); staging data too thin to verify several processes |
| **Needs Configuration** | 6 | Bill approver role; purchasing company and service item; BOD/STCBL suppliers; maintenance team; drivers and employees; user passwords |
| **Not Implemented** | 1 | **SAP integration** |
| **Business Clarification Required** | 4 | Reminder ladder; maintenance approach; approval chain depth vs the signed blueprint; Chairman's Office POL account |
| **Needs Verification** | 4 | Driving licence alert at 14 days; `gdl` / `gdl_custom_app` interaction; POL print format; Expense Claim path |

---

## 10. What would stop go-live today

In order of severity:

1. **No fuel claim can be raised** — BOD and STCBL suppliers do not exist.
2. **No service bill can be approved** — `Bill Approver Role` is blank, so the refusal
   applies to everyone including managers.
3. **Five roles are held by nobody** — Fleet Driver, Fleet HR Approver, Fleet Store User,
   Fleet Maintenance User, Fleet Administrator. Those processes have no operator.
4. **No drivers** (1 record) — movement orders and POL abstracts both require one.
5. **Fourteen users have no passwords** and sit on `@gdl.test` placeholder addresses.
6. **SAP integration unscoped.**

Items 1–5 are configuration and master data, not development.
