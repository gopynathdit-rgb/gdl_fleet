# Copyright (c) 2026, GDL and contributors
"""The reading taken as the vehicle leaves.

The printed Vehicle Movement Order asks for "Time and km. reading on
departure". The time the order knows; the reading it did not, so the printout
carried a ruled blank for the gate to write in. GDL asked for the field.

It is deliberately NOT defaulted from the vehicle. An order is raised before
the journey, so a figure filled in then would be a guess printed as a fact.
Vehicle Log defaults its start reading because that genuinely is the previous
trip's end - this is an observation, and at the time the order is raised there
is nothing yet to observe.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from gdl_fleet_extension.tests.test_vehicle_extension import TEST_TYPE, new_vehicle


def new_order(vehicle, driver, **kwargs):
	values = {
		"doctype": "Movement Order",
		"vehicle": vehicle,
		"driver": driver,
		"departure_datetime": f"{add_days(nowdate(), 2)} 08:00:00",
		"expected_return": f"{add_days(nowdate(), 2)} 17:00:00",
		"purpose": "Site inspection",
		"destination": "Jamjee Farm",
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	return doc


class TestDepartureOdometer(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(vehicle_type=TEST_TYPE, last_odometer=20000)
		self.vehicle.insert()
		self.driver = frappe.get_doc({
			"doctype": "Driver", "full_name": "Gate Test Driver", "status": "Active",
			"license_number": frappe.generate_hash(length=8),
		})
		self.driver.flags.ignore_permissions = True
		self.driver.insert()

	def order(self, **kwargs):
		return new_order(self.vehicle.name, self.driver.name, **kwargs)

	def test_the_field_exists_and_survives_approval(self):
		"""The gate reads it after the order is approved, so it has to be
		editable on a submitted document - like the vehicle and driver."""
		field = frappe.get_meta("Movement Order").get_field("departure_odometer")
		self.assertIsNotNone(field)
		self.assertTrue(field.allow_on_submit,
		                "the reading is taken after approval; it must be editable then")

	def test_it_is_not_required(self):
		"""An order is raised before the journey. Requiring it would mean
		inventing a number to get the order out."""
		self.assertFalse(frappe.get_meta("Movement Order")
		                 .get_field("departure_odometer").reqd)

	def test_an_order_saves_without_one(self):
		doc = self.order()
		doc.insert()
		self.assertFalse(doc.departure_odometer)

	def test_it_is_not_defaulted_from_the_vehicle(self):
		"""The point. A guess printed as a fact is worse than a blank line."""
		doc = self.order()
		doc.insert()
		self.assertFalse(doc.departure_odometer,
		                 "the reading was filled in before anyone had read it")

	def test_a_sensible_reading_is_accepted(self):
		doc = self.order(departure_odometer=20500)
		doc.insert()
		self.assertEqual(doc.departure_odometer, 20500)

	def test_the_vehicle_s_own_reading_is_accepted(self):
		"""Leaving straight after the last trip is the normal case."""
		doc = self.order(departure_odometer=20000)
		doc.insert()
		self.assertEqual(doc.departure_odometer, 20000)

	def test_a_reading_below_the_vehicle_s_last_is_refused(self):
		"""An odometer does not run backwards - that is a typo or the wrong
		vehicle, and both are worth stopping."""
		doc = self.order(departure_odometer=19999)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_a_negative_reading_is_refused(self):
		doc = self.order(departure_odometer=-5)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_the_check_still_runs_after_approval(self):
		"""Where it actually matters: the gate types the figure into an order
		that is already submitted."""
		doc = self.order()
		doc.insert()
		doc.submit()

		doc.departure_odometer = 19000
		self.assertRaises(frappe.ValidationError, doc.save)

		doc.reload()
		doc.departure_odometer = 20800
		doc.save()
		self.assertEqual(doc.departure_odometer, 20800)


class TestItReachesThePrintedOrder(IntegrationTestCase):
	"""Item 7 of the paper form, both ways round."""

	def rendered(self, doc):
		from frappe.www.printview import get_rendered_template
		return get_rendered_template(
			doc, print_format=frappe.get_doc("Print Format", "Vehicle Movement Order"))

	def item_seven(self, doc):
		"""Just the one row, so an assertion cannot pass on text from elsewhere
		in the page - which is exactly how the first version of the test below
		passed: it matched the word "ruled" in a CSS comment."""
		import re
		match = re.search(r"7\. Time and km\. reading on departure.*?</tr>",
		                  self.rendered(doc), re.S)
		self.assertIsNotNone(match, "item 7 is not on the printout at all")
		return re.sub(r"<[^>]+>", " ", match.group(0))

	def setUp(self):
		self.vehicle = new_vehicle(vehicle_type=TEST_TYPE, last_odometer=20000)
		self.vehicle.insert()
		self.driver = frappe.get_doc({
			"doctype": "Driver", "full_name": "Print Test Driver", "status": "Active",
			"license_number": frappe.generate_hash(length=8),
		})
		self.driver.flags.ignore_permissions = True
		self.driver.insert()

	def test_a_reading_is_printed_when_there_is_one(self):
		doc = new_order(self.vehicle.name, self.driver.name, departure_odometer=20500)
		doc.insert()
		self.assertIn("20,500 km", self.item_seven(doc))

	def test_no_figure_is_printed_before_the_reading_is_taken(self):
		"""The sheet is normally printed before the vehicle moves, and the gate
		writes the reading on the paper. Printing a "km" with nothing against
		it, or worse a stale figure, would be inventing a reading."""
		doc = new_order(self.vehicle.name, self.driver.name)
		doc.insert()
		row = self.item_seven(doc)
		self.assertIn("Time and km. reading on departure", row)
		self.assertNotIn("km", row.split(":", 1)[1],
		                 "a kilometre figure was printed before anyone read one")

	def test_items_9_and_10_are_not_on_the_printout(self):
		"""GDL asked for both to be dropped - they are filled in after the
		journey, on a form handed over before it."""
		doc = new_order(self.vehicle.name, self.driver.name)
		doc.insert()
		html = self.rendered(doc)
		self.assertNotIn("Return to parking place", html)
		self.assertNotIn("officer utilizing", html)

	def test_the_eight_items_the_form_asks_for_are_all_there(self):
		doc = new_order(self.vehicle.name, self.driver.name)
		doc.insert()
		html = self.rendered(doc)
		for label in ("Name of the office", "Pool Vehicle No.",
		              "Name of the Driver", "Place/s to visit",
		              "Purpose of Movement", "Officer/s to carry",
		              "Time and km. reading on departure",
		              "Validity of movement order"):
			self.assertIn(label, html, f"item missing from the printout: {label}")


class TestThePrintFormatIsActuallyReached(IntegrationTestCase):
	"""A format nobody is shown is a format that does not exist.

	The Vehicle Movement Order format was built, registered and rendering
	correctly server-side - and Print still produced frappe's generic
	field-by-field layout, because default_print_format was never set on the
	DocType. POL Abstract had it set, which is why that one worked and this one
	did not, and why the difference went unnoticed.

	Every test here passed while that was broken. This is the one that would
	not have.
	"""

	EXPECTED = {
		"Movement Order": "Vehicle Movement Order",
		"POL Abstract": "POL Abstract",
	}

	def test_each_doctype_opens_on_its_own_format(self):
		for doctype, print_format in self.EXPECTED.items():
			self.assertEqual(
				frappe.get_meta(doctype).default_print_format, print_format,
				f"{doctype} does not open on {print_format} - Print will show the "
				f"generic layout instead, and nobody will find the real one",
			)

	def test_the_format_exists_and_is_not_disabled(self):
		for doctype, print_format in self.EXPECTED.items():
			row = frappe.db.get_value("Print Format", print_format,
			                          ["doc_type", "disabled"], as_dict=True)
			self.assertTrue(row, f"{print_format} is not installed")
			self.assertEqual(row.doc_type, doctype)
			self.assertFalse(row.disabled, f"{print_format} is disabled")
