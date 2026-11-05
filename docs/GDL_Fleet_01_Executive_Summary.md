# GDL Fleet Management — Executive Summary

**Audit date:** 4 November 2026
**Audited system:** `gdl-staging.localhost` (GDL staging database, local WSL instance)
**Requirement baseline:** GDL Fleet Management Business Blueprint v1.00, October 2026
**Method:** read-only inspection of source code, DocType definitions, hooks, workflows,
notifications, permissions and the staging database. No records created, modified or
deleted; no migrations run; no configuration changed.

---

## 1. A correction before anything else

The audit brief names the application `gdl_fleet_management`. **That application is not
installed.** It exists on disk but is absent from the installed-apps list.

The live fleet application is **`gdl_fleet_extension` v1.0.0**.

```
Installed on gdl-staging.localhost:
  frappe 16.32.0 · erpnext 16.33.0 · hrms 16.17.0
  gdl 0.0.1 · gdl_custom_app 0.0.1 · gdl_fleet_extension 1.0.0
```

This is consistent with the project instruction not to use `gdl_fleet_management` as the
base. Everything in these five documents refers to `gdl_fleet_extension`. If anyone is
reading or changing `apps/gdl_fleet_management`, they are working on a dormant codebase
that affects nothing.

> **Decision required:** keep the unused `gdl_fleet_management` directory, or remove it.
> Leaving it invites someone to edit the wrong app. Nothing on staging depends on it.

---

## 2. Overall status

The implementation is **substantially complete against the blueprint**. Of the blueprint's
eleven functional components, nine are fully implemented, one is implemented by a different
mechanism than the blueprint names, and one is not built at all.

| Measure | Figure |
|---|---|
| Custom DocTypes | 17 (9 transactional/master, 8 child tables) |
| Standard DocTypes extended | 8, via **101 custom fields** and 16 property setters |
| Workflows | 3, all active |
| Notifications | 12 (10 enabled, 2 deliberately switched off) |
| Script reports | 18 |
| Dashboard | 5 number cards, 5 charts |
| Custom roles | 11 |
| Scheduled jobs | 1 (dormant by default) |
| Client Scripts / Server Scripts in the database | **0** |
| Automated tests | 606, all passing |

The zero on Client and Server Scripts is worth noting: **all logic lives in versioned
files**, none in database records. That means the whole application can be reviewed in
git, deployed by `bench migrate`, and cannot drift between environments. This is the right
way to have built it.

---

## 3. Major findings

### 3.1 The POL calculation reproduces the blueprint exactly

The blueprint's POL Abstract example (page 8, vehicle BG-1-A2397) was run through the
implementation's own calculation functions during this audit. Every figure matches:

| Figure | Blueprint | Computed |
|---|---|---|
| Total fuel supplied | 154.81 L | 154.81 L |
| Total amount (STCBL) | 16,339.43 | 16,339.43 |
| Total KM | 1,079 | 1,079 |
| Total fuel consumed | 134.81 L | 134.81 L |
| Performance per litre | 8.00 | 8.00 |
| Fuel book balance (BOD) | 15,000.00 | 15,000.00 |
| Fuel book balance (STCBL) | 3,660.57 | 3,660.57 |

This is the single strongest piece of evidence in the audit. The consumption formula in
particular — **supplied + previous tank − present tank**, not the reverse — is what makes
1,079 ÷ 134.81 come to exactly the 8.00 the customer's own sheet shows.

### 3.2 Maintenance uses Asset Maintenance, not Maintenance Schedule

The blueprint names "ERPNext Maintenance Schedule" and "ERPNext Log Book". The
implementation uses **Asset Maintenance / Asset Maintenance Task / Asset Maintenance Log /
Asset Repair** instead.

This is a deviation from the blueprint text, and in the auditor's judgement **the correct
one**. ERPNext's Maintenance Schedule belongs to the *Maintenance* module, which exists to
service equipment you have sold to a customer: `Maintenance Visit` makes `customer`
mandatory. Using it would force GDL to create a Customer record and a sales item for every
one of its own vehicles before anyone could record an oil change.

"Log Book" is not an ERPNext DocType at all — it is a generic term in the blueprint.

> **Decision required:** accept Asset Maintenance in writing, so the deviation is a
> recorded decision rather than a finding at acceptance.

### 3.3 The approval chain was deliberately shortened

The blueprint's GAP item 3 specifies a five-stage chain: User → Validate → Reviewer →
MTO/CEO → FAS. That chain is **built but switched off**. The live chain is two steps —
the user applies, the location MTO approves — following the client's instruction of
3 November 2026: *"User will apply, manager will approve, and create Movement order."*

Nothing was deleted. `Movement Order Approval` in GDL Fleet Settings switches between
them, and both sets of workflow states exist so an order mid-approval is never stranded.

### 3.4 Location-wise MTO approval is implemented

Each site has a named MTO who approves that site's requests; the Head Office MTO is the
final authority and can approve anywhere. This was added after the blueprint, on the
client's instruction, and is enforced in code — not merely by role.

### 3.5 SAP integration is not built

The blueprint names it once, under Tyre Mileage: *"Expense tracking via ERPNext Accounts →
SAP integration."* Nothing exists. There is no interface, no mapping and no queue.

> **Scoping required:** direction (push or pull), transport (file, REST, middleware), and
> which documents cross. It cannot be estimated until those are answered.

### 3.6 Staging data is too thin to verify several processes

| DocType | Records | Consequence |
|---|---|---|
| Renewal Register | 0 | Insurance/renewal process unverified on real data |
| Fleet Part Issue | 0 | Spare parts process unverified |
| Vehicle Tyre | 0 | Tyre lifecycle unverified |
| Asset Repair | 0 | Breakdown repair unverified |
| Stock Entry | 0 | Stock integration unverified |
| Asset Maintenance | 0 | Preventive plans unverified |
| Driver | 1 | Minimal |
| Employee | 1 | Minimal |

Fourteen vehicles and one of most things else. The *code paths* are covered by 606 passing
automated tests; what is not evidenced is that **GDL's own data** exercises them.

### 3.7 Configuration is incomplete, and that blocks two whole processes

Seven settings are blank. Two of them stop a business process dead:

| Blank setting | Consequence |
|---|---|
| `Bill Approver Role` | **No service bill can be approved by anyone.** |
| `BOD Supplier`, `STCBL Supplier` | **No fuel claim can be raised.** |
| `Purchasing Company`, `Maintenance Service Item` | Approved bills raise no purchasing document |
| `Notify Role` | Nobody is told when a purchasing document is raised |
| `Default Maintenance Team` | Preventive maintenance plans cannot be created |

None is a defect. All are GDL decisions or master data.

---

## 4. The reminder-schedule discrepancy

The brief correctly flags that the blueprint is internally inconsistent about renewal
reminders. For the record, the blueprint says **four different things**:

| Blueprint location | Value |
|---|---|
| Section heading, *Alerts … Before Annual Renewal Expiry* | 14 days |
| Narrative under that heading | 14 days |
| `Days Before` field in the trigger detail | **30 days** |
| Recommended escalation | 7 days, 3 days, on expiry |
| Reports section, *Insurance/Renewal Due* | 30 / 15 / 7 days |

**Actually configured on staging today:**

| Notification | Days before | Enabled |
|---|---|---|
| Renewal Due (First Reminder) | 14 | yes |
| Renewal Due (Second Reminder) | 3 | yes |
| Renewal Due (Third Reminder) | 7 | **no** |
| Renewal Due (Final Reminder) | 3 | **no** |
| Renewal Expired | 1 day *after* | yes |

So the live schedule is **14 days, 3 days, and the day after expiry**, set on the client's
instruction of 3 November 2026 (*"their requirement is in 14 day … Or 14 and 3 days"*).
All four rungs are configurable; 0 switches one off.

> **Business decision required:** confirm 14 / 3 / expiry is final, or state the intended
> ladder. The blueprint cannot be followed as written because it contradicts itself.

---

## 5. What was changed during the preceding development (context, not audit findings)

This audit was performed immediately after a development round. For transparency, that
round made these changes, all covered by tests:

- Tyre cost and **Tyre Cost Analysis** report; **Parts Consumption** and **Part Replacement
  History** reports; named passengers on the vehicle request.
- Approval chain simplified to two steps; location-wise MTO approval added.
- Renewal ladder set to 14 / 3 / expiry.
- POL running coupon balance (opening → closing carry-forward).
- Dashboard (5 cards, 5 charts).
- Six defects fixed: four reports whose filters never rendered; users unable to submit
  their own requests; MTOs unable to allocate a vehicle; a reminder set to 0 reverting on
  migrate; and the vehicle/driver not carrying to a Movement Order created from the form.

---

## 6. Recommendation

The application is fit for user acceptance testing **today** for vehicle master, drivers,
daily KM, requests, movement orders, POL, mileage and reporting.

Before UAT can cover the whole scope, GDL must supply: drivers and employees, the two fuel
suppliers, the bill approver role, the purchasing company and service item, stock items,
and passwords for the fourteen fleet users.

Before go-live, three business decisions are outstanding: the maintenance approach, the
reminder ladder, and whether the Chairman's Office POL account should be split.

SAP integration should be carved out and scoped separately.

---

*Companion documents: 02 Business Process Guide · 03 Custom vs Default Analysis ·
04 Blueprint Gap Analysis · 05 Testing and Validation.*
