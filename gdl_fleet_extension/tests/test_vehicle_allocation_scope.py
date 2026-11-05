# Copyright (c) 2026, GDL and contributors
"""What the Assigned Vehicle dropdown offers.

Three things GDL asked for on the request form:

  1. Only vehicles free for THIS window. The field used to filter on
     vehicle_status alone, so a vehicle already booked was offered and the
     clash only surfaced when the save was refused. Check Availability knew
     better; the field beside it did not.
  2. The availability list assigns on click instead of being read and retyped.
     That is the form's job and is covered by the client script.
  3. A location's people are offered that location's fleet.

The head office MTO is not scoped. "Final MTO will be at head office" is the
whole point of that seat, and confining it to head office vehicles would take
away the authority it exists to hold.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from gdl_fleet_extension.gdl_fleet.doctype.movement_order_request.movement_order_request import (
	assignable_vehicle_query,
	assignable_vehicles,
	get_available_vehicles,
)
from gdl_fleet_extension.utils.location_officers import sites_for_user
from gdl_fleet_extension.tests.test_movement_order_request import (
	approved_booking,
	new_booking,
)
from gdl_fleet_extension.tests.test_vehicle_extension import TEST_TYPE, new_vehicle


def offered(**filters):
	"""What the dropdown would show."""
	rows = assignable_vehicle_query("Vehicle", "", "name", 0, 50, filters)
	return {r[0] for r in rows}


class TestTheDropdownRespectsTheClock(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(vehicle_type=TEST_TYPE)
		self.vehicle.insert()
		self.window = {
			"from_datetime": f"{add_days(nowdate(), 3)} 08:00:00",
			"to_datetime": f"{add_days(nowdate(), 3)} 17:00:00",
			"vehicle_type": TEST_TYPE,
		}

	def test_a_free_vehicle_is_offered(self):
		self.assertIn(self.vehicle.name, offered(**self.window))

	def test_a_vehicle_booked_for_that_window_is_not_offered(self):
		"""The whole point. Before this it was offered and the save refused."""
		approved_booking(self.vehicle.name,
		                 required_date=add_days(nowdate(), 3),
		                 required_from_time="08:00:00",
		                 required_to_time="17:00:00")
		self.assertNotIn(self.vehicle.name, offered(**self.window),
		                 "a vehicle already booked for this window was offered")

	def test_it_agrees_with_check_availability(self):
		"""The dropdown and the button must never disagree - that disagreement
		was the bug."""
		approved_booking(self.vehicle.name,
		                 required_date=add_days(nowdate(), 3),
		                 required_from_time="08:00:00",
		                 required_to_time="17:00:00")
		from_button = {v["name"] for v in get_available_vehicles(
			self.window["from_datetime"], self.window["to_datetime"],
			vehicle_type=TEST_TYPE)}
		self.assertEqual(offered(**self.window), from_button)

	def test_a_booking_on_another_day_does_not_block_it(self):
		approved_booking(self.vehicle.name,
		                 required_date=add_days(nowdate(), 10),
		                 required_from_time="08:00:00",
		                 required_to_time="17:00:00")
		self.assertIn(self.vehicle.name, offered(**self.window))

	def test_the_request_being_edited_does_not_block_itself(self):
		booking = approved_booking(self.vehicle.name,
		                           required_date=add_days(nowdate(), 3),
		                           required_from_time="08:00:00",
		                           required_to_time="17:00:00")
		self.assertIn(self.vehicle.name,
		              offered(exclude=booking.name, **self.window),
		              "a request's own vehicle vanished from its own dropdown")

	def test_with_no_window_yet_it_still_offers_something(self):
		"""The schedule is filled in after the form opens. An empty dropdown
		with no explanation would read as a broken field."""
		self.assertIn(self.vehicle.name, offered(vehicle_type=TEST_TYPE))

	def test_an_unavailable_vehicle_is_never_offered(self):
		self.vehicle.db_set("vehicle_status", "Under Maintenance")
		self.assertNotIn(self.vehicle.name, offered(**self.window))
		self.assertNotIn(self.vehicle.name, offered(vehicle_type=TEST_TYPE))


class TestTheDropdownRespectsTheLocation(IntegrationTestCase):
	"""GDL: "if i am HO user i will see only HO vehicle only"."""

	def test_an_unmapped_user_is_not_restricted(self):
		"""Deliberate. A site list is a filter, not a security boundary, and
		returning nothing for everyone GDL has not mapped yet would empty the
		dropdown across the fleet on day one."""
		self.assertIsNone(sites_for_user("Administrator"))

	def test_a_location_mto_is_scoped_to_their_own_location(self):
		from gdl_fleet_extension.utils.location_officers import get_officers, enforcement_is_on
		if not enforcement_is_on():
			self.skipTest("location enforcement is off on this site")
		rows = [r for r in get_officers() if not r.is_head_office and r.mto and r.location]
		if not rows:
			self.skipTest("no location MTO configured on this site")

		row = rows[0]
		sites = sites_for_user(row.mto)
		self.assertIsNotNone(sites, f"{row.mto} was not scoped to any location")
		self.assertIn(row.location, sites)

	def test_the_head_office_mto_is_not_scoped(self):
		"""The final authority approves anywhere. Scoping it would remove the
		one thing that seat exists for."""
		from gdl_fleet_extension.utils.location_officers import (
			get_head_office_mto, enforcement_is_on)
		if not enforcement_is_on():
			self.skipTest("location enforcement is off on this site")
		head = get_head_office_mto()
		if not head:
			self.skipTest("no head office MTO configured on this site")
		self.assertIsNone(sites_for_user(head))

	def test_the_vehicle_list_follows_the_scope(self):
		"""The resolver and the list it is supposed to drive, together."""
		from gdl_fleet_extension.utils.location_officers import get_officers, enforcement_is_on
		if not enforcement_is_on():
			self.skipTest("location enforcement is off on this site")
		rows = [r for r in get_officers() if not r.is_head_office and r.mto and r.location]
		if not rows:
			self.skipTest("no location MTO configured on this site")

		mto = rows[0].mto
		frappe.set_user(mto)
		try:
			sites = set(sites_for_user())
			seen = {v.site for v in assignable_vehicles() if v.site}
			self.assertTrue(seen <= sites,
			                f"{mto} was offered vehicles outside {sites}: {seen - sites}")
		finally:
			frappe.set_user("Administrator")

	def test_a_group_location_reaches_the_depots_under_it(self):
		from gdl_fleet_extension.utils.location_officers import expand_sites
		group = frappe.get_all("Location", filters={"is_group": 1}, limit=1, pluck="name")
		if not group:
			self.skipTest("no group Location on this site")
		children = frappe.get_all(
			"Location", filters={"name": ("descendants of", group[0]), "is_group": 0},
			pluck="name")
		if not children:
			self.skipTest("the group Location has no leaf sites")
		self.assertTrue(set(children) <= set(expand_sites([group[0]])))
