# DEF-001 — Regression Test Plan

**To run only after the fix is approved and applied.** Nothing here has been executed.

**Governing rule:** every permission assertion evaluates a **named role**, never
Administrator. Administrator bypasses every check — testing with it is what let DEF-001
survive 606 tests and three rounds of manual testing.

---

## 1. Two layers, and why both are needed

| Layer | Method | Proves | Needs |
|---|---|---|---|
| **A — automated** | `frappe.set_user()` in the existing test suite | The permission *rule* is right | Nothing. Runs in CI. |
| **B — manual UI** | A real browser, logged in as a real account | The user can actually *do the job* | Passwords + a browser *(both currently blocked)* |

Layer A can run the day the fix lands. Layer B is the UAT evidence and stays blocked until
the Master Plan blockers clear.

> `frappe.set_user()` does **not** bypass permissions — it evaluates them as that user. It
> is how frappe's own suite tests permissions. What it does not prove is that login works
> or that the form renders, which is Layer B's job.

---

## 2. Layer A — automated regression tests

Proposed file: `gdl_fleet_extension/tests/test_fleet_permissions.py`, following the
existing suite's conventions.

### Fixture approach

The fix grants permissions to **roles**, and no user currently holds five of them. The
tests therefore create **throwaway users inside the test transaction**, each holding
exactly one role — which is also the only way to prove a role in isolation.

```python
def user_with_only(role):
    """A disposable user holding exactly one fleet role.

    One role only: a user holding two cannot tell you which one granted access,
    and that ambiguity is precisely how DEF-001 hid - every tester also held
    Fleet Manager.
    """
    email = f"uat.{role.lower().replace(' ', '.')}@gdl.test"
    if not frappe.db.exists("User", email):
        user = frappe.get_doc({
            "doctype": "User", "email": email, "first_name": role,
            "user_type": "System User", "send_welcome_email": 0,
        })
        user.flags.ignore_permissions = True
        user.insert()
        user.add_roles(role)          # exactly one
    return email
```

These users exist only inside the test transaction and are rolled back. **No password is
set**, because `set_user()` does not need one.

### The nine required cases, plus the ones that keep us honest

| # | Test | Role | Asserts | Brief ref |
|---|---|---|---|---|
| RT-01 | Fleet Administrator can create a Vehicle | Fleet Administrator | `has_permission("Vehicle","create")` is True **and** an insert succeeds | §6.1 |
| RT-02 | Fleet Administrator can create a Driver | Fleet Administrator | create + insert succeed | §6.2 |
| RT-03 | Fleet Driver can create a Vehicle Log | Fleet Driver | create, write, submit; a log inserts and submits | §6.3 |
| RT-04 | Fleet Maintenance User can record maintenance | Fleet Maintenance User | create + submit on Asset Maintenance Log | §6.4 |
| RT-05 | Fleet Manager can read every fleet report | Fleet Manager | all 18 reports execute without permission error | §6.5 |
| RT-06 🚫 | Fleet User cannot approve their own request | Fleet User | `apply_workflow(..., "Accept")` raises | §6.6 |
| RT-07 🚫 | Wrong-site MTO cannot approve | Fleet Approver | `validate_approver()` raises, naming the right MTO | §6.7 |
| RT-08 🚫 | Fleet Driver cannot approve their own POL | Fleet Driver | `apply_workflow(..., "Approve")` raises | §6.8 |
| RT-09 🚫 | Unauthorised roles cannot reach restricted documents | each | matrix of denials, below | §6.9 |

### RT-09 — the denial matrix

Each cell asserts **False**. A True is a defect.

| Role | Vehicle create | Driver create | Vehicle Log create | Asset Maint. Log create | GDL Fleet Settings write |
|---|---|---|---|---|---|
| Fleet User | False | False | False | False | False |
| Fleet Driver | False | False | **True** ✅ | False | False |
| Fleet Approver | False | False | False | False | False |
| Fleet Maintenance User | False | False | False | **True** ✅ | False |
| Fleet Store User | False | False | False | False | False |
| Fleet HR Approver | False | False | False | False | False |
| Fleet Administrator | **True** ✅ | **True** ✅ | **True** ✅ | **True** ✅ | **True** ✅ |

### Tests that keep the fix honest

| # | Test | Asserts |
|---|---|---|
| RT-10 | **Nothing was revoked** | Every permission present before the fix is still present. The fix is additive; a disappearance is a defect. |
| RT-11 | **Fleet Manager is untouched** | Its rows on Vehicle, Driver and Vehicle Log match ERPNext's shipped values exactly — it is a standard role |
| RT-12 | **Idempotent** | `setup_fleet_permissions()` twice in a row → second call grants nothing |
| RT-13 | **Survives a migrate** | After `bench migrate`, the matrix is unchanged |
| RT-14 | **No delete anywhere** | No GDL role has `delete` on any of the five DocTypes |
| RT-15 | **No import anywhere** | No GDL role has `import` |
| RT-16 | **Permlevel 1 unchanged** | Movement Order Request allocation rights are exactly as before |
| RT-17 | **`if_owner` unchanged** | Fleet User still has `if_owner = 1` on Movement Order Request |
| RT-18 | **Matrix matches the specification** | `permission_report()` equals §3 of the Permission Matrix, field by field |

RT-10, RT-11 and RT-18 matter most. A permission fix that quietly removes something, or
that edits a standard ERPNext role, is worse than the defect it fixes.

### Running it

```bash
bench --site erpnext16.localhost run-tests --module gdl_fleet_extension.tests.test_fleet_permissions
```

Then the full suite, to prove nothing else moved:

```bash
bench --site erpnext16.localhost run-tests --app gdl_fleet_extension
```

**Expected: 606 existing + ~25 new, all passing.** Any pre-existing test that newly fails
is a signal the fix changed behaviour it should not have.

---

## 3. Layer B — manual UI regression

**Blocked** until passwords and a browser exist. Maps to the user-wise scripts.

| # | Case | Script ID | Evidence |
|---|---|---|---|
| UI-01 | Fleet Administrator creates a Vehicle | TC-030 | `03_fleet_administrator/TC-030_create_vehicle.png` |
| UI-02 | Fleet Administrator creates a Driver | TC-034 | `03_fleet_administrator/TC-034_create_driver.png` |
| UI-03 | Fleet Driver records a Vehicle Log | TC-050 | `04_fleet_driver/TC-050_create_vehicle_log.png` |
| UI-04 | Fleet Maintenance User records a service | TC-080 | `06_maintenance/TC-080_create_service_log.png` |
| UI-05 | Fleet Manager opens all 18 reports | TC-103…118 | `08_fleet_manager/` |
| UI-06 🚫 | Fleet User cannot approve | TC-007 | `09_negative_permission/TC-007_cannot_approve.png` |
| UI-07 🚫 | Wrong-site MTO refused | TC-019 | `09_negative_permission/TC-019_wrong_site.png` |
| UI-08 🚫 | Driver cannot approve own POL | TC-062 | `09_negative_permission/TC-062_self_approve_pol.png` |
| UI-09 🚫 | Unauthorised access refused | TC-003, TC-006, TC-027 | `09_negative_permission/` |

Each screenshot must show the **logged-in user in the top-right**. A form without that
proves nothing about who was acting — which is the whole point here.

---

## 4. Entry and exit criteria

**Entry**
1. Fix approved and the four open questions in the Proposed Fix answered.
2. Staging backed up.
3. Tests run on development first.

**Exit**
1. RT-01 … RT-18 pass.
2. The 606 existing tests still pass.
3. The live matrix matches §3 of the Permission Matrix exactly.
4. No permission that existed before the fix is missing after it.
5. `Fleet Manager` byte-identical to ERPNext's shipped definition.
6. Layer B executed with screenshots — **or** formally deferred with the blocker recorded.

---

## 5. What this plan will not establish

| Not proven | Why |
|---|---|
| That a user can log in | `set_user()` does not exercise authentication |
| That forms render correctly | Needs a browser |
| That error messages are understandable | A human must read them |
| That the five roles are assigned to real people | GDL's task, not a test |
| Notification delivery | Email muted, scheduler paused by design |

Layer A proves the **rule** is right. Only Layer B proves the **system** is usable. Passing
Layer A alone is not grounds for UAT sign-off.
