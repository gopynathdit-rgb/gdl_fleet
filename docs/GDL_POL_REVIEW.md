# POL Implementation Review — pre-coding (section 22 deliverable)

Sources inspected: `POL.xlsx` (sheets `BG-1-A2397`, `BG-1-A3812`, `Sheet2` empty),
`Fleet Mgmt.docx` §4.10, and the live site `erpnext16.localhost`.

No code has been changed. This document is for approval before implementation.

---

## 0. BLOCKER — the brief and the workbook disagree on fuel consumed

The brief (§5) states:

    Total Fuel Consumed = Total Fuel Supplied + Present Tank Balance - Previous Tank Balance

The workbook's actual cell formula is the mirror image of that:

| Sheet | Cell | Formula in the file | Evaluates to |
|---|---|---|---|
| BG-1-A2397 | `D30` | `=(E9+D22)-D24` | `(154.81 + 40) - 60` = **134.81** |
| BG-1-A3812 | `D32` | `=(E11+D24)-D26` | `(252 + 30) - 35` = **247** |

i.e. **supplied + previous - present**, not supplied + present - previous.
This is also the physically correct stock equation: consumed = supplied +
opening stock - closing stock.

The brief's figures (174.81 and 257) do not appear anywhere in the workbook.

### The workbook is internally self-consistent, and the brief is not

`BG-1-A3812!D34` holds the **literal number 9** — it is not a formula, so it is
not display rounding.

    2223 / 247 = 9.000000   exactly        <- workbook's own formula
    2223 / 257 = 8.649805...               <- the brief's formula

The hand-typed 9 reproduces exactly under the workbook's formula. The
probability of that landing on a whole number by chance is low enough to treat
it as confirmation.

Cross-check on the other sheet, where performance *is* a live formula
(`D32 = D20/D30`), cached result `8.003857280617165`:

    1079 / 134.81 = 8.003857280617164...   <- workbook, matches the cached value
    1079 / 174.81 = 6.172415...            <- the brief claims 6.1724

**Recommendation: implement the workbook formula.** The brief instructs that
`POL.xlsx` is the source of truth and that its logic must not be replaced, so
where the two conflict the workbook wins. Test cases 1 and 2 in §19 of the
brief need their expected values corrected to 134.81 / 8.0039 and 247 / 9.0000.

**This needs GDL's explicit sign-off before coding** — it is the single
calculation the whole abstract turns on.

---

## 0b. Second discrepancy — Test Case 1's STCBL total depends on a truncation

On `BG-1-A2397` the Amount (STCBL) cells are **typed constants**, not formulas.
On `BG-1-A3812` they **are** formulas (`=F6*E6`).

Row 1 of sheet 1: `41.81 x 105.55 = 4413.0455`, but the workbook holds
`4413.04` — truncated, not rounded (rounding gives `4413.05`).

| | STCBL amount | Book balance (20,000 - amount) |
|---|---|---|
| Workbook's typed values | **16,339.43** | **3,660.57** |
| Computed, round-half-up per row | 16,339.44 | 3,660.56 |

So Test Case 1's expected `16339.43` / `3660.57` is only reproducible if the
per-row amount is allowed to carry the operator's entered value rather than a
recomputed one.

**Proposal:** `amount` is computed as `litres x rate` on entry but remains
editable, exactly mirroring the customer's own two-sheet practice (one typed,
one formula). Tests then seed sheet 1's typed amounts and compute sheet 2's.
This satisfies both test cases without faking either.

---

## A. Exact current POL implementation status

**There is none.** Verified on the live site:

- POL DocTypes: none (the only `%pol%` matches are HR's Leave Policy family).
- POL reports: none.
- `GDL Fleet Settings` has no POL fields.
- No POL workflow, no POL role.

What exists today that touches fuel:

| Object | State |
|---|---|
| `Fleet Fuel Entry` | Submittable, 9 records on site. Per-fill transaction: vehicle, driver, date, source_type, fuel_type, qty, uom, rate, amount, is_tank_full, odometer, previous_odometer, distance_since_last_fill, supplier, warehouse, invoice_reference, site/department/cost_center/project, accounting_voucher link. |
| `Vehicle Log` | 32 records. Opening/Closing odometer, distance travelled, movement order, place to travel. |
| `Fuel Consumption and Performance` report | Reads `Fleet Fuel Entry`. Uses the **full-to-full** method (km/L only between two full-tank fills). This is a different, stricter method than POL's. |

Nothing POL-shaped has to be removed. The work is purely additive.

---

## B. Exact gaps against POL.xlsx

| Workbook element | Today | Gap |
|---|---|---|
| Abstract header (vehicle, abstract date, period) | — | new |
| Supply memo no., date, litres, rate | `Fleet Fuel Entry` has equivalents | needs to appear as POL entry lines |
| `Amount (BOD)` | — | new, **and no rule supplied** (see D) |
| `Amount (STCBL)` | `Fleet Fuel Entry.amount` | new on abstract |
| Total fuel recoupment BOD / STCBL | — | new |
| Opening KM / Closing KM / Total KM | Vehicle Log has per-trip equivalents | new at abstract level |
| Previous / Present tank balance | — | new |
| Fuel book balance BOD / STCBL | — | new |
| Total fuel consumed | — | new (formula above) |
| Performance per litre | report computes it full-to-full | **method differs** — must change to POL method |
| Submitted By / Approved By | — | new, via workflow |
| Printable abstract | — | new Print Format |
| POL Summary Register | — | new report |
| POL Supplier / Book Balance | — | new report |

### What the workbook answers that §4.10 of the Word document did not

Column F of sheet `BG-1-A2397` carries GDL's own implementation notes. These
resolve three previously open questions:

| Field | GDL's note | Reading |
|---|---|---|
| Total fuel recoupment (BOD) | `Maintain` | standing balance held on the record |
| Total fuel recoupment (STCBL) | `Maintain` | same |
| Opening Km | `Pull from previous refuleing field` | **carried forward automatically** |
| Closing Km | `manual` | operator enters |
| Previous tank balance | `manual (Assump)` | **manual, and GDL flags it as an assumption** |
| Present tank balance | `manual` | operator enters |

So §7 of the brief resolves to: carry Opening KM forward automatically;
leave Previous tank balance manual with carry-forward offered as a default
the operator can override.

### Reporting period is NOT a calendar month

The entry dates span month boundaries on both sheets:

- `BG-1-A2397`: 07.08.26, 17.08.26, **24.09.26** — Aug into Sep
- `BG-1-A3812`: 29.06.26 ... 28.08.26 — Jun into Aug

Both carry the same abstract header date `24/08/2026`. The period is therefore
an explicit From/To on the abstract, not a derived month. (Note sheet 1 has an
entry dated *after* its own abstract date — worth raising with GDL as a data
query, not a system rule.)

### "HRS Liters" / "km/hr"

In both samples column E holds plain litres (41.81, 58, 55 / 30, 63, ...), and
Opening/Closing KM hold odometer readings in the tens of thousands with the
unit label `km/hr`. The evidence is that this is one template serving both
km-metered and hour-metered assets, and that **both sample vehicles are
km-metered**. Proposal: carry a `distance_basis` of `KM` or `Hours` on the
abstract, defaulting to KM, so an hour-metered asset is supported later without
reinterpreting the KM fields. Terminology preserved as GDL writes it.

Currency confirms the context: company `GDL` is Bhutan / **BTN**, matching the
workbook's `Nu.` and `Nu/chh.` units.

---

## C. Proposed POL data model

Two new DocTypes. No existing DocType is modified destructively.

### `POL Abstract` (submittable, workflow-controlled)

```
naming_series   POL-.YYYY.-.#####
vehicle         Link Vehicle            reqd
abstract_date   Date                    reqd      (workbook B2/C2)
period_from     Date                    reqd      (explicit - not derived)
period_to       Date                    reqd
distance_basis  Select KM / Hours       default KM
driver          Link Driver                       (defaults from Driver Assignment)
site / department / cost_center / project         (accounting dimensions, as elsewhere)

entries         Table POL Entry

-- fuel totals (computed, read-only) --
total_litres        Float      = SUM(entries.litres)
total_amount_bod    Currency   = SUM(entries.amount_bod)
total_amount_stcbl  Currency   = SUM(entries.amount_stcbl)

-- recoupment (input, "Maintain") --
recoupment_bod      Currency
recoupment_stcbl    Currency

-- odometer --
opening_km      Float   (carried forward, overridable)
closing_km      Float   reqd
total_km        Float   = closing_km - opening_km            read-only

-- tank --
previous_tank_balance Float   (carried forward, overridable)
present_tank_balance  Float   reqd

-- derived --
fuel_book_balance_bod   Currency = recoupment_bod   - total_amount_bod
fuel_book_balance_stcbl Currency = recoupment_stcbl - total_amount_stcbl
total_fuel_consumed     Float    = (total_litres + previous_tank_balance) - present_tank_balance
performance_per_litre   Float    = total_km / total_fuel_consumed   (null when consumed <= 0)

-- accountability --
submitted_by    Link User/Employee   (set on submit)
approved_by     Link User/Employee   (set by workflow)
```

### `POL Entry` (child table)

```
supply_memo_no  Data     reqd
date            Date     reqd
litres          Float    reqd           (workbook's "HRS Liters")
rate            Currency reqd
amount_bod      Currency                -- NOT auto-derived; see D
amount_stcbl    Currency                -- defaults to litres x rate, editable
fuel_entry      Link Fleet Fuel Entry   -- optional provenance link (see G)
```

### Calculation service layer

All arithmetic lives in `gdl_fleet_extension/utils/pol.py` as pure functions
over `Decimal`, with no Frappe document dependency, so it is unit-testable on
its own:

```python
def total_litres(entries) -> Decimal
def total_amount(entries, column) -> Decimal
def total_km(opening, closing) -> Decimal
def total_fuel_consumed(total_litres, previous_tank, present_tank) -> Decimal
def performance_per_litre(total_km, total_consumed) -> Decimal | None
def fuel_book_balance(recoupment, amount) -> Decimal
```

Monetary values use `Decimal` throughout and are quantised once at the
boundary using ERPNext's currency precision (site is set to 2).

---

## D. Calculation formulas (exactly as the workbook demonstrates)

```
Total Fuel Supplied     = SUM(entry.litres)
Amount (STCBL)          = litres x rate          (default; operator-overridable)
Amount (BOD)            = NOT DERIVED - see below
Total KM                = Closing KM - Opening KM
Total Fuel Consumed     = (Total Fuel Supplied + Previous Tank Balance) - Present Tank Balance
Performance per Litre   = Total KM / Total Fuel Consumed
Fuel Book Balance BOD   = Total Fuel Recoupment (BOD)   - Amount (BOD)
Fuel Book Balance STCBL = Total Fuel Recoupment (STCBL) - Amount (STCBL)
```

**Amount (BOD) is left as a controlled manual field.** Column G is empty on
both sheets, and neither sheet totals it — the BOD book-balance formulas
reference an empty cell (`=D12-G9`, `=D14-G11`), which is why BOD book balance
evaluates to the bare recoupment (15,000 and 0). No BOD rule can be inferred,
and none will be invented. Flagged as a business clarification.

### Validations

Closing KM >= Opening KM; previous and present tank balances >= 0; litres > 0;
rate >= 0; recoupment >= 0; total fuel consumed may not be negative;
performance suppressed (left blank, never zero or faked) when consumed <= 0;
supply memo uniqueness per vehicle — see the open question below.

---

## E. Existing objects to reuse (not rebuild)

`Vehicle`, `Driver`, `Employee`, `Supplier`, `Location` (Site), `Department`,
`Cost Center`, `Project`, `Company`, `UOM`, `Currency` (BTN), the Frappe
Workflow engine, the existing Notification pattern, and the existing roles —
**`Fleet Driver`** submits and **`Fleet HR Approver`** approves, which matches
the workbook's own signatures (Thinley Dorji / Driver; Mr. Sonam Tobgye /
Head-HR). No new role is required.

The Vehicle accounting dimension already propagates to 57 DocTypes, so POL
inherits dimension reporting without extra work.

---

## F. New objects required

| Object | Type |
|---|---|
| `POL Abstract` | DocType, submittable |
| `POL Entry` | child DocType |
| `GDL POL Approval` | Workflow — Draft -> Pending Approval -> Approved / Rejected |
| `POL Abstract` print format | matches the workbook layout, for printing/export |
| `POL Summary Register` | Script Report — filters: Vehicle, From, To, Driver, Status, Site |
| `POL Supplier / Book Balance` | Script Report — vehicle, supplier, period, memo, litres, rate, amount, BOD/STCBL recoupment and book balance |
| `utils/pol.py` | calculation service layer |
| `tests/test_pol.py` | both workbook vehicles as fixtures |
| Settings fields | `pol_performance_precision`, `pol_carry_forward_opening_km`, `pol_carry_forward_tank_balance`, `pol_enforce_unique_supply_memo` |

Every threshold and toggle above is configuration, not code, per the standing
constraint.

---

## G. Migration and data impact plan

**Nothing is deleted and nothing existing changes shape.** The 9 `Fleet Fuel
Entry` records, 32 `Vehicle Log` records and all masters are untouched.

### `Fleet Fuel Entry` — recommendation: **option B, consume it**

Rather than replace it. Reasons: it already carries supplier, warehouse,
accounting voucher and tank-full flags that POL has no column for; it is the
link into standard ERPNext accounting; and it holds live data. The POL Entry
row carries an optional `fuel_entry` link, so an abstract can either be keyed
from existing fuel entries or typed directly where no entry exists.

**Double counting is avoided structurally:** POL Abstract posts no accounting
entries of its own. It is an abstract *over* fuel transactions, not a second
fuel transaction. Money reaches the ledger only once, through `Fleet Fuel
Entry`'s existing voucher link. Where a POL Entry links a `Fleet Fuel Entry`,
the link is validated as one-to-one so the same fill cannot appear on two
abstracts.

This remains GDL's decision to confirm (the brief's §18 open question).

### `Fuel Consumption and Performance` report

Must change method (brief §17). Today it reports km/L full-to-full from
`Fleet Fuel Entry`. It will be re-pointed at `POL Abstract` and report
Total KM, Total Fuel Supplied, Previous Tank, Present Tank, Total Fuel
Consumed and Performance KM/L. The full-to-full figure is the stricter
engineering measure and will be retained as an additional column where the
underlying fuel entries support it, rather than discarded.

Its `ref_doctype` changes from `Fleet Fuel Entry` to `POL Abstract` — a patch,
same pattern as the report renames already shipped.

### Patch plan

One `post_model_sync` patch creating the POL workflow and seeding the new
settings fields. No data migration is needed because no POL data exists.

### Test impact

Current suite: **286 tests, all passing.** Expected after POL: 286 unchanged
plus roughly 35-40 new, including both workbook vehicles reproduced to the
decimal. The `Fuel Consumption and Performance` assertions in `test_reports.py`
will change with the report's method.

---

## Open questions for GDL (blocking)

1. **Fuel consumed formula** — confirm the workbook's
   `(supplied + previous) - present`, and that §19's expected values
   (174.81 / 257) in the brief are corrected to 134.81 / 247.
2. **Amount (BOD)** — what is the rule? Left manual until answered.
3. **Fleet Fuel Entry** — replace, or consume (recommended)?
4. **Supply memo uniqueness** — unique per vehicle, per period, or globally?
   The samples show no overlap but also no obvious scheme (25743, 39883, 64535
   / 13622, 2296, 19350, 13277, 36498).
5. **Hour-metered assets** — do any exist, or is KM the only basis?
6. **Previous tank balance** — carry forward from the prior abstract's present
   balance by default (with override), or always manual as GDL's own note
   `manual (Assump)` suggests?
