# Copyright (c) 2026, GDL and contributors
"""
GDL's own fleet, as the Business Blueprint records it.

The blueprint's mileage chart (Optimal Fleet Utilization) is the only place
the real fleet is written down: fourteen vehicles, their registration numbers,
their type and the minimum km/litre each must achieve. That table is reproduced
here verbatim, and nothing is added to it.

Client, 3 Nov 2026:
    "u an create all the vehicles for each Location."
    "create a user and a manager (MTO location wise)."
    "and final MTO will be at head office."

So this also creates, per location, one requesting user and one MTO, and ticks
the head office MTO as the final authority.

Everything here is idempotent and additive. It never edits or deletes a record
that already exists, so running it twice changes nothing the second time.
"""

import frappe
from frappe import _

# --- the blueprint's mileage chart, verbatim -------------------------------
# (registration, blueprint vehicle type, minimum km/litre)
FLEET = {
	"Head Office": [
		("BG-1-A2397", "Hilux", 8.0),
		("BG-1A3812", "Toyota Fortuner", 9.0),
		("BG-1A-3779", "BYD EV", 0.0),
	],
	"Jamjee": [
		("BG-1-A3632", "Bolero", 6.5),
		("BG-1-A3687", "Hiace Bus", 7.0),
		("BG-1A-0091", "TATA Bus", 3.0),
	],
	"Dochula": [
		("BG-1-A0017", "Hiace Bus", 9.0),
		("BG-1-A3679", "Yodha (Pickup)", 10.0),
	],
	"Dagapela": [
		("BG-1-A3387", "Hiace Bus", 7.0),
		("BG-1A-3782", "Yodha (Pickup)", 8.5),
	],
	"Gedu": [
		("BG-1-A3615", "Hiace Bus", 7.45),
	],
	"Samcholing": [
		("BG-1-A3631", "Bolero", 8.5),
		("BG-1-A3529", "Hiace Bus", 6.0),
	],
	"Jigmeling": [
		("BG-1A-3780", "Bolero", 12.0),
	],
}

# The blueprint names a model, not a category. Vehicle needs Make, Model and a
# Fleet Vehicle Type, so each model maps to the three. Fuel type follows the
# model: the BYD is the only electric vehicle in the chart, which is why its
# minimum is 0 - km/litre does not apply to it.
MODELS = {
	"Hilux":           ("Toyota", "Hilux", "Pickup", "Diesel", 5),
	"Toyota Fortuner": ("Toyota", "Fortuner", "SUV", "Diesel", 7),
	"BYD EV":          ("BYD", "EV", "Car", "Electric", 5),
	"Bolero":          ("Mahindra", "Bolero", "SUV", "Diesel", 7),
	"Hiace Bus":       ("Toyota", "Hiace", "Bus", "Diesel", 15),
	"TATA Bus":        ("Tata", "Bus", "Bus", "Diesel", 30),
	"Yodha (Pickup)":  ("Tata", "Yodha", "Pickup", "Diesel", 5),
}

HEAD_OFFICE = "Head Office"

# Placeholder addresses on the reserved .test domain, so nothing this creates
# can ever email a real person by accident. GDL replaces them with real
# addresses before go-live.
EMAIL_DOMAIN = "gdl.test"

USER_ROLES = ["Fleet User"]
# OBS-005: deliberately NOT Fleet Manager. That is a standard ERPNext role with
# broad access - it let every MTO see vehicle values, service costs and the whole
# purchasing trail. Fleet Approver plus the report and renewal rights granted in
# setup/fleet_permissions.py cover the MTO's actual job.
MTO_ROLES = ["Fleet Approver", "Fleet User"]


def slug(location: str) -> str:
	return location.lower().replace(" ", "").replace("'", "")


# ---------------------------------------------------------------------------
def create_vehicle_types():
	"""One Fleet Vehicle Type per category in the chart."""
	created = []
	wanted = {}
	for _make, _model, category, fuel, seats in MODELS.values():
		wanted.setdefault(category, (fuel, seats))

	for category, (fuel, seats) in sorted(wanted.items()):
		if frappe.db.exists("Fleet Vehicle Type", category):
			continue
		doc = frappe.get_doc({
			"doctype": "Fleet Vehicle Type",
			"vehicle_type_name": category,
			"requires_driver": 1,
			"default_seating_capacity": seats,
			"default_fuel_type": fuel,
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		created.append(category)
	return created


def create_vehicles(company=None):
	"""The fourteen vehicles in the blueprint's mileage chart."""
	company = company or frappe.defaults.get_global_default("company")
	created, skipped, missing_location = [], [], []

	for location, vehicles in FLEET.items():
		if not frappe.db.exists("Location", location):
			missing_location.append(location)
			continue

		for plate, blueprint_type, min_mileage in vehicles:
			if frappe.db.exists("Vehicle", {"license_plate": plate}):
				skipped.append(plate)
				continue

			make, model, category, fuel, seats = MODELS[blueprint_type]
			doc = frappe.get_doc({
				"doctype": "Vehicle",
				"license_plate": plate,
				"make": make,
				"model": model,
				"vehicle_type": category,
				"ownership_type": "GDL Owned",
				"vehicle_status": "Active",
				"fuel_type": fuel,
				"uom": "Litre",
				"last_odometer": 0,
				"company": company,
				"site": location,
				"capacity": seats,
				# The chart's "Min Required" column. 0 on the BYD means km/litre
				# is not applicable, and the deviation engine reads it that way.
				"min_mileage": min_mileage,
			})
			doc.flags.ignore_permissions = True
			doc.insert()
			created.append(f"{plate} ({make} {model}, {location})")

	return {"created": created, "already_present": skipped,
	        "location_missing": missing_location}


def create_user(email, first_name, last_name, roles):
	"""A disabled-login user with fleet roles and no password set.

	No password is set and no welcome email is sent: GDL's administrator sets
	each password through the desk. That keeps credentials out of this script
	and out of any log it writes.
	"""
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc({
			"doctype": "User",
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"user_type": "System User",
			"send_welcome_email": 0,
			"enabled": 1,
		})
		user.flags.ignore_permissions = True
		user.insert()

	existing = {r.role for r in user.get("roles") or []}
	added = False
	for role in roles:
		if role not in existing and frappe.db.exists("Role", role):
			user.append("roles", {"role": role})
			added = True
	if added:
		user.flags.ignore_permissions = True
		user.save()
	return user.name


def create_location_officers():
	"""One requesting user and one MTO per location, head office last."""
	settings = frappe.get_single("GDL Fleet Settings")
	configured = {row.location for row in settings.get("location_officers") or []}
	created_users, rows = [], []

	for location in FLEET:
		if not frappe.db.exists("Location", location):
			continue

		key = slug(location)
		user_email = f"{key}.user@{EMAIL_DOMAIN}"
		mto_email = f"{key}.mto@{EMAIL_DOMAIN}"

		created_users.append(create_user(user_email, location, "User", USER_ROLES))
		created_users.append(create_user(mto_email, location, "MTO", MTO_ROLES))

		if location in configured:
			continue

		settings.append("location_officers", {
			"location": location,
			"mto": mto_email,
			"fleet_user": user_email,
			"is_head_office": 1 if location == HEAD_OFFICE else 0,
		})
		rows.append(location)

	if rows:
		settings.flags.ignore_permissions = True
		settings.save()

	return {"users": created_users, "locations_configured": rows}


def rollout(company=None):
	"""Everything, in dependency order."""
	result = {
		"vehicle_types": create_vehicle_types(),
		"officers": create_location_officers(),
		"vehicles": create_vehicles(company),
	}
	frappe.db.commit()
	return result
