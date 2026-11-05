# Copyright (c) 2026, GDL and contributors
"""
The GDL fleet, from the mileage chart in
`Fleet Management- Final. 25-Sept.docx` (Optimal Fleet Utilization).

The chart gives, for each vehicle: office/site, registration number, vehicle
type and the minimum required km/l. Those four things are loaded here and
nothing else is invented - chassis numbers, engine numbers, acquisition dates
and odometer readings are left blank for GDL to fill from the registration
documents.

Two judgements are recorded rather than hidden:

  * Fuel type is not in the chart. Every vehicle is set to Diesel except the
    BYD EV, which is Electric. Correct these if any run on petrol.
  * Odometers start at 0. The first Vehicle Log or POL Abstract will set the
    real reading; seeding a guess would corrupt distance and mileage from the
    first day.

The chart is explicitly a requirement example, not necessarily the whole fleet,
so this only ever ADDS vehicles that are missing. An existing vehicle is never
overwritten.
"""

import frappe

COMPANY = "GDL"

# vehicle type name -> (requires driver, default fuel)
VEHICLE_TYPES = {
	"Car": (1, "Petrol"),
	"SUV": (1, "Diesel"),
	"Bus": (1, "Diesel"),
	"Truck": (1, "Diesel"),
	"Utility": (1, "Diesel"),
}

# (registration, site, make, model, vehicle type, minimum km/l, fuel)
FLEET = [
	# Head Office
	("BG-1-A2397",  "Head Office",   "Toyota", "Hilux",          "Utility", 8.0,  "Diesel"),
	("BG-1A3812",   "Head Office",   "Toyota", "Fortuner",       "SUV",     9.0,  "Diesel"),
	("BG-1A-3779",  "Head Office",   "BYD",    "EV",             "Car",     0.0,  "Electric"),
	# Jamjee Farm
	("BG-1-A3632",  "Jamjee Farm",   "Mahindra", "Bolero",       "SUV",     6.5,  "Diesel"),
	("BG-1-A3687",  "Jamjee Farm",   "Toyota", "Hiace Bus",      "Bus",     7.0,  "Diesel"),
	("BG-1A-0091",  "Jamjee Farm",   "TATA",   "TATA Bus",       "Bus",     3.0,  "Diesel"),
	# Dochula Farm
	("BG-1-A0017",  "Dochula Farm",  "Toyota", "Hiace Bus",      "Bus",     9.0,  "Diesel"),
	("BG-1-A3679",  "Dochula Farm",  "TATA",   "Yodha (Pickup)", "Utility", 10.0, "Diesel"),
	# Dagapela Farm
	("BG-1-A3387",  "Dagapela Farm", "Toyota", "Hiace Bus",      "Bus",     7.0,  "Diesel"),
	("BG-1A-3782",  "Dagapela Farm", "TATA",   "Yodha (Pickup)", "Utility", 8.5,  "Diesel"),
	# Gedu
	("BG-1-A3615",  "Gedu",          "Toyota", "Hiace Bus",      "Bus",     7.45, "Diesel"),
	# Samcholing
	("BG-1-A3631",  "Samcholing",    "Mahindra", "Bolero",       "SUV",     8.5,  "Diesel"),
	("BG-1-A3529",  "Samcholing",    "Toyota", "Hiace Bus",      "Bus",     6.0,  "Diesel"),
	# Jigmeling
	("BG-1A-3780",  "Jigmeling",     "Mahindra", "Bolero",       "SUV",     12.0, "Diesel"),
]


def create_vehicle_types():
	"""The five types the document names. Existing types are left alone."""
	created = []
	for name, (requires_driver, fuel) in VEHICLE_TYPES.items():
		if frappe.db.exists("Fleet Vehicle Type", name):
			continue
		doc = frappe.get_doc({
			"doctype": "Fleet Vehicle Type",
			"vehicle_type_name": name,
			"requires_driver": requires_driver,
			"default_fuel_type": fuel,
			"description": "From the vehicle type list in Fleet Management Final 25-Sept.",
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		created.append(name)
	return created


def load_fleet(company=COMPANY):
	"""Add any chart vehicle that is not already registered.

	Returns what was created, what was already there, and anything that could
	not be loaded, so the caller can report honestly rather than assume.
	"""
	create_vehicle_types()

	created, existed, skipped = [], [], []
	uom = "Litre" if frappe.db.exists("UOM", "Litre") else None

	for registration, site, make, model, vehicle_type, min_mileage, fuel in FLEET:
		if frappe.db.exists("Vehicle", registration):
			existed.append(registration)
			continue
		if not frappe.db.exists("Location", site):
			skipped.append((registration, f"site '{site}' does not exist"))
			continue

		doc = frappe.get_doc({
			"doctype": "Vehicle",
			"license_plate": registration,
			"make": make,
			"model": model,
			"vehicle_type": vehicle_type,
			"site": site,
			"company": company,
			"ownership_type": "GDL Owned",
			"fuel_type": fuel,
			"uom": uom,
			"last_odometer": 0,
			"min_mileage": min_mileage,
		})
		doc.flags.ignore_permissions = True
		try:
			doc.insert()
			created.append(registration)
		except Exception as exc:
			skipped.append((registration, str(exc).split("\n")[0][:120]))

	return {"created": created, "already_present": existed, "skipped": skipped}


@frappe.whitelist()
def load_gdl_fleet():
	"""Run the loader from the UI or `bench execute`."""
	frappe.only_for("System Manager")
	result = load_fleet()
	frappe.db.commit()
	return result
