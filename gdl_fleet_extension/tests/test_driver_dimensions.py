# Copyright (c) 2026, GDL and contributors
"""The accounting dimensions are not a driver's business.

GDL, looking at the Vehicle Log as a driver: "in driver login i dont need this
field" - Site, Department, Cost Center, Project and Task. Those are how FINANCE
files a journey, not how a driver records one, and they sat as five empty boxes
between the driver and the odometer reading.

The same section sits on POL Abstract and GDL asked for it there too, so both
forms are covered here rather than in two files that would drift apart.

POL Abstract is GDL's own DocType, so its level-1 rows live in its JSON. Vehicle
Log is ERPNext's, so its rows go through setup/fleet_permissions.py. Different
mechanism, same decision - which is the reason to test them side by side.

Permlevel 1 is what hides them. The danger of permlevel is never the hiding -
it is the two things either side of it:

  * it hides the fields from EVERY role without a level-1 row, including
    standard ERPNext roles that have nothing to do with this change, and
  * a user who cannot see a field can still save the document, so the question
    is whether their save carries the values they never saw.

Both are tested here, because both have bitten this app before.
"""

import contextlib

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
from gdl_fleet_extension.tests.test_vehicle_log_extension import get_employee

DIMENSIONS = ("site", "department", "cost_center", "project", "task")
LAYOUT = ("gdl_dimension_section", "gdl_dimension_cb")


@contextlib.contextmanager
def acting_as(role):
	email = f"gdl-vlog-{role.lower().replace(' ', '-')}@example.com"
	if not frappe.db.exists("User", email):
		user = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": role,
			"user_type": "System User", "send_welcome_email": 0, "enabled": 1,
		})
		user.insert(ignore_permissions=True)
		user.add_roles(role)
	frappe.set_user(email)
	try:
		yield
	finally:
		frappe.set_user("Administrator")


def levels(ptype="read"):
	return frappe.new_doc("Vehicle Log").get_permlevel_access(ptype)


class TestTheDriverDoesNotSeeThem(IntegrationTestCase):
	def test_every_dimension_sits_above_level_zero(self):
		meta = frappe.get_meta("Vehicle Log")
		for fieldname in DIMENSIONS + LAYOUT:
			field = meta.get_field(fieldname)
			self.assertIsNotNone(field, f"{fieldname} is missing from Vehicle Log")
			self.assertEqual(field.permlevel, 1, f"{fieldname} is still at level 0")

	def test_the_section_heading_goes_with_them(self):
		"""Hiding the five fields and leaving the heading would leave an empty
		'Site and Accounting Dimensions' band on the driver's form."""
		meta = frappe.get_meta("Vehicle Log")
		for fieldname in LAYOUT:
			self.assertEqual(meta.get_field(fieldname).permlevel, 1)

	def test_a_driver_reaches_level_zero_only(self):
		with acting_as("Fleet Driver"):
			self.assertEqual(levels("read"), [0])
			self.assertEqual(levels("write"), [0])

	def test_a_driver_can_still_record_the_journey(self):
		"""The point of the change is the five boxes, not the driver's job."""
		meta = frappe.get_meta("Vehicle Log")
		for fieldname in ("date", "odometer", "license_plate"):
			field = meta.get_field(fieldname)
			if field:
				self.assertEqual(field.permlevel, 0,
				                 f"{fieldname} was raised out of the driver's reach")


class TestNobodyElseLostThem(IntegrationTestCase):
	"""Raising a permlevel takes the field from every role without a level-1
	row. These four had it at level 0 and must still have it."""

	KEEPS_READ = ("Fleet Administrator", "Fleet Manager",
	              "Fleet Approver", "Fleet Maintenance User")
	KEEPS_WRITE = ("Fleet Administrator", "Fleet Manager")

	def test_they_can_still_see_the_dimensions(self):
		for role in self.KEEPS_READ:
			with acting_as(role):
				self.assertIn(1, levels("read"), f"{role} lost sight of the dimensions")

	def test_the_two_who_filed_them_can_still_write_them(self):
		for role in self.KEEPS_WRITE:
			with acting_as(role):
				self.assertIn(1, levels("write"), f"{role} can no longer file a journey")

	def test_fleet_manager_is_covered_although_it_is_not_gdls_role(self):
		"""Fleet Manager ships with ERPNext. It had write on Vehicle Log before
		any of this, and a permlevel change is no reason to take it away."""
		row = frappe.db.get_value(
			"Custom DocPerm",
			{"parent": "Vehicle Log", "role": "Fleet Manager", "permlevel": 1},
			["read", "write"], as_dict=True)
		self.assertTrue(row, "Fleet Manager has no level-1 row and silently lost access")
		self.assertTrue(row.read and row.write)


class TestADriversSaveDoesNotWipeThem(IntegrationTestCase):
	"""The failure mode that matters.

	A user who cannot see a field can still save the document. If the save
	posts empty values for the fields they never saw, every cost centre finance
	set would be cleared by the next driver who touched the log.
	"""

	def setUp(self):
		self.employee = get_employee()
		if not self.employee:
			self.skipTest("no Employee on this site")
		self.vehicle = new_vehicle(last_odometer=10000)
		self.vehicle.insert()
		self.location = frappe.get_all("Location", filters={"is_group": 0},
		                               limit=1, pluck="name")

	def make_log(self):
		doc = frappe.get_doc({
			"doctype": "Vehicle Log",
			"license_plate": self.vehicle.name,
			"employee": self.employee,
			"date": nowdate(),
			"odometer": 10200,
			"usage_type": "Official",
			"place_to_travel": "Local",
			"site": self.location[0] if self.location else None,
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc

	def test_the_value_survives_a_drivers_save(self):
		if not self.location:
			self.skipTest("no Location on this site to file the journey against")

		log = self.make_log()
		self.assertEqual(log.site, self.location[0])

		with acting_as("Fleet Driver"):
			driver_copy = frappe.get_doc("Vehicle Log", log.name)
			driver_copy.odometer = 10400
			driver_copy.save()

		self.assertEqual(
			frappe.db.get_value("Vehicle Log", log.name, "site"), self.location[0],
			"a driver's save cleared the site finance had set",
		)
		self.assertEqual(frappe.db.get_value("Vehicle Log", log.name, "odometer"), 10400,
		                 "the driver's own change did not stick")

	def test_a_driver_cannot_set_one_by_sending_it_anyway(self):
		"""Hidden on the form is not the same as refused by the server."""
		if not self.location:
			self.skipTest("no Location on this site")

		log = self.make_log()
		with acting_as("Fleet Driver"):
			driver_copy = frappe.get_doc("Vehicle Log", log.name)
			driver_copy.cost_center = "Nonexistent Cost Centre"
			driver_copy.save()

		self.assertFalse(
			frappe.db.get_value("Vehicle Log", log.name, "cost_center"),
			"a driver wrote a field they cannot see",
		)


# ---------------------------------------------------------------------------
# The same section, on POL Abstract
# ---------------------------------------------------------------------------
POL_DIMENSIONS = ("site", "department", "cost_center", "project")
POL_LAYOUT = ("sec_dimensions", "col_dim_1")


def pol_levels(ptype="read"):
	return frappe.new_doc("POL Abstract").get_permlevel_access(ptype)


class TestThePOLDimensionsAreAlsoAboveTheDriver(IntegrationTestCase):
	def test_every_dimension_sits_above_level_zero(self):
		meta = frappe.get_meta("POL Abstract")
		for fieldname in POL_DIMENSIONS + POL_LAYOUT:
			field = meta.get_field(fieldname)
			self.assertIsNotNone(field, f"{fieldname} is missing from POL Abstract")
			self.assertEqual(field.permlevel, 1, f"{fieldname} is still at level 0")

	def test_a_driver_reaches_level_zero_only(self):
		with acting_as("Fleet Driver"):
			self.assertEqual(pol_levels("read"), [0])

	def test_the_driver_still_fills_in_the_abstract_itself(self):
		"""The fuel is the driver's job. Only the accounting filing is not."""
		meta = frappe.get_meta("POL Abstract")
		for fieldname in ("vehicle", "abstract_date", "opening_km", "closing_km",
		                  "entries"):
			field = meta.get_field(fieldname)
			if field:
				self.assertEqual(field.permlevel, 0,
				                 f"{fieldname} was raised out of the driver's reach")

	def test_who_signs_it_stays_visible_to_the_driver(self):
		"""Accountability was deliberately left alone - a driver submitting an
		abstract should see who approves it."""
		meta = frappe.get_meta("POL Abstract")
		for fieldname in ("submitted_by_designation", "approved_by_designation"):
			self.assertEqual(meta.get_field(fieldname).permlevel, 0,
			                 f"{fieldname} was hidden from the driver by accident")

	def test_nobody_else_lost_them(self):
		for role in ("Fleet Administrator", "Fleet HR Approver",
		             "Fleet Manager", "Fleet User"):
			with acting_as(role):
				self.assertIn(1, pol_levels("read"), f"{role} lost sight of the dimensions")

	def test_the_two_who_file_them_can_still_write_them(self):
		for role in ("Fleet Administrator", "Fleet HR Approver"):
			with acting_as(role):
				self.assertIn(1, pol_levels("write"), f"{role} can no longer file an abstract")
