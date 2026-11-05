# DEF-001 — Before / After Permission Comparison

**Site:** `erpnext16.localhost` (development) · **Date:** 4 November 2026
**Staging:** untouched — verified byte-identical before and after.

Captured from `frappe.get_meta(doctype).permissions` immediately before and after
applying the change and running `bench migrate`.

---

## 1. Headline

| Measure | Before | After | Delta |
|---|---|---|---|
| Permission rows | 28 | 61 | **+33** |
| Fields above level 0 | 3 | 27 | **+24** |
| **Rows removed** | — | — | **0** |
| **Rights revoked** | — | — | **0** |

## 2. The two checks that matter — requirement 5

**Was any permission row removed?**

```
NONE
```

**Was any right revoked from any role?**

```
NONE — nothing was revoked
```

Every row present before is present after, with an identical or larger rights list.
**The change is additive.** Asserted continuously by test RT-10.

---

## 3. Requirement 3 — Fleet Manager unchanged

| Row | Before | After | Same |
|---|---|---|---|
| `Driver|Fleet Manager|0` | export, print, read, report, share | export, print, read, report, share | YES |
| `Movement Order Request|Fleet Manager|0` | print, read, report, share | print, read, report, share | YES |
| `Movement Order Request|Fleet Manager|1` | read | read | YES |
| `Vehicle Log|Fleet Manager|0` | cancel, create, delete, export, print, read, report, share, submit, write | cancel, create, delete, export, print, read, report, share, submit, write | YES |
| `Vehicle|Fleet Manager|0` | create, delete, export, print, read, report, share, write | create, delete, export, print, read, report, share, write | YES |

Every pre-existing Fleet Manager row is untouched. The two new rows
(`Vehicle|Fleet Manager|1`, `Asset Maintenance Log|Fleet Manager|1,2`) are **preservation**
rows — see section 4. Asserted by RT-11.

---

## 4. Requirement 5 — the five preservation rows

These exist only to stop standard roles losing fields that moved above level 0.

| Role · DocType | Level 0 (unchanged) | Added | Expands access? |
|---|---|---|---|
| Fleet Manager · Vehicle | create, delete, export, print, read, report, share, write | L1: export, read, write | No — subset of level 0 |
| Delivery Manager · Vehicle | export, print, read, report, share, write | L1: export, read, write | No — subset of level 0 |
| Delivery User · Vehicle | print, read, report | L1: export, read | **export** |
| Manufacturing User · Asset Maintenance Log | amend, cancel, create, delete, export, print, read, report, share, submit, write | L1: export, read, write | No — subset of level 0 |
| Manufacturing User · Asset Maintenance Log | amend, cancel, create, delete, export, print, read, report, share, submit, write | L2: export, read, write | No — subset of level 0 |

Every preservation row is a **subset** of what that role already holds at level 0.
They keep the fields that moved and gain nothing. Verified by RT-21 and RT-21b.

---

## 5. All 33 rows added

| DocType | Role | Lvl | Rights |
|---|---|---|---|
| Asset Maintenance Log | Fleet Administrator | 0 | amend, cancel, create, export, read, submit, write |
| Asset Maintenance Log | Fleet Administrator | 1 | export, read, write |
| Asset Maintenance Log | Fleet Administrator | 2 | export, read, write |
| Asset Maintenance Log | Fleet Driver | 0 | create, export, read, submit, write |
| Asset Maintenance Log | Fleet Maintenance User | 0 | create, export, read, submit, write |
| Asset Maintenance Log | Fleet Maintenance User | 1 | export, read, write |
| Asset Maintenance Log | Fleet Maintenance User | 2 | export, read |
| Asset Maintenance Log | Fleet Manager *(preserving)* | 0 | export, read |
| Asset Maintenance Log | Fleet Manager *(preserving)* | 1 | export, read |
| Asset Maintenance Log | Fleet Manager *(preserving)* | 2 | export, read |
| Asset Maintenance Log | Manufacturing User *(preserving)* | 1 | export, read, write |
| Asset Maintenance Log | Manufacturing User *(preserving)* | 2 | export, read, write |
| Asset Repair | Fleet Administrator | 0 | cancel, create, export, read, submit, write |
| Asset Repair | Fleet Maintenance User | 0 | create, export, read, submit, write |
| Asset Repair | Fleet Manager *(preserving)* | 0 | export, read |
| Driver | Fleet Administrator | 0 | create, export, read, write |
| Driver | Fleet Approver | 0 | export, read |
| Driver | Fleet Driver | 0 | export, read |
| Driver | Fleet Maintenance User | 0 | export, read |
| Vehicle Log | Fleet Administrator | 0 | amend, cancel, create, export, read, submit, write |
| Vehicle Log | Fleet Approver | 0 | export, read |
| Vehicle Log | Fleet Driver | 0 | create, export, read, submit, write |
| Vehicle | Delivery Manager *(preserving)* | 1 | export, read, write |
| Vehicle | Delivery User *(preserving)* | 1 | export, read |
| Vehicle | Fleet Administrator | 0 | create, export, read, write |
| Vehicle | Fleet Administrator | 1 | export, read, write |
| Vehicle | Fleet Approver | 0 | export, read |
| Vehicle | Fleet Driver | 0 | export, read |
| Vehicle | Fleet HR Approver | 0 | export, read |
| Vehicle | Fleet Maintenance User | 0 | export, read |
| Vehicle | Fleet Manager *(preserving)* | 1 | export, read, write |
| Vehicle | Fleet Store User | 0 | export, read |
| Vehicle | Fleet User | 0 | export, read |

> `export` appears on every new row because `frappe.permissions.add_permission()` grants
> it alongside read by default. It permits exporting data the role can already read, so it
> widens nothing. **`import` is not granted anywhere** — asserted by RT-15.

---

## 6. The 24 field permission levels

| Field | Lvl | Why |
|---|---|---|
| `Asset Maintenance Log.approved_by` | 2 | decision trail — who approved, what it became in the ledger |
| `Asset Maintenance Log.bill_attachment` | 1 | money — supplier, cost, bill, charge-to |
| `Asset Maintenance Log.bill_date` | 1 | money — supplier, cost, bill, charge-to |
| `Asset Maintenance Log.bill_no` | 1 | money — supplier, cost, bill, charge-to |
| `Asset Maintenance Log.bill_status` | 2 | decision trail — who approved, what it became in the ledger |
| `Asset Maintenance Log.cost_center` | 1 | money — supplier, cost, bill, charge-to |
| `Asset Maintenance Log.labour_cost` | 1 | money — supplier, cost, bill, charge-to |
| `Asset Maintenance Log.parts_cost` | 1 | money — supplier, cost, bill, charge-to |
| `Asset Maintenance Log.payment_status` | 2 | decision trail — who approved, what it became in the ledger |
| `Asset Maintenance Log.project` | 1 | money — supplier, cost, bill, charge-to |
| `Asset Maintenance Log.purchase_invoice` | 2 | decision trail — who approved, what it became in the ledger |
| `Asset Maintenance Log.purchase_order` | 2 | decision trail — who approved, what it became in the ledger |
| `Asset Maintenance Log.purchasing_message` | 2 | decision trail — who approved, what it became in the ledger |
| `Asset Maintenance Log.purchasing_status` | 2 | decision trail — who approved, what it became in the ledger |
| `Asset Maintenance Log.rejection_reason` | 2 | decision trail — who approved, what it became in the ledger |
| `Asset Maintenance Log.service_provider` | 1 | money — supplier, cost, bill, charge-to |
| `Asset Maintenance Log.submission_date` | 2 | decision trail — who approved, what it became in the ledger |
| `Asset Maintenance Log.submitted_by` | 2 | decision trail — who approved, what it became in the ledger |
| `Asset Maintenance Log.total_cost` | 1 | money — supplier, cost, bill, charge-to |
| `Fleet Service Item.cost` | 1 | **inside the service-items grid** — the child-table hole |
| `Fleet Service Item.invoice_reference` | 1 | **inside the service-items grid** — the child-table hole |
| `Vehicle.asset` | 1 | commercial — value, asset register, lessor |
| `Vehicle.lessor` | 1 | commercial — value, asset register, lessor |
| `Vehicle.vehicle_value` | 1 | commercial — value, asset register, lessor |

---

## 7. Staging

```
before: 28 permission rows, 3 fields above level 0
after : 28 permission rows, 3 fields above level 0   <- identical
```

No migration was run on staging and no staging record was touched.
