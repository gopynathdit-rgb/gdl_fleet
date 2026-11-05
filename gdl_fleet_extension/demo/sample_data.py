# Copyright (c) 2026, GDL and contributors
"""
Realistic sample data for the GDL Fleet Extension.

Every record created is written to a manifest so `remove_sample_data()` can take
exactly those records back out, child-first, leaving nothing behind.

Run:
    bench --site <site> execute gdl_fleet_extension.demo.sample_data.create_sample_data
    bench --site <site> execute gdl_fleet_extension.demo.sample_data.remove_sample_data

This writes to the DEMO company only. It never touches Stock Settings, never
activates a workflow, and never edits the legacy app.
"""

import json
import os

import frappe
from frappe.utils import add_days, add_months, cint, flt, getdate, nowdate

COMPANY = "GDL (Demo)"
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "manifest.json")

# ---------------------------------------------------------------------------
_created: list[tuple[str, str]] = []


def _log(doctype, name):
    _created.append((doctype, name))
    # Written on every record, not just at the end: a run that fails half way
    # must still be completely removable.
    try:
        with open(MANIFEST, "w") as handle:
            json.dump(_created, handle, indent=1)
    except OSError:
        pass
    return name


def _save(doc, submit=False):
    doc.flags.ignore_permissions = True
    doc.insert()
    if submit:
        doc.submit()
    _log(doc.doctype, doc.name)
    return doc


# ===========================================================================
# Masters
# ===========================================================================
VEHICLE_TYPES = [
    ("Car", 5, "Petrol", 1),
    ("4WD Pickup", 5, "Diesel", 1),
    ("Bus", 30, "Diesel", 1),
    ("Truck", 3, "Diesel", 1),
    ("Tractor", 1, "Diesel", 1),
]

DRIVERS = [
    ("Karma Wangchuk", "17112233", "BT-DL-101", "Head Office"),
    ("Sonam Dorji", "17224455", "BT-DL-102", "Jamjee Farm"),
    ("Pema Tshering", "17336677", "BT-DL-103", "Gedu"),
    ("Tashi Namgay", "17448899", "BT-DL-104", "Samcholing"),
    ("Ugyen Choden", "17551122", "BT-DL-105", "Dochula Farm"),
    ("Dorji Phuntsho", "17663344", "BT-DL-106", "Jigmeling"),
]

EMPLOYEES = [
    ("Kinley", "Zangmo", "Female", "Head Office"),
    ("Jigme", "Wangdi", "Male", "Jamjee Farm"),
    ("Deki", "Yangzom", "Female", "Gedu"),
    ("Namgay", "Tenzin", "Male", "Samcholing"),
]

# registration, type, site, make, model, year, odometer, fuel, colour, owns_asset
VEHICLES = [
    ("BP-1-A1234", "4WD Pickup", "Head Office", "Toyota", "Hilux Revo", 2022, 42500, "Diesel", "White", True),
    ("BP-1-A2201", "Car", "Head Office", "Hyundai", "Creta", 2023, 31200, "Petrol", "Silver", True),
    ("BP-2-B3310", "4WD Pickup", "Jamjee Farm", "Isuzu", "D-Max", 2021, 58900, "Diesel", "Blue", True),
    ("BP-2-B4102", "Truck", "Gedu", "Tata", "LPT 1613", 2020, 76400, "Diesel", "Yellow", False),
    ("BP-3-C5520", "Bus", "Samcholing", "Ashok Leyland", "Falcon", 2019, 91300, "Diesel", "White", False),
    ("BP-3-C6014", "Tractor", "Dochula Farm", "Mahindra", "575 DI", 2022, 12800, "Diesel", "Red", False),
    ("BP-4-D7788", "4WD Pickup", "Jigmeling", "Toyota", "Hilux Revo", 2023, 23600, "Diesel", "Grey", False),
]


def _abbr():
    return frappe.get_cached_value("Company", COMPANY, "abbr")


def _account(**filters):
    base = {"company": COMPANY, "is_group": 0, "disabled": 0}
    base.update(filters)
    return frappe.db.get_value("Account", base, "name")


def create_vehicle_types():
    for name, seats, fuel, needs_driver in VEHICLE_TYPES:
        if frappe.db.exists("Fleet Vehicle Type", name):
            continue
        _save(frappe.get_doc({
            "doctype": "Fleet Vehicle Type", "vehicle_type_name": name,
            "default_seating_capacity": seats, "default_fuel_type": fuel,
            "requires_driver": needs_driver,
        }))


def create_employees():
    names = []
    for first, last, gender, _site in EMPLOYEES:
        existing = frappe.db.get_value(
            "Employee", {"employee_name": f"{first} {last}", "company": COMPANY}, "name")
        if existing:
            names.append(existing)
            continue
        doc = _save(frappe.get_doc({
            "doctype": "Employee", "first_name": first, "last_name": last,
            "gender": gender, "date_of_birth": "1992-04-15",
            "date_of_joining": "2021-01-04", "company": COMPANY, "status": "Active",
        }))
        names.append(doc.name)
    return names


def create_drivers(employees):
    names = []
    for index, (full_name, cell, licence, site) in enumerate(DRIVERS):
        existing = frappe.db.get_value("Driver", {"full_name": full_name}, "name")
        if existing:
            names.append(existing)
            continue
        doc = _save(frappe.get_doc({
            "doctype": "Driver", "full_name": full_name, "status": "Active",
            "cell_number": cell, "license_number": licence,
            "issuing_date": "2021-03-01",
            # one licence expires soon so the expiry alert has something to find
            "expiry_date": add_days(nowdate(), 20 if index == 0 else 400),
            "site": site,
        }))
        names.append(doc.name)
    return names


def _workshop_user():
    """A user of its own for the workshop team.

    `Maintenance Team Member` is autonamed by the member's email and that name is
    unique across every team, so a user already on another maintenance team
    cannot be reused. erpnext also raises the task ToDo against User.email, so
    the login name and the email must match.
    """
    email = "fleet.workshop@gdl.bt"
    if not frappe.db.exists("User", email):
        _save(frappe.get_doc({
            "doctype": "User", "email": email, "first_name": "Fleet",
            "last_name": "Workshop", "send_welcome_email": 0, "enabled": 1,
            "roles": [{"role": "Fleet Maintenance User"}],
        }))
    return email


def create_asset_prerequisites():
    category = "GDL Fleet Vehicles"
    if not frappe.db.exists("Asset Category", category):
        _save(frappe.get_doc({
            "doctype": "Asset Category", "asset_category_name": category,
            "accounts": [{
                "company_name": COMPANY,
                "fixed_asset_account": _account(account_type="Fixed Asset"),
                "accumulated_depreciation_account": _account(
                    account_type="Accumulated Depreciation"),
                "depreciation_expense_account": _account(account_type="Depreciation"),
            }],
        }))

    item = "GDL Fleet Vehicle Asset"
    if not frappe.db.exists("Item", item):
        _save(frappe.get_doc({
            "doctype": "Item", "item_code": item, "item_name": item,
            "item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
            "is_fixed_asset": 1, "is_stock_item": 0, "asset_category": category,
        }))

    team = "GDL Fleet Workshop"
    if not frappe.db.exists("Asset Maintenance Team", team):
        user = _workshop_user()
        _save(frappe.get_doc({
            "doctype": "Asset Maintenance Team", "maintenance_team_name": team,
            "company": COMPANY, "maintenance_manager": user,
            "maintenance_team_members": [
                {"team_member": user, "maintenance_role": "Fleet Maintenance User"}],
        }))
    return category, item, team


def create_asset(registration, purchase_amount, category, item):
    doc = _save(frappe.get_doc({
        "doctype": "Asset", "asset_name": f"Vehicle {registration}",
        "item_code": item, "asset_category": category, "company": COMPANY,
        "location": "Head Office", "purchase_date": "2022-04-01",
        "available_for_use_date": "2022-04-01", "asset_type": "Existing Asset",
        "calculate_depreciation": 0, "net_purchase_amount": purchase_amount,
        "asset_quantity": 1, "maintenance_required": 1,
    }), submit=True)
    return doc.name


def create_vehicles(drivers, category, item, team):
    created = []
    for index, (reg, vtype, site, make, model, year, odo, fuel, colour, owns) in enumerate(VEHICLES):
        if frappe.db.exists("Vehicle", reg):
            created.append(reg)
            continue

        values = {
            "doctype": "Vehicle", "license_plate": reg, "make": make, "model": model,
            "last_odometer": odo, "opening_odometer": odo, "fuel_type": fuel,
            "uom": "Litre", "company": COMPANY, "colour": colour, "color": colour,
            "vehicle_type": vtype, "ownership_type": "GDL Owned", "site": site,
            "cost_center": f"Main - {_abbr()}",
            "driver": drivers[index % len(drivers)],
            "manufacturing_year": year,
            "chassis_no": f"CH{year}{1000 + index}",
            "engine_no": f"EN{year}{2000 + index}",
            "acquisition_date": f"{year}-04-01",
            "vehicle_value": 1450000 + index * 120000,
            "insurance_company": "Royal Insurance Corporation of Bhutan",
            "policy_no": f"RICB/MV/{year}/{4400 + index}",
            "start_date": add_months(nowdate(), -10),
            # the first two expire inside the 30-day notice window
            "end_date": add_days(nowdate(), 18 if index == 0 else 200 + index * 20),
            "registration_expiry": add_days(nowdate(), 25 if index == 1 else 300 + index * 15),
            "inspection_expiry": add_days(nowdate(), 150 + index * 10),
            "expected_monthly_km": [2500, 1800, 3000, 3500, 2200, 600, 2400][index],
            "documents": [
                {"document_type": "Registration Certificate",
                 "document_number": f"RC/{reg}", "issue_date": f"{year}-04-05",
                 "expiry_date": add_days(nowdate(), 25 if index == 1 else 300)},
                {"document_type": "Insurance", "document_number": f"RICB/MV/{year}/{4400+index}",
                 "issue_date": add_months(nowdate(), -10),
                 "expiry_date": add_days(nowdate(), 18 if index == 0 else 200)},
            ],
        }
        if owns:
            values["asset"] = create_asset(reg, 1450000 + index * 120000, category, item)

        doc = _save(frappe.get_doc(values))
        created.append(doc.name)
    return created


def create_stock_masters():
    warehouse = f"GDL Fleet Store - {_abbr()}"
    if not frappe.db.exists("Warehouse", warehouse):
        _save(frappe.get_doc({
            "doctype": "Warehouse", "warehouse_name": "GDL Fleet Store",
            "company": COMPANY}))

    group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
    items = []
    for code, name, rate in [
        ("GDL-SP-OIL", "Engine Oil 15W-40 (4L)", 1450),
        ("GDL-SP-OILFLT", "Engine Oil Filter", 480),
        ("GDL-SP-FUELFLT", "Fuel Filter", 760),
        ("GDL-SP-BRKPAD", "Brake Pad Set", 2900),
        ("GDL-SP-BATT", "Battery 12V 90Ah", 8600),
    ]:
        if not frappe.db.exists("Item", code):
            _save(frappe.get_doc({
                "doctype": "Item", "item_code": code, "item_name": name,
                "item_group": group, "is_stock_item": 1, "stock_uom": "Nos",
                "valuation_rate": rate,
            }))
        items.append(code)
    return warehouse, items


def receive_stock(warehouse, items):
    rows = [{"item_code": code, "qty": 20, "t_warehouse": warehouse,
             "basic_rate": flt(frappe.db.get_value("Item", code, "valuation_rate")) or 500}
            for code in items]
    _save(frappe.get_doc({
        "doctype": "Stock Entry", "stock_entry_type": "Material Receipt",
        "company": COMPANY, "posting_date": add_days(nowdate(), -40), "items": rows,
    }), submit=True)


def configure_settings():
    settings = frappe.get_single("GDL Fleet Settings")
    changed = False

    if not settings.default_maintenance_team and frappe.db.exists(
            "Asset Maintenance Team", "GDL Fleet Workshop"):
        settings.default_maintenance_team = "GDL Fleet Workshop"
        changed = True

    if not settings.get("mileage_norms"):
        for vtype, km in [("Car", 1800), ("4WD Pickup", 2500), ("Bus", 2200),
                          ("Truck", 3500), ("Tractor", 600)]:
            settings.append("mileage_norms", {
                "vehicle_type": vtype, "expected_km_per_month": km, "is_active": 1})
        changed = True

    if not settings.get("site_requirements"):
        for site, vtype, minimum in [
            ("Head Office", "Car", 2), ("Head Office", "4WD Pickup", 2),
            ("Jamjee Farm", "4WD Pickup", 2), ("Gedu", "Truck", 2),
            ("Samcholing", "Bus", 1), ("Dochula Farm", "Tractor", 2),
            ("Jigmeling", "4WD Pickup", 1),
        ]:
            settings.append("site_requirements", {
                "site": site, "vehicle_type": vtype,
                "minimum_required": minimum, "is_active": 1})
        changed = True

    if not settings.default_spare_warehouse:
        settings.default_spare_warehouse = f"GDL Fleet Store - {_abbr()}"
        changed = True

    if changed:
        settings.flags.ignore_permissions = True
        settings.save()
    return changed


# ===========================================================================
# Transactions
# ===========================================================================
def create_bookings(vehicles, drivers, employees):
    from frappe.model.workflow import apply_workflow

    plans = [
        ("Field inspection of the plantation blocks", "Jamjee Farm", "4WD Pickup",
         3, 3, "Routine", "full"),
        ("Carry staff to the district office", "Head Office", "Car",
         5, 2, "Critical Business", "review"),
        ("Move seedlings to the nursery", "Gedu", "Truck", 7, 2, "Routine", "draft"),
        ("Emergency medical run", "Samcholing", "Bus", 1, 8, "Emergency", "full"),
    ]

    names = []
    for index, (purpose, site, vtype, in_days, passengers, priority, depth) in enumerate(plans):
        doc = _save(frappe.get_doc({
            "doctype": "Movement Order Request",
            "requester": frappe.session.user,
            "employee": employees[index % len(employees)],
            "site": site, "purpose": purpose, "usage_type": "Official",
            "priority": priority, "passenger_count": passengers,
            "vehicle_type": vtype,
            "required_date": add_days(nowdate(), in_days),
            "required_from_time": "08:00:00", "required_to_time": "17:00:00",
            "pickup_location": "Head Office", "destination": site,
            "cost_center": f"Main - {_abbr()}",
        }))

        if depth == "draft":
            names.append(doc.name)
            continue

        apply_workflow(doc, "Submit for Validation")
        apply_workflow(doc.reload(), "Validate")
        apply_workflow(doc.reload(), "Review")
        apply_workflow(doc.reload(), "Approve")      # MTO/CEO
        if depth == "review":
            names.append(doc.name)
            continue

        apply_workflow(doc.reload(), "Approve")      # FAS -> Approved
        doc.reload()
        match = next((v for v in vehicles
                      if frappe.db.get_value("Vehicle", v, "vehicle_type") == vtype), None)
        if match:
            doc.vehicle = match
            doc.driver = frappe.db.get_value("Vehicle", match, "driver") or drivers[0]
            doc.flags.ignore_permissions = True
            doc.save()
            apply_workflow(doc.reload(), "Assign Vehicle")
        names.append(doc.name)
    return names


def create_vehicle_logs(vehicles, employees):
    """Trips through August and September.

    August distances are deliberately calibrated against each vehicle's
    Expected Monthly KM so the deviation report shows a realistic spread: most
    vehicles on target, one well under and one well over.
    """
    plan = {
        # registration: [(date, km, from, to, purpose)]   August target in the comment
        "BP-1-A1234": [                                   # expect 2500 -> 2540, on target
            ("2026-08-04", 380, "Head Office", "Jamjee Farm", "Field inspection"),
            ("2026-08-12", 620, "Head Office", "Samcholing", "Quarterly audit"),
            ("2026-08-19", 810, "Head Office", "Gedu", "Supervision visit"),
            ("2026-08-27", 730, "Head Office", "Jamjee Farm", "Harvest planning"),
            ("2026-09-08", 540, "Head Office", "Gedu", "Monthly review"),
            ("2026-09-17", 410, "Head Office", "Jamjee Farm", "Input delivery"),
        ],
        "BP-1-A2201": [                                   # expect 1800 -> 1150, well under
            ("2026-08-06", 210, "Head Office", "Head Office", "Bank and office errands"),
            ("2026-08-18", 480, "Head Office", "Gedu", "Staff transport"),
            ("2026-08-26", 460, "Head Office", "Head Office", "Official meetings"),
            ("2026-09-11", 260, "Head Office", "Head Office", "Office errands"),
        ],
        "BP-2-B3310": [                                   # expect 3000 -> 3080, on target
            ("2026-08-05", 720, "Jamjee Farm", "Dagapela Farm", "Inter-farm transfer"),
            ("2026-08-13", 880, "Jamjee Farm", "Gedu", "Input delivery"),
            ("2026-08-21", 840, "Jamjee Farm", "Dochula Farm", "Seedling delivery"),
            ("2026-08-29", 640, "Jamjee Farm", "Jamjee Farm", "Block patrol"),
            ("2026-09-12", 690, "Jamjee Farm", "Gedu", "Fertiliser collection"),
        ],
        "BP-2-B4102": [                                   # expect 3500 -> 4480, well over
            ("2026-08-03", 1150, "Gedu", "Jigmeling", "Fertiliser haulage"),
            ("2026-08-11", 1240, "Gedu", "Samcholing", "Produce haulage"),
            ("2026-08-20", 1090, "Gedu", "Jamjee Farm", "Equipment haulage"),
            ("2026-08-28", 1000, "Gedu", "Jigmeling", "Return haulage"),
            ("2026-09-09", 980, "Gedu", "Samcholing", "Produce haulage"),
        ],
        "BP-3-C5520": [                                   # expect 2200 -> 2150, on target
            ("2026-08-08", 760, "Samcholing", "Head Office", "Staff shuttle"),
            ("2026-08-19", 700, "Samcholing", "Gedu", "Staff shuttle"),
            ("2026-08-27", 690, "Samcholing", "Head Office", "Staff shuttle"),
            ("2026-09-15", 640, "Samcholing", "Head Office", "Staff shuttle"),
        ],
        "BP-3-C6014": [                                   # expect 600 -> 580, on target
            ("2026-08-07", 180, "Dochula Farm", "Dochula Farm", "Field ploughing"),
            ("2026-08-16", 210, "Dochula Farm", "Dochula Farm", "Field ploughing"),
            ("2026-08-25", 190, "Dochula Farm", "Dochula Farm", "Field harrowing"),
            ("2026-09-14", 160, "Dochula Farm", "Dochula Farm", "Field ploughing"),
        ],
        "BP-4-D7788": [                                   # expect 2400 -> 2360, on target
            ("2026-08-09", 610, "Jigmeling", "Gedu", "Site survey"),
            ("2026-08-17", 720, "Jigmeling", "Jigmeling", "Boundary patrol"),
            ("2026-08-26", 1030, "Jigmeling", "Dagapela Farm", "Plantation visit"),
            ("2026-09-16", 575, "Jigmeling", "Gedu", "Material collection"),
        ],
    }

    logs = []
    for index, (registration, trips) in enumerate(plan.items()):
        if not frappe.db.exists("Vehicle", registration):
            continue
        odometer = cint(frappe.db.get_value("Vehicle", registration, "last_odometer"))
        for trip_date, distance, start, destination, purpose in trips:
            odometer += distance
            doc = _save(frappe.get_doc({
                "doctype": "Vehicle Log", "license_plate": registration,
                "employee": employees[index % len(employees)],
                "date": trip_date, "odometer": odometer,
                "usage_type": "Official", "start_location": start,
                "destination": destination, "purpose": purpose,
            }), submit=True)
            logs.append(doc.name)
    return logs


def create_fuel_entries(vehicles, drivers):
    """Full-tank fills so the efficiency report has complete intervals."""
    supplier = "Druk Petroleum Depot"
    if not frappe.db.exists("Supplier", supplier):
        _save(frappe.get_doc({
            "doctype": "Supplier", "supplier_name": supplier,
            "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
        }))

    entries = []
    for registration in ("BP-1-A1234", "BP-2-B3310", "BP-2-B4102"):
        if not frappe.db.exists("Vehicle", registration):
            continue
        current = cint(frappe.db.get_value("Vehicle", registration, "last_odometer"))
        fuel_type = frappe.db.get_value("Vehicle", registration, "fuel_type")
        driver = frappe.db.get_value("Vehicle", registration, "driver")

        # Three full tanks -> two complete intervals.
        # Dated AFTER the last trip so these readings do not inflate the August
        # distance the deviation report measures.
        for step, (fill_date, qty, rate, full) in enumerate([
            ("2026-09-18", 55, 92.5, 1), ("2026-09-20", 48, 94.0, 1),
            ("2026-09-22", 52, 95.5, 1),
        ]):
            current += 0 if step == 0 else 470
            # Fleet Fuel Entry was retired; the final requirements document
            # captures each fill as a POL Entry row on the POL Abstract.
            entries.append({
                "supply_memo_no": f"DPD/{fill_date[5:7]}{fill_date[8:]}/{registration[-4:]}",
                "date": fill_date, "fuel_type": fuel_type, "driver": driver,
                "litres": qty, "rate": rate, "odometer": current,
                "supplier": supplier,
            })
    return entries


def create_maintenance(vehicles):
    from gdl_fleet_extension.utils.maintenance import create_maintenance_plan

    plans, logs, repairs = [], [], []
    for registration in ("BP-1-A1234", "BP-1-A2201", "BP-2-B3310"):
        if not frappe.db.exists("Vehicle", registration):
            continue
        if not frappe.db.get_value("Vehicle", registration, "asset"):
            continue

        plan_name = create_maintenance_plan(
            registration, maintenance_team="GDL Fleet Workshop")
        if plan_name not in [n for _d, n in _created]:
            _log("Asset Maintenance", plan_name)
        plans.append(plan_name)

        plan = frappe.get_doc("Asset Maintenance", plan_name)
        task = next((t for t in plan.asset_maintenance_tasks
                     if t.maintenance_task == "Engine Oil"), None)
        if not task:
            continue

        odometer = cint(frappe.db.get_value("Vehicle", registration, "last_odometer"))
        doc = _save(frappe.get_doc({
            "doctype": "Asset Maintenance Log", "asset_maintenance": plan_name,
            "asset_name": plan.asset_name, "task": task.name, "task_name": "Engine Oil",
            "maintenance_type": task.maintenance_type, "periodicity": task.periodicity,
            "due_date": task.next_due_date, "completion_date": add_days(nowdate(), -12),
            "maintenance_status": "Completed", "odometer": odometer,
            "actions_performed": "Engine oil and filter changed, levels topped up.",
            "service_provider": None, "labour_cost": 800, "parts_cost": 1930,
            "cost_center": f"Main - {_abbr()}",
        }), submit=True)
        logs.append(doc.name)

    # Put one vehicle's oil change genuinely past its threshold, so the
    # Maintenance Due report has something real to show.
    overdue_on = "BP-2-B3310"
    plan_name = frappe.db.get_value("Asset Maintenance", {"vehicle": overdue_on}, "name")
    if plan_name:
        plan = frappe.get_doc("Asset Maintenance", plan_name)
        current = cint(frappe.db.get_value("Vehicle", overdue_on, "last_odometer"))
        for row in plan.asset_maintenance_tasks:
            if row.maintenance_task == "Engine Oil Filter":
                row.next_due_odometer = current - 300      # 300 km overdue
            elif row.maintenance_task == "Fuel Filter":
                row.next_due_odometer = current + 250      # inside the notice window
        plan.flags.ignore_permissions = True
        plan.save()

    # One corrective repair. NOTE: Asset Repair.repair_cost is READ ONLY in
    # ERPNext - it is derived from linked purchase invoices and consumed stock,
    # so the cost is created by consuming a real part, which also produces the
    # Material Issue and the GL posting.
    registration = "BP-2-B3310"
    asset = frappe.db.get_value("Vehicle", registration, "asset")
    warehouse = f"GDL Fleet Store - {_abbr()}"
    if asset:
        doc = _save(frappe.get_doc({
            "doctype": "Asset Repair", "asset": asset, "company": COMPANY,
            "failure_date": add_days(nowdate(), -9) + " 09:30:00",
            "completion_date": add_days(nowdate(), -7) + " 16:00:00",
            "repair_status": "Completed", "maintenance_category": "Corrective",
            "description": "Front suspension bush worn out after farm-track use.",
            "actions_performed": "Both front bushes replaced and wheel alignment done.",
            "labour_cost": 3200,
            "odometer": cint(frappe.db.get_value("Vehicle", registration, "last_odometer")),
            "cost_center": f"Main - {_abbr()}",
            "stock_items": [{
                "item_code": "GDL-SP-BRKPAD", "warehouse": warehouse,
                "consumed_quantity": 1, "valuation_rate": 2900,
            }],
        }), submit=True)
        repairs.append(doc.name)

    return plans, logs, repairs







# ===========================================================================
# Entry points
# ===========================================================================
def sample_data_present():
    """Demo vehicles are the marker: their registrations are distinctive."""
    return bool(frappe.db.exists("Vehicle", VEHICLES[0][0]))


@frappe.whitelist()
def create_sample_data(force=0):
    """Build a complete, realistic fleet in the DEMO company.

    Transactions are NOT idempotent - running twice would stack duplicate
    bookings, logs and claims - so a second run is refused. ERPNext commits
    internally during asset submission and workflow actions, which means a
    failed run can leave records behind; remove_sample_data cleans those out.
    """
    if not frappe.db.exists("Company", COMPANY):
        frappe.throw(f"Company {COMPANY} does not exist on this site.")

    if sample_data_present() and not cint(force):
        frappe.throw(
            "Sample data already exists. Run "
            "gdl_fleet_extension.demo.sample_data.remove_sample_data first."
        )

    _created.clear()
    summary = {}

    create_vehicle_types()
    employees = create_employees()
    drivers = create_drivers(employees)
    category, item, team = create_asset_prerequisites()
    vehicles = create_vehicles(drivers, category, item, team)
    warehouse, items = create_stock_masters()
    receive_stock(warehouse, items)
    configure_settings()

    summary["vehicle_types"] = len(VEHICLE_TYPES)
    summary["employees"] = len(employees)
    summary["drivers"] = len(drivers)
    summary["vehicles"] = len(vehicles)
    summary["spare_items"] = len(items)

    summary["bookings"] = len(create_bookings(vehicles, drivers, employees))
    summary["vehicle_logs"] = len(create_vehicle_logs(vehicles, employees))
    summary["fuel_entries"] = len(create_fuel_entries(vehicles, drivers))

    plans, logs, repairs = create_maintenance(vehicles)
    summary["maintenance_plans"] = len(plans)
    summary["maintenance_logs"] = len(logs)
    summary["asset_repairs"] = len(repairs)

    with open(MANIFEST, "w") as handle:
        json.dump(_created, handle, indent=1)

    frappe.db.commit()
    summary["records_created"] = len(_created)
    summary["manifest"] = MANIFEST
    return summary


def _discover_sample_records():
    """Find demo records by their distinctive values.

    The manifest can be incomplete if a run failed part way, so removal also
    sweeps for the records this module is known to create. Only records matching
    these exact demo identifiers are touched.
    """
    found = []
    registrations = [v[0] for v in VEHICLES]

    # transactions first, masters last
    for doctype, filters in (
        ("Fleet Accident Report", {"vehicle": ("in", registrations)}),
        ("Fleet Mileage Deviation", {"vehicle": ("in", registrations)}),
        ("Fleet Tyre Installation", {"vehicle": ("in", registrations)}),
        ("Expense Claim", {"vehicle": ("in", registrations)}),
        ("Movement Order Request", {"vehicle_type": ("is", "set")}),
        ("Vehicle Log", {"license_plate": ("in", registrations)}),
        ("Asset Repair", {"vehicle": ("in", registrations)}),
        ("Asset Maintenance Log", {"vehicle": ("in", registrations)}),
        ("Asset Maintenance", {"vehicle": ("in", registrations)}),
        ("Material Request", {"fleet_request_type": ("is", "set")}),
        ("Stock Entry", {"company": COMPANY, "posting_date": (">=", "2026-07-01")}),
        ("Vehicle", {"name": ("in", registrations)}),
        ("Asset", {"asset_name": ("like", "Vehicle BP-%")}),
        ("Driver", {"full_name": ("in", [d[0] for d in DRIVERS])}),
        ("Employee", {"employee_name": ("in", [f"{f} {l}" for f, l, _g, _s in EMPLOYEES])}),
        ("Item", {"item_code": ("like", "GDL-SP-%")}),
        ("Item", {"item_code": ("like", "GDL-TYRE-%")}),
        ("Item", {"item_code": "GDL Fleet Vehicle Asset"}),
        ("Asset Maintenance Team", {"name": "GDL Fleet Workshop"}),
        ("Asset Category", {"name": "GDL Fleet Vehicles"}),
        ("Warehouse", {"warehouse_name": "GDL Fleet Store"}),
        ("Supplier", {"supplier_name": "Druk Petroleum Depot"}),
        ("User", {"name": "fleet.workshop@gdl.bt"}),
    ):
        try:
            for name in frappe.get_all(doctype, filters=filters, pluck="name"):
                found.append((doctype, name))
        except Exception:
            continue
    return found


@frappe.whitelist()
def remove_sample_data():
    """Remove the demo records, newest first.

    Uses the manifest where it exists and also sweeps for known demo records, so
    a partially-completed run is still cleaned up.
    """
    records = []
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as handle:
            records = [tuple(r) for r in json.load(handle)]

    # The manifest is chronological, so it is walked backwards. The sweep is
    # already written in dependency order (transactions first, masters last), so
    # it must NOT be reversed - doing so deletes an Item before the Stock Entry
    # that references it.
    ordered = list(reversed(records))
    seen = set(ordered)
    for entry in _discover_sample_records():
        if entry not in seen:
            ordered.append(entry)
            seen.add(entry)

    if not ordered:
        return {"removed": 0, "note": "no sample data found"}

    removed, failed = 0, []
    # Two passes: a document freed by the first pass can go in the second.
    for _pass in range(2):
        failed = []
        for doctype, name in ordered:
            if not frappe.db.exists(doctype, name):
                continue
            try:
                doc = frappe.get_doc(doctype, name)
                if doc.docstatus == 1:
                    doc.flags.ignore_permissions = True
                    doc.cancel()
                frappe.delete_doc(doctype, name, force=1, ignore_permissions=True,
                                  delete_permanently=True)
                removed += 1
            except Exception as exc:
                failed.append({"doctype": doctype, "name": name, "error": str(exc)[:160]})
        if not failed:
            break

    frappe.db.commit()
    if not failed and os.path.exists(MANIFEST):
        os.remove(MANIFEST)
    return {"removed": removed, "failed": failed[:12], "failed_count": len(failed)}


@frappe.whitelist()
def sample_data_status():
    """What the demo data looks like right now."""
    counts = {}
    for doctype in ("Fleet Vehicle Type", "Driver", "Vehicle", "Movement Order Request",
                    "Vehicle Log", "Asset", "Asset Maintenance",
                    "Asset Maintenance Log", "Asset Repair", "Material Request",
                    "Stock Entry", "Fleet Tyre Installation", "Expense Claim",
                    "Fleet Mileage Deviation", "Fleet Accident Report"):
        try:
            counts[doctype] = frappe.db.count(doctype)
        except Exception:
            counts[doctype] = None
    return {
        "company": COMPANY,
        "manifest_present": os.path.exists(MANIFEST),
        "manifest_records": len(json.load(open(MANIFEST))) if os.path.exists(MANIFEST) else 0,
        "counts": counts,
    }
