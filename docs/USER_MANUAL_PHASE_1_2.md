# GDL Fleet Extension — User Manual & Test Guide

**Covers:** Phase 1 (extension app) and Phase 2 (Vehicle master extension)
**Applies to:** ERPNext 16.30.0 · Frappe 16.29.0 · HRMS 16.15.0 · `gdl_fleet_extension` 0.1.0
**Site:** http://erpnext16.localhost:8000

---

## 1. What this release gives you

The standard ERPNext **Vehicle** record has been extended with GDL's fleet information. You still use the same Vehicle screen you always did — it now has four extra sections on it.

**Nothing standard was removed or replaced.** Vehicle Log, Driver, the Vehicle Expenses report and the Expense Claim link all behave exactly as before.

### What is NOT in this release yet

Do not look for these — they arrive in later phases:

| Not yet available | Phase |
|---|---|
| Vehicle Booking / Request | 4 |
| Vehicle Allocation | 4 |
| Trip fields on Vehicle Log (start/end odometer, purpose, usage type) | 5 |
| Fuel entry and fuel efficiency | 6 |
| Maintenance scheduling and service intervals | 7 |
| Spare parts, tyres, accidents | 8–13 |
| Fleet reports, dashboard, notifications | 14–15 |
| Vehicle as an Accounting Dimension | 3 |

Until Phase 3, the Cost Center / Department / Project fields on the Vehicle are **descriptive only** — they do not yet flow into accounting entries.

---

## 1a. Where to find it in the interface

There is **no standard "Fleet Management" module in ERPNext 16**. Fleet is not an app or a workspace — Vehicle belongs to the Setup module, and Vehicle Log belongs to HR. Three separate things carry the "fleet" name on this site:

| What you see | What it actually is | Use it? |
|---|---|---|
| **GDL Fleet** tile in the launcher | The new `gdl_fleet_extension` workspace | **Yes — this is the one.** Vehicle, Driver, Fleet Vehicle Type, Vehicle Log, Sites, Cost Center, Department, Vehicle Expenses report |
| **Fleet Management** card inside *Frappe HR → Expenses* | Standard ERPNext/HRMS fleet, exactly as shipped | Yes, unchanged — the GDL Fleet workspace simply gathers the same records in one place |
| Grey **Fleet Mana…** tile in the launcher | The **old `gdl_fleet_management` app** — Vehicle Master, Fleet Settings, Driver Authorization | **No. Ignore it.** It is the parallel system being replaced. It stays installed until the cleanup phase. |

The old app's **Vehicle Master** is not the same record as the standard **Vehicle**. Everything in this manual refers to the standard Vehicle, reached from the **GDL Fleet** workspace.

If the GDL Fleet tile does not appear, hard-refresh the browser (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>R</kbd>).

---

## 2. First-time setup

Do these three steps once, in order, before entering any vehicles.

### Step 1 — Assign roles

Ten roles were created. Assign them to users under **Users → select user → Roles**.

| Role | Give it to |
|---|---|
| **Fleet Administrator** | Whoever maintains vehicle master data. Full create/edit/delete on fleet records. |
| **Fleet Manager** | Fleet oversight. Read and report, no master-data edits. |
| **Fleet User** | General staff who will raise requests later. Read-only for now. |
| Fleet Driver | Drivers |
| Fleet Validator | First approval step (Phase 4 onward) |
| Fleet Reviewer | Second approval step |
| Fleet Approver | MTO / CEO level |
| Fleet Maintenance User | Workshop staff (Phase 7) |
| Fleet Store User | Stores / spare parts (Phase 8) |
| Fleet Finance User | FAS / finance approval |
| Fleet HR Approver | Mileage deviation approval (Phase 11) |

Only **Fleet Administrator** and **Fleet Manager** are needed for this release. Do not grant System Manager.

### Step 2 — Create your Vehicle Types

**This is required.** Vehicle Type is a mandatory field, so no vehicle can be saved until at least one type exists.

Go to **GDL Fleet → Fleet Vehicle Type → Add** and create one record per type of vehicle GDL runs. For example:

| Vehicle Type | Default Seating Capacity | Default Fuel Type | Requires Driver |
|---|---|---|---|
| Car | 5 | Petrol | ✔ |
| 4WD Pickup | 5 | Diesel | ✔ |
| Bus | 30 | Diesel | ✔ |
| Truck | 3 | Diesel | ✔ |
| Tractor | 1 | Diesel | ✔ |

Use GDL's own list — the above is only an example. Types can be added at any time. Tick **Disabled** to retire a type without deleting it.

### Step 3 — Check your Sites

The site hierarchy has already been created as standard ERPNext **Location** records. Open **GDL Fleet → Sites** (or the Location tree) and confirm:

```
GDL                    (group)
├── Head Office        (site)
└── Farms              (group)
    ├── Jamjee Farm
    ├── Dochula Farm
    ├── Dagapela Farm
    ├── Gedu
    ├── Samcholing
    └── Jigmeling
```

**Vehicles must be assigned to a site, never to a group.** `GDL` and `Farms` are grouping nodes for reporting only — the system will refuse them.

Cost Centers are **not** created by this app. Use GDL's existing Cost Centers.

---

## 3. The Vehicle screen, section by section

Open **Vehicle → Add Vehicle**. Sections appear in this order.

### 3.1 Top of the form (standard, unchanged)

| Field | Notes |
|---|---|
| **Registration Number** | Formerly labelled "License Plate". This is the vehicle's registration number **and its document name**. Required and unique. |
| **Make** | Required. e.g. Toyota |
| **Model** | Required. e.g. Hilux |
| **Company** | Your GDL company |

### 3.2 GDL Fleet Identification *(new)*

| Field | Required | Notes |
|---|---|---|
| **Vehicle ID** | Auto | GDL's internal fleet number. **Leave blank and it is generated automatically** as `GDL-VEH-00001`, `GDL-VEH-00002`, … You may type your own instead. **Once saved it cannot be changed.** Must be unique. |
| **Vehicle Type** | **Yes** | From the list you created in Step 2. |
| **Vehicle Status** | Read-only | Available / Reserved / In Use / Under Maintenance / Unavailable / Sold-Disposed. Defaults to **Available**. From Phase 4 this is maintained automatically by bookings, allocations and open repairs — do not try to edit it. |
| **Ownership Type** | **Yes** | GDL Owned / Leased / Rented / Other. Defaults to **GDL Owned**. |
| **Lessor / Rental Supplier** | Conditional | Only appears when Ownership Type is Leased or Rented, and is then mandatory. |
| **Asset** | No | Links this vehicle to its ERPNext Asset record. This is what enables standard Asset Maintenance, Asset Repair and depreciation from Phase 7. One Asset may belong to one Vehicle only, and the Asset's company must match. Leave blank until Finance has created the Asset records. |
| **Engine No** | No | |
| **Manufacturing Year** | No | Must be between 1950 and next year. |

### 3.3 Site and Accounting Dimensions *(new)*

| Field | Notes |
|---|---|
| **Site** | The GDL Location this vehicle belongs to. Must be a specific site, not a group. |
| **Department** | Standard ERPNext Department |
| **Cost Center** | Use GDL's existing Cost Centers. No new ones were created. |
| **Project** | Standard ERPNext Project |

### 3.4 Details (standard, with two new fields)

| Field | Notes |
|---|---|
| **Current Odometer (KM)** | Standard `last_odometer`, relabelled. Required. **It is now editable** — previously ERPNext locked it after creation. From Phase 5 it is maintained automatically by Vehicle Log. |
| **Opening Odometer** *(new)* | The reading when the vehicle entered GDL's records. Cannot be higher than Current Odometer. |
| **Expected Monthly KM** *(new)* | Used from Phase 11 for mileage-deviation analysis. Leave blank to fall back to the vehicle-type norm. |
| Acquisition Date, Chassis No, Vehicle Value | Standard, unchanged. **Chassis Number uses the standard field** — no duplicate was added. |
| **Responsible Employee** | Standard `employee`, relabelled. |
| **Assigned Driver** *(new)* | Links to the standard Driver record. |
| ~~Location~~ | Hidden and marked deprecated. **Use Site instead.** |

### 3.5 Insurance Details (standard, relabelled)

No new insurance fields were created — the standard ones are reused.

| Field | Notes |
|---|---|
| **Insurance Company** | Standard free-text field |
| **Policy No** | Standard |
| **Insurance Start Date** | Standard `start_date`, relabelled |
| **Insurance Expiry** | Standard `end_date`, relabelled. Must be after the start date. |

### 3.6 Registration and Compliance *(new)*

| Field | Notes |
|---|---|
| **Registration Expiry** | Drives the expiry alert from Phase 15 |
| **Registration Renewal Date** | When it was or will be renewed |
| **Inspection Expiry** | |
| **Insurance Renewal Date** | |

### 3.7 Vehicle Documents *(new, collapsible)*

A table for the vehicle's paperwork. One row per document.

| Column | Notes |
|---|---|
| **Document Type** | Registration Certificate / Insurance / Inspection / Fitness / Pollution / Permit / Lease Agreement / Other |
| **Document Number** | |
| **Issue Date**, **Expiry Date**, **Renewal Date** | Expiry cannot be before Issue |
| **Status** | Read-only, set automatically on save: **Expired**, **Expiring Soon** (within 30 days), **Valid**, or **Not Applicable** (no expiry date) |
| **Attachment** | Scan of the document |
| **Remarks** | |

### 3.8 Additional Details (standard)

Fuel Type — **now also offers Hybrid, CNG, LPG and Other** in addition to the standard Petrol, Diesel, Natural Gas, Electric. Fuel UOM, Last Carbon Check, **Color** (standard field, no duplicate added), Wheels, Doors are unchanged.

---

## 4. Rules the system enforces

If you see one of these messages, this is why.

| Message | Cause | Fix |
|---|---|---|
| *Vehicle ID `X` is already used by Vehicle `Y`* | Two vehicles with the same Vehicle ID | Use a different ID, or leave it blank to auto-generate |
| *Vehicle ID cannot be changed once set (current value: X)* | You edited the Vehicle ID of a saved vehicle | The ID is permanent by design. Correct it only via a data fix by an administrator. |
| *Manufacturing Year X is not valid* | Year outside 1950 – next year | Enter a real year |
| *Site X is a group Location* | You chose `GDL` or `Farms` | Choose a specific site |
| *Asset X is already linked to Vehicle Y* | Two vehicles share one Asset | One Asset, one Vehicle |
| *Asset X belongs to Company A but this Vehicle belongs to B* | Company mismatch | Correct the company on one of them |
| *Opening Odometer (X) cannot be greater than Current Odometer (Y)* | Opening reading above current | Correct one of the two |
| *Row #N: Expiry Date cannot be before Issue Date* | Bad dates in the Documents table | Correct the dates |
| *Insurance Start date should be less than Insurance End date* | **Standard ERPNext rule**, still active | Correct the insurance period |
| *Current Odometer Value should be greater than Last Odometer Value* | **Standard ERPNext rule** on Vehicle Log | Enter a higher reading |

---

## 5. How to test

### 5.1 Automated tests

Twenty-five tests ship with the app. Run them from the bench.

Enable testing on the site once:

```bash
cd ~/erpnext-v16/frappe-bench/sites && ../env/bin/python -m frappe.utils.bench_helper frappe --site erpnext16.localhost set-config allow_tests true
```

Run the Vehicle extension tests (18 tests):

```bash
cd ~/erpnext-v16/frappe-bench/sites && ../env/bin/python -m frappe.utils.bench_helper frappe --site erpnext16.localhost run-tests --module gdl_fleet_extension.tests.test_vehicle_extension
```

Run the standard-fleet regression tests (7 tests) — these prove ERPNext's own fleet behaviour is untouched:

```bash
cd ~/erpnext-v16/frappe-bench/sites && ../env/bin/python -m frappe.utils.bench_helper frappe --site erpnext16.localhost run-tests --module gdl_fleet_extension.tests.test_standard_fleet_regression
```

Expected: `OK` with 18 and 7 tests respectively. Any `FAILED` line is a genuine problem — send the output.

> **After every test run, do the cleanup in §5.4.** The frappe test runner commits some of ERPNext's own sample `Location` records into the site, and they will otherwise show up in the Site dropdown.

### 5.2 What the automated tests cover

**Vehicle extension (18):** Vehicle ID auto-generation · explicit ID kept · uniqueness · immutability · backfill for pre-existing vehicles · leaf site accepted · group site rejected · the 9-record site tree · manufacturing year range · opening odometer rule · vehicle type mandatory · extended fuel types · document expiry-before-issue rejected · document status computation (all four states) · no duplicate fields created · standard vehicle still creatable · standard insurance validation still fires.

**Standard fleet regression (7):** Vehicle Log submit rolls the odometer forward · Vehicle Log rejects a lower reading · refuelling and service child table intact · Expense Claim creation from a Vehicle Log · the standard Vehicle Expenses report still runs and totals correctly · Vehicle naming unchanged · Vehicle Log standard fields intact.

### 5.3 Manual UAT script

Log in at **http://erpnext16.localhost:8000**. Work through in order.

| # | Test | Steps | Expected result | P/F |
|---|---|---|---|---|
| 0 | Workspace visible | Launcher → **GDL Fleet** tile | Opens with Vehicle Master, Operations, Setup and Reports cards | |
| 1 | Roles exist | Role list → search "Fleet" | 11 roles listed (10 new + standard Fleet Manager) | |
| 2 | Site tree | Location list → tree view | GDL › Head Office, Farms › 6 farms | |
| 3 | Create a Vehicle Type | Fleet Vehicle Type → new → "4WD Pickup", capacity 5, Diesel | Saves | |
| 4 | Duplicate type rejected | Create "4WD Pickup" again | Duplicate error | |
| 5 | Vehicle Type is mandatory | Vehicle → new → fill plate/make/model/odometer/fuel/UOM, leave Vehicle Type blank → Save | Mandatory-field error on Vehicle Type | |
| 6 | Create a vehicle | Fill everything including Vehicle Type, leave Vehicle ID blank → Save | Saves. **Vehicle ID auto-fills as `GDL-VEH-000xx`** | |
| 7 | Document name | Look at the URL / title | Named by the Registration Number, not the Vehicle ID | |
| 8 | Vehicle ID is permanent | Edit the Vehicle ID on the saved vehicle → Save | *Vehicle ID cannot be changed once set* | |
| 9 | Vehicle ID unique | New vehicle, type the same Vehicle ID → Save | *Vehicle ID … is already used by Vehicle …* | |
| 10 | Group site rejected | Set Site = `Farms` → Save | *Site Farms is a group Location* | |
| 11 | Leaf site accepted | Set Site = `Jamjee Farm` → Save | Saves | |
| 12 | Bad manufacturing year | Set Manufacturing Year = 1800 → Save | Validation error | |
| 13 | Opening odometer rule | Current Odometer 1000, Opening Odometer 5000 → Save | *Opening Odometer … cannot be greater than …* | |
| 14 | Odometer now editable | Change Current Odometer on a saved vehicle → Save | Saves (ERPNext used to block this) | |
| 15 | Lessor conditional | Set Ownership Type = Rented | Lessor field appears and becomes mandatory | |
| 16 | New fuel types | Open the Fuel Type dropdown | Petrol, Diesel, Natural Gas, Electric, **Hybrid, CNG, LPG, Other** | |
| 17 | Document status | Add 4 Documents rows: one expired, one expiring within 30 days, one far future, one with no expiry date → Save | Status reads Expired / Expiring Soon / Valid / Not Applicable | |
| 18 | Document date rule | Set a row's Expiry before its Issue date → Save | *Row #N: Expiry Date cannot be before Issue Date* | |
| 19 | Old Location field hidden | Look for the old "Location" field | Not visible (replaced by Site) | |
| 20 | **Standard Vehicle Log still works** | Vehicle Log → new → pick the vehicle, employee, date, a higher odometer → Submit | Submits. The Vehicle's Current Odometer updates to match | |
| 21 | **Standard odometer guard** | New Vehicle Log with a *lower* odometer | *Current Odometer Value should be greater than Last Odometer Value* | |
| 22 | **Standard Expense Claim link** | On a submitted Vehicle Log with fuel qty and price → Create → Expense Claim | A draft Expense Claim opens with the correct amount | |
| 23 | **Standard report** | Vehicle Expenses report, set the date range | Runs and shows the fuel expense | |
| 24 | Permissions | Log in as a Fleet User | Can view vehicles, cannot create or delete | |
| 25 | Existing vehicle | Open vehicle `TN32` | Has Vehicle ID `GDL-VEH-00001`. **Set its Vehicle Type before saving** — see §6. | |

Tests 20–23 are the important ones: they confirm standard ERPNext fleet still works.

### 5.4 Cleanup after an automated test run

```bash
cd ~/erpnext-v16/frappe-bench/sites && for L in "Block 1" "Field 1" "Division 1" "Basil Farm" "Test Location Area" "Test Location" "Test Location 2"; do ../env/bin/python -m frappe.utils.bench_helper frappe --site erpnext16.localhost execute frappe.client.delete --kwargs "{'doctype':'Location','name':'$L'}"; done
```

Then confirm the Location list contains only the 9 GDL records.

### 5.5 Reinstating a clean state

A backup taken before any of this work exists at
`sites/erpnext16.localhost/private/backups/20260922_190837-*`.

---

## 6. Known items and open questions

| Item | Status |
|---|---|
| **Existing vehicle `TN32` has no Vehicle Type** | Vehicle Type is mandatory, so this record cannot be saved until a type is chosen. Set it once your types exist. |
| **`Asset` is optional even though all GDL vehicles are company-owned** | Deliberate: there are no Asset records on this site yet, and making it mandatory would block vehicle creation. It will be enforced in Phase 7 once Finance has loaded the Assets. Confirm if you want it mandatory sooner. |
| **Cost Center / Department / Project on the Vehicle are descriptive only** | They begin flowing into accounting in Phase 3, when Vehicle becomes an Accounting Dimension. |
| **Vehicle Status is not yet automatic** | It stays on its default until Phase 4 introduces bookings and allocations. |
| **GDL's real Vehicle Type list is needed** | Send the list and it can be seeded for you. |
| **Automated test runs leak ERPNext sample Locations** | Known behaviour of the frappe test runner, not a bug in this app. Use the §5.4 cleanup. |

---

## 7. Where things live

| What | Where |
|---|---|
| The app | `apps/gdl_fleet_extension` |
| Vehicle fields & property setters | `gdl_fleet_extension/setup/vehicle_fields.py` |
| Vehicle validation rules | `gdl_fleet_extension/overrides/vehicle.py` |
| Site hierarchy | `gdl_fleet_extension/setup/sites.py` |
| Roles | `gdl_fleet_extension/setup/roles.py` |
| New DocTypes | `gdl_fleet_extension/gdl_fleet/doctype/` |
| Tests | `gdl_fleet_extension/tests/` |

Everything the app changes on a standard DocType is a **Custom Field** or a **Property Setter** tagged `module = GDL Fleet`. No ERPNext, HRMS or Frappe file was modified, and `gdl_fleet_management` was not touched.
