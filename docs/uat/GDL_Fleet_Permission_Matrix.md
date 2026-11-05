# GDL Fleet — Permission Matrix (FINAL)

**Version:** final, incorporating your decisions of 4 November 2026
**Status:** proposal. Nothing applied; staging untouched.

**Legend:** `R` read · `W` write · `C` create · `S` submit · `X` cancel · `A` amend
`—` no permission row · `·` row exists, right not granted

---

## 1. Your four decisions, as built into this matrix

| # | Decision | How it is implemented |
|---|---|---|
| 1 | Fleet Driver may enter and submit service information, but not access or modify financial fields | **Three permission levels** on Asset Maintenance Log. Driver gets level 0 only. |
| 2 | Leave standard Fleet Manager permissions unchanged; do not affect other ERPNext modules | No existing row is altered. Where a permlevel is introduced, **preserving rows** keep Fleet Manager, Delivery Manager, Delivery User and Manufacturing User at exactly their present access. |
| 3 | Fleet User may read Vehicle; keep sensitive fields restricted | Level-0 read granted. `vehicle_value`, `asset` and `lessor` move to level 1. |
| 4 | No permissions for Fleet Validator / Reviewer / Finance User | None granted. |

---

## 2. ⚠ The one thing to understand before approving

**Raising a field's permission level is subtractive by nature.** Once a field sits at
level 1, every role without a level-1 row loses it — including roles belonging to other
ERPNext modules.

| DocType | Roles holding level 0 today that would lose the moved fields |
|---|---|
| Vehicle | Fleet Manager *(standard)*, **Delivery Manager**, **Delivery User** |
| Asset Maintenance Log | **Manufacturing User** |

Decision 2 says not to affect other modules, so the plan **adds a preserving level-1 (and
level-2) row for each of those roles**, mirroring their current rights exactly. Their
effective access is byte-for-byte unchanged.

> This is the only part of the change that touches a standard role's permission set, and it
> does so **solely to prevent a loss of access**. If you would rather not add rows for
> Delivery Manager, Delivery User and Manufacturing User at all, the alternative is to
> leave those fields at level 0 — which means decisions 1 and 3 cannot be delivered. Flagged
> for your explicit confirmation.

---

## 3. Field permission levels — Asset Maintenance Log

### Level 0 — the service record *(what happened to the vehicle)*

`vehicle` · `asset_name` · `item_code` · `location` · `odometer` · `completion_date`
(Service Date) · `maintenance_status` · `maintenance_type` · `task` · `asset_maintenance`
· `driver` · `driver_employee` · `actions_performed` · `has_certificate` ·
`certificate_attachement` · `next_due_date` · `next_due_odometer` · `service_items` *(the
table itself)* · `naming_series`

**Why:** this is the operational record. A driver can say which vehicle went in, at what
odometer, on what date, and what was done — none of it financial.

### Level 1 — money and the bill

| Field | Why it is sensitive |
|---|---|
| `service_provider` | The supplier the money goes to |
| `labour_cost` | Money |
| `parts_cost` | Money |
| `total_cost` *(read-only)* | Money |
| `bill_no` | The commercial document reference |
| `bill_date` | Part of the bill identity |
| `bill_attachment` | The supplier invoice scan itself |
| `cost_center` | Where the cost is charged |
| `project` | Where the cost is charged |
| **`Fleet Service Item.cost`** | ⚠ **Inside the service-items grid** |
| **`Fleet Service Item.invoice_reference`** | ⚠ **Inside the grid** |

> **The two child-table fields are the ones that would have been missed.** Cost and invoice
> reference live *inside* the service-items table. Moving only the parent fields would leave
> a driver with level-0 write able to type costs directly into the grid. Frappe v16 honours
> permlevel on child-table fields (`Document.reset_values_if_no_permlevel_access` runs over
> child rows), so moving these two closes the hole.

### Level 2 — approval and purchasing audit trail

`bill_status` · `submitted_by` · `submission_date` · `approved_by` · `rejection_reason` ·
`purchase_order` · `purchase_invoice` · `purchasing_status` · `purchasing_message` ·
`payment_status`

**Why separate from level 1:** these record *who decided what and what it became in the
ledger*. The maintenance user enters a bill (level 1) but must not be able to mark it
approved or edit the purchase invoice link. All but `rejection_reason` are already
`read_only = 1` and are written by code via `frappe.db.set_value`, which bypasses field
permissions — so level 2 is defence in depth, not the primary control.

---

## 4. Field permission levels — Vehicle

### Level 1 — commercial

| Field | Standard or GDL | Why |
|---|---|---|
| `vehicle_value` | **standard erpnext** | The purchase price. Not an employee's business. |
| `asset` | GDL | Links to the fixed-asset register |
| `lessor` | GDL | Commercial counterparty on a leased vehicle |

### Deliberately left at level 0

`cost_center`, `project` — the MTO and administrator need them routinely, and a cost centre
name is not confidential. `chassis_no`, `engine_no`, `acquisition_date` — identity, not
money. Insurance fields (`policy_no`, `insurance_company`, `start_date`, `end_date`) — an
employee seeing that a vehicle's insurance expires next month is useful, not a leak.

---

## 5. FINAL permission matrix

### Vehicle

| Role | Lvl | R | W | C | S | X | A | D | Note |
|---|---|---|---|---|---|---|---|---|---|
| **Fleet Administrator** | 0 | Y | Y | Y | · | · | · | · | Owns the master |
| **Fleet Administrator** | 1 | Y | Y | · | · | · | · | · | May set value, asset, lessor |
| **Fleet User** | 0 | Y | · | · | · | · | · | · | **Decision 3** |
| **Fleet Approver** | 0 | Y | · | · | · | · | · | · | Allocates vehicles |
| **Fleet Driver** | 0 | Y | · | · | · | · | · | · | Sees the vehicle on their log |
| **Fleet Maintenance User** | 0 | Y | · | · | · | · | · | · | Services it |
| **Fleet Store User** | 0 | Y | · | · | · | · | · | · | Issues parts to it |
| **Fleet HR Approver** | 0 | Y | · | · | · | · | · | · | Reviews fuel claims |
| Fleet Manager *(standard)* | 0 | Y | Y | Y | · | · | · | Y | **UNCHANGED** |
| Fleet Manager *(standard)* | 1 | Y | Y | · | · | · | · | · | **preserving** — mirrors its level-0 R/W |
| Delivery Manager *(standard)* | 1 | Y | Y | · | · | · | · | · | **preserving** |
| Delivery User *(standard)* | 1 | Y | · | · | · | · | · | · | **preserving** |

### Driver

| Role | Lvl | R | W | C |
|---|---|---|---|---|
| **Fleet Administrator** | 0 | Y | Y | Y |
| **Fleet Approver** | 0 | Y | · | · |
| **Fleet Driver** | 0 | Y | · | · |
| **Fleet Maintenance User** | 0 | Y | · | · |
| Fleet Manager *(standard)* | 0 | Y | · | · | **UNCHANGED** |

*No permlevel introduced on Driver, so no preserving rows are needed.*

### Vehicle Log

| Role | Lvl | R | W | C | S | X | A | Note |
|---|---|---|---|---|---|---|---|---|
| **Fleet Driver** | 0 | Y | Y | Y | Y | · | · | Records daily KM. **No cancel** — cancelling rewrites the vehicle odometer |
| **Fleet Administrator** | 0 | Y | Y | Y | Y | Y | Y | Corrects and cancels |
| **Fleet Approver** | 0 | Y | · | · | · | · | · | Checks a vehicle's running |
| Fleet Manager *(standard)* | 0 | Y | Y | Y | Y | Y | · | **UNCHANGED** |

*No permlevel introduced.*

### Asset Maintenance Log

| Role | Lvl | R | W | C | S | X | A | Note |
|---|---|---|---|---|---|---|---|---|
| **Fleet Driver** | 0 | Y | Y | Y | Y | · | · | **Decision 1** — service information only |
| **Fleet Driver** | 1 | — | — | — | — | — | — | **No access to money** |
| **Fleet Driver** | 2 | — | — | — | — | — | — | **No access to the approval trail** |
| **Fleet Maintenance User** | 0 | Y | Y | Y | Y | · | · | Records services |
| **Fleet Maintenance User** | 1 | Y | Y | · | · | · | · | Enters the bill and costs |
| **Fleet Maintenance User** | 2 | Y | · | · | · | · | · | Sees status, cannot set it |
| **Fleet Administrator** | 0 | Y | Y | Y | Y | Y | Y | |
| **Fleet Administrator** | 1 | Y | Y | · | · | · | · | |
| **Fleet Administrator** | 2 | Y | Y | · | · | · | · | Only role that may edit the trail |
| **Fleet Manager** | 0 | Y | · | · | · | · | · | Reporting |
| **Fleet Manager** | 1 | Y | · | · | · | · | · | Reporting on cost |
| **Fleet Manager** | 2 | Y | · | · | · | · | · | Reporting on status |
| Manufacturing User *(standard)* | 0 | Y | Y | Y | Y | Y | Y | **UNCHANGED** |
| Manufacturing User *(standard)* | 1 | Y | Y | · | · | · | · | **preserving** |
| Manufacturing User *(standard)* | 2 | Y | Y | · | · | · | · | **preserving** |

### Asset Repair

| Role | Lvl | R | W | C | S | X |
|---|---|---|---|---|---|---|
| **Fleet Maintenance User** | 0 | Y | Y | Y | Y | · |
| **Fleet Administrator** | 0 | Y | Y | Y | Y | Y |
| **Fleet Manager** | 0 | Y | · | · | · | · |

*Usable only where the vehicle is linked to a fixed Asset — 3 of 14 today.*

### Not granted — decision 4

Fleet Validator, Fleet Reviewer, Fleet Finance User receive **nothing**. The five-stage
chain is switched off.

---

## 6. Does the business process still work?

Decision 1 necessarily changes **who types the bill**. Verified against the actual code.

### Before

1. **Driver** enters service provider, bill no, bill date, parts cost, labour cost, attachment → clicks **Submit Bill**
2. Bill Approver approves → purchasing document raised

### After

| Step | Who | Level |
|---|---|---|
| 1. Record the visit — vehicle, odometer, date, service items done | **Fleet Driver** *or* Fleet Maintenance User | 0 |
| 2. Hand over the paper bill | Driver *(physical, not a system step)* | — |
| 3. Enter supplier, bill no/date, costs, attachment | **Fleet Maintenance User** or Fleet Administrator | 1 |
| 4. Click **Submit Bill** | Same person | needs doc `write`, which they have |
| 5. Approve | Bill Approver Role | 2 written by code |
| 6. Purchase Invoice → payment | Accounts | standard |

**Verified:** `submit_bill()` checks `frappe.has_permission("Asset Maintenance Log", "write")`
— **doctype-level write, not field-level** — and writes via `frappe.db.set_value`, which
bypasses permlevel. So the button works for anyone with level-0 write, and the level-1
restriction only governs who can *type* the figures. The process is intact.

> **This is a real process change and the handbook must be updated.** `GDL_Fleet_Handbook.html`
> Part 7 currently says *"the driver hands in the bill"* and lists the driver entering the
> costs. After this change the driver hands over the paper and the maintenance user records
> it. Arguably better — separation of duties means the person who took the vehicle in is not
> the person who enters what it cost — but it is a change, and GDL should agree to it rather
> than discover it.

---

## 7. Change summary

| Change type | Count |
|---|---|
| Permission rows **added** | **33** |
| Permission rows modified | **0** |
| Permission rows removed | **0** |
| Field permission levels changed | **24** |
| Standard app files edited | **0** |

### Rows by DocType

| DocType | Lvl 0 | Lvl 1 | Lvl 2 | Total | of which preserving |
|---|---|---|---|---|---|
| Vehicle | 7 | 4 | — | 11 | 3 |
| Driver | 4 | — | — | 4 | 0 |
| Vehicle Log | 3 | — | — | 3 | 0 |
| Asset Maintenance Log | 4 | 4 | 4 | 12 | 2 |
| Asset Repair | 3 | — | — | 3 | 0 |
| **Total** | **21** | **8** | **4** | **33** | **5** |

The original 21 level-0 rows are unchanged from the earlier proposal. The 12 additional
rows exist entirely because of the permission levels decisions 1 and 3 require — 7 to grant
GDL roles the new levels, and **5 purely to stop standard roles losing access**.
