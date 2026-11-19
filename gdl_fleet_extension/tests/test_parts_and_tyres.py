# Copyright (c) 2026, GDL and contributors
"""
Spare-part and tyre issuance (final document GAP item 4) and the
20,000 km +/-20% tyre performance target (Tire Mileage).
"""

from decimal import Decimal

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, nowdate

from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
from gdl_fleet_extension.utils.tyre import (
	ABOVE,
	BELOW,
	IN_SERVICE,
	WITHIN,
	classify_tyre,
	get_tyre_target,
	get_tyre_tolerance,
	tyre_bounds,
	tyre_deviation_percent,
)

TARGET, TOL = 20000, Decimal("20")


def make_item(code, serialised=False, is_tyre=False):
	if frappe.db.exists("Item", code):
		return code
	doc = frappe.get_doc({
		"doctype": "Item", "item_code": code, "item_name": code,
		"item_group": "All Item Groups", "stock_uom": "Nos",
		"is_stock_item": 1, "has_serial_no": 1 if serialised else 0,
	})
	if serialised:
		doc.serial_no_series = f"{code}-.#####"
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc.name


class TestTyreTarget(IntegrationTestCase):
	def test_band_is_target_plus_minus_tolerance(self):
		low, high = tyre_bounds(TARGET, TOL)
		self.assertEqual(low, Decimal("16000"))
		self.assertEqual(high, Decimal("24000"))

	def test_on_target(self):
		self.assertEqual(classify_tyre(20000, TARGET, TOL), WITHIN)

	def test_boundaries_are_inclusive(self):
		self.assertEqual(classify_tyre(16000, TARGET, TOL), WITHIN)
		self.assertEqual(classify_tyre(24000, TARGET, TOL), WITHIN)

	def test_just_outside_the_band(self):
		self.assertEqual(classify_tyre(15999, TARGET, TOL), BELOW)
		self.assertEqual(classify_tyre(24001, TARGET, TOL), ABOVE)

	def test_not_yet_removed_is_in_service(self):
		self.assertEqual(classify_tyre(None, TARGET, TOL), IN_SERVICE)

	def test_deviation_percent(self):
		self.assertEqual(tyre_deviation_percent(10000, TARGET), Decimal("-50"))
		self.assertEqual(tyre_deviation_percent(30000, TARGET), Decimal("50"))

	def test_target_and_tolerance_are_configuration(self):
		self.assertEqual(get_tyre_target(), 20000)
		self.assertEqual(get_tyre_tolerance(), Decimal("20"))


class TestFleetPartIssue(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(last_odometer=50000)
		self.vehicle.insert()
		self.part = make_item("GDL-TEST-PART-01")
		self.tyre = make_item("GDL-TEST-TYRE-01")

	def make_issue(self, items, submit=False, odometer=50000, **kwargs):
		values = {
			"doctype": "Fleet Part Issue", "vehicle": self.vehicle.name,
			"issue_date": nowdate(), "odometer": odometer,
			"purpose": "Routine Replacement", "items": items,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert()
		if submit:
			doc.submit()
		return doc

	# --- validation -----------------------------------------------------
	def test_issue_needs_at_least_one_item(self):
		self.assertRaises(frappe.ValidationError, self.make_issue, [])

	def test_zero_qty_is_rejected(self):
		self.assertRaises(frappe.ValidationError, self.make_issue,
		                  [{"item_code": self.part, "qty": 0, "rate": 100}])

	def test_amount_is_calculated(self):
		doc = self.make_issue([{"item_code": self.part, "qty": 3, "rate": 250}])
		self.assertEqual(flt(doc.items[0].amount), 750)
		self.assertEqual(flt(doc.total_amount), 750)
		self.assertEqual(flt(doc.total_qty), 3)

	def test_a_tyre_must_be_issued_one_per_row(self):
		"""Each tyre is tracked to the kilometres it achieves."""
		self.assertRaises(frappe.ValidationError, self.make_issue,
		                  [{"item_code": self.tyre, "qty": 4, "rate": 9000,
		                    "is_tyre": 1, "tyre_position": "Front Left"}])

	def test_a_tyre_needs_a_position(self):
		self.assertRaises(frappe.ValidationError, self.make_issue,
		                  [{"item_code": self.tyre, "qty": 1, "rate": 9000, "is_tyre": 1}])

	def test_duplicate_serial_on_one_issue_is_rejected(self):
		self.assertRaises(frappe.ValidationError, self.make_issue, [
			{"item_code": self.part, "qty": 1, "rate": 10, "serial_no": "SN-DUP"},
			{"item_code": self.part, "qty": 1, "rate": 10, "serial_no": "SN-DUP"},
		])

	def test_negative_odometer_is_rejected(self):
		self.assertRaises(frappe.ValidationError, self.make_issue,
		                  [{"item_code": self.part, "qty": 1, "rate": 10}], odometer=-5)

	# --- tyre lifecycle --------------------------------------------------
	def test_submitting_creates_a_tyre_record(self):
		doc = self.make_issue([{"item_code": self.tyre, "qty": 1, "rate": 9000,
		                        "is_tyre": 1, "tyre_position": "Front Left",
		                        "serial_no": f"TY-{frappe.generate_hash(length=6)}"}],
		                      submit=True)
		tyres = frappe.get_all("Vehicle Tyre", filters={"part_issue": doc.name},
		                       fields=["name", "status", "fitted_odometer", "tyre_position"])
		self.assertEqual(len(tyres), 1)
		self.assertEqual(tyres[0].status, "Fitted")
		self.assertEqual(tyres[0].fitted_odometer, 50000)
		self.assertEqual(tyres[0].tyre_position, "Front Left")

	def test_a_plain_part_creates_no_tyre_record(self):
		doc = self.make_issue([{"item_code": self.part, "qty": 2, "rate": 100}], submit=True)
		self.assertEqual(frappe.db.count("Vehicle Tyre", {"part_issue": doc.name}), 0)

	def test_same_tyre_cannot_be_fitted_twice(self):
		serial = f"TY-{frappe.generate_hash(length=6)}"
		row = {"item_code": self.tyre, "qty": 1, "rate": 9000, "is_tyre": 1,
		       "tyre_position": "Front Left", "serial_no": serial}
		self.make_issue([row], submit=True)
		self.assertRaises(frappe.ValidationError, self.make_issue, [dict(row)])

	def test_cancelling_removes_the_tyre_record(self):
		doc = self.make_issue([{"item_code": self.tyre, "qty": 1, "rate": 9000,
		                        "is_tyre": 1, "tyre_position": "Rear Left",
		                        "serial_no": f"TY-{frappe.generate_hash(length=6)}"}],
		                      submit=True)
		self.assertEqual(frappe.db.count("Vehicle Tyre", {"part_issue": doc.name}), 1)
		doc.cancel()
		self.assertEqual(frappe.db.count("Vehicle Tyre", {"part_issue": doc.name}), 0)

	def test_status_follows_docstatus(self):
		doc = self.make_issue([{"item_code": self.part, "qty": 1, "rate": 10}])
		self.assertEqual(doc.status, "Draft")
		doc.submit()
		self.assertEqual(frappe.db.get_value("Fleet Part Issue", doc.name, "status"), "Issued")

	def test_the_module_keeps_no_stock_of_its_own(self):
		"""Quantities live in ERPNext stock, never in a parallel fleet ledger."""
		for name in ("Fleet Stock", "Fleet Part Balance", "Vehicle Stock"):
			self.assertFalse(frappe.db.exists("DocType", name))


class TestVehicleTyreLifecycle(IntegrationTestCase):
	def setUp(self):
		self.vehicle = new_vehicle(last_odometer=50000)
		self.vehicle.insert()
		self.item = make_item("GDL-TEST-TYRE-02")

	def make_tyre(self, fitted=50000, removed=None, **kwargs):
		values = {
			"doctype": "Vehicle Tyre", "vehicle": self.vehicle.name,
			"item_code": self.item, "tyre_position": "Front Left",
			"fitted_date": add_days(nowdate(), -200), "fitted_odometer": fitted,
			"serial_no": f"TY-{frappe.generate_hash(length=6)}",
		}
		if removed is not None:
			values["removed_odometer"] = removed
			values["removed_date"] = nowdate()
			values["removal_reason"] = "Worn Out"
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc

	def test_in_service_tyre_has_no_km_achieved(self):
		t = self.make_tyre()
		self.assertIsNone(t.km_achieved)
		self.assertEqual(t.performance, "In Service")

	def test_km_achieved_on_removal(self):
		t = self.make_tyre(fitted=50000, removed=70000)
		self.assertEqual(t.km_achieved, 20000)
		self.assertEqual(t.performance, "Within Tolerance")
		self.assertEqual(t.status, "Removed")

	def test_tyre_that_fell_short(self):
		t = self.make_tyre(fitted=50000, removed=61000)   # 11,000 km
		self.assertEqual(t.km_achieved, 11000)
		self.assertEqual(t.performance, "Below Tolerance")

	def test_tyre_that_ran_beyond_the_band(self):
		t = self.make_tyre(fitted=50000, removed=80000)   # 30,000 km
		self.assertEqual(t.performance, "Above Tolerance")

	def test_removed_odometer_cannot_precede_fitted(self):
		self.assertRaises(frappe.ValidationError, self.make_tyre, 50000, 40000)

	def test_target_is_stamped_from_settings(self):
		self.assertEqual(self.make_tyre().target_km, 20000)

	def test_report_runs_and_explains_the_band(self):
		self.make_tyre(fitted=50000, removed=70000)
		result = frappe.get_attr(
			"gdl_fleet_extension.gdl_fleet.report.tyre_mileage_report.tyre_mileage_report.execute"
		)({"vehicle": self.vehicle.name})
		self.assertTrue(result[0])
		self.assertIn("20,000 km", result[2])
		rows = [r for r in result[1] if r["vehicle"] == self.vehicle.name]
		self.assertTrue(rows)
		self.assertEqual(rows[0]["km_so_far"], 20000)


class TestPartIssueStockSetup(IntegrationTestCase):
	"""The setup a Material Issue needs, checked on the fleet form.

	GDL pressed Submit on a part issue and got ERPNext's own refusal:
	"Please enter Difference Account or set default Stock Adjustment Account
	for company GreenDigital Limited" - a message naming neither this document
	nor anything visible on it. Their source warehouse was also a group, and
	the tyre had no stock anywhere, so two more refusals waited behind it.

	These checks run on validate, so all three are answered while the record
	is still a draft.
	"""

	def setUp(self):
		from gdl_fleet_extension.tests.test_vehicle_extension import get_test_company
		self.company = get_test_company()
		self.vehicle = new_vehicle(last_odometer=50000, company=self.company)
		self.vehicle.insert()
		self.part = make_item("GDL-TEST-STOCKSETUP-PART")

	def _issue(self, **kwargs):
		values = {
			"doctype": "Fleet Part Issue", "vehicle": self.vehicle.name,
			"issue_date": nowdate(), "odometer": 50000,
			"purpose": "Routine Replacement",
			"items": [{"item_code": self.part, "qty": 1, "rate": 100}],
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		return doc

	def _warehouse(self, name, is_group=0, parent=None):
		abbr = frappe.get_cached_value("Company", self.company, "abbr")
		full = f"{name} - {abbr}"
		if frappe.db.exists("Warehouse", full):
			return full
		doc = frappe.get_doc({
			"doctype": "Warehouse", "warehouse_name": name,
			"company": self.company, "is_group": is_group,
		})
		if parent:
			doc.parent_warehouse = parent
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc.name

	def test_a_group_warehouse_is_refused_with_a_clear_message(self):
		group = self._warehouse("GDL Test Group WH", is_group=1)
		with self.assertRaises(frappe.ValidationError) as cm:
			self._issue(source_warehouse=group).insert()
		self.assertIn("group warehouse", str(cm.exception).lower())

	def test_a_missing_stock_adjustment_account_is_refused_by_name(self):
		warehouse = self._warehouse("GDL Test Setup WH")
		original = frappe.db.get_value("Company", self.company, "stock_adjustment_account")
		perpetual = frappe.db.get_value("Company", self.company, "enable_perpetual_inventory")
		try:
			frappe.db.set_value("Company", self.company, "enable_perpetual_inventory", 1)
			frappe.db.set_value("Company", self.company, "stock_adjustment_account", None)
			frappe.clear_cache()
			with self.assertRaises(frappe.ValidationError) as cm:
				self._issue(source_warehouse=warehouse).insert()
			self.assertIn("Stock Adjustment Account", str(cm.exception))
		finally:
			frappe.db.set_value("Company", self.company, "stock_adjustment_account", original)
			frappe.db.set_value("Company", self.company, "enable_perpetual_inventory", perpetual)
			frappe.clear_cache()

	def test_a_properly_set_up_issue_saves(self):
		"""The guard must not stand in the way of a correct record."""
		warehouse = self._warehouse("GDL Test Setup WH")
		self.assertTrue(frappe.db.get_value("Company", self.company, "stock_adjustment_account"),
		                "fixture company has no Stock Adjustment Account - test proves nothing")
		doc = self._issue(source_warehouse=warehouse)
		doc.insert()
		self.assertEqual(doc.docstatus, 0)

	def test_short_stock_warns_rather_than_refusing(self):
		"""The parts may arrive before anyone submits, so this must not block."""
		warehouse = self._warehouse("GDL Test Setup WH")
		doc = self._issue(source_warehouse=warehouse)
		doc.insert()          # no stock received for this item at all
		self.assertEqual(doc.docstatus, 0)

	def test_submitting_without_stock_is_refused_by_name(self):
		"""A warning in the draft becomes a refusal at submit. GDL got here and
		met ERPNext's "Valuation Rate Missing" instead, whose first suggestion
		would have issued the tyre at no value."""
		warehouse = self._warehouse("GDL Test Setup WH")
		doc = self._issue(source_warehouse=warehouse)
		doc.insert()
		with self.assertRaises(frappe.ValidationError) as cm:
			doc.submit()
		message = str(cm.exception)
		self.assertIn("being issued", message)
		self.assertIn("Material Receipt", message)
		self.assertEqual(frappe.db.get_value("Fleet Part Issue", doc.name, "docstatus"), 0)

	def test_stock_received_at_no_rate_is_refused(self):
		"""In stock, but valued at nothing - ERPNext cannot post the issue."""
		warehouse = self._warehouse("GDL Test Setup WH")
		item = make_item("GDL-TEST-NORATE-PART")
		frappe.db.set_value("Item", item, "valuation_rate", 0)
		bin_name = frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse})
		if not bin_name:
			b = frappe.get_doc({"doctype": "Bin", "item_code": item, "warehouse": warehouse})
			b.flags.ignore_permissions = True
			b.insert()
			bin_name = b.name
		frappe.db.set_value("Bin", bin_name, {"actual_qty": 10, "valuation_rate": 0})
		doc = self._issue(source_warehouse=warehouse,
		                  items=[{"item_code": item, "qty": 1, "rate": 100}])
		doc.insert()
		with self.assertRaises(frappe.ValidationError) as cm:
			doc.submit()
		self.assertIn("no valuation", str(cm.exception))

	def _receive(self, item_code, qty, warehouse, rate=500):
		"""A Material Receipt in THIS test's company.

		fleet_fixtures.receive_stock() is hard-wired to its own company, while
		get_test_company() returns whichever company happens to be first on the
		site - they are not the same one, and a warehouse from one company in a
		stock entry for another is refused by ERPNext.
		"""
		entry = frappe.get_doc({
			"doctype": "Stock Entry", "stock_entry_type": "Material Receipt",
			"purpose": "Material Receipt", "company": self.company,
			"items": [{"item_code": item_code, "qty": qty,
			           "t_warehouse": warehouse, "basic_rate": rate}],
		})
		entry.flags.ignore_permissions = True
		entry.insert()
		entry.submit()
		return entry

	def test_a_stocked_part_still_issues(self):
		"""The guard must not stand in the way of a real issue."""
		warehouse = self._warehouse("GDL Test Setup WH")
		item = make_item("GDL-TEST-INSTOCK-PART")
		self._receive(item, 5, warehouse, rate=500)
		doc = self._issue(source_warehouse=warehouse,
		                  items=[{"item_code": item, "qty": 1, "rate": 500}])
		doc.insert()
		doc.submit()
		self.assertEqual(doc.docstatus, 1)
		self.assertTrue(doc.stock_entry, "no Stock Entry was raised")
		self.assertEqual(frappe.db.get_value("Stock Entry", doc.stock_entry, "docstatus"), 1)


class TestVehicleTyreIsOffTheMenu(IntegrationTestCase):
	"""GDL circled Vehicle Tyre in the breadcrumb: "hide this".

	The LINK ROW is removed - not a permission, and not the `hidden` tick.
	That tick does nothing: desk/desktop.py get_links() filters workspace
	entries on is_item_allowed() alone and never reads it. And permission is
	the wrong lever here, because Fleet Part Issue writes these records and
	both tyre reports read them.
	"""

	def workspace(self):
		return frappe.get_doc("Workspace", "GDL Fleet")

	def links(self):
		return [l.link_to for l in self.workspace().links if l.type == "Link"]

	def test_vehicle_tyre_has_no_menu_entry(self):
		self.assertNotIn("Vehicle Tyre", self.links())

	def test_the_tyre_reports_keep_theirs(self):
		"""The tracking the document asks for is still reachable."""
		labels = [l.label for l in self.workspace().links]
		for report in ("Tyre Mileage Report", "Tyre Cost Analysis"):
			self.assertIn(report, labels, f"{report} lost its menu entry too")

	def test_the_doctype_and_its_records_are_untouched(self):
		"""Hidden from a menu, never removed."""
		self.assertTrue(frappe.db.exists("DocType", "Vehicle Tyre"))

	def test_permission_was_not_the_lever(self):
		"""Taking the right away would break Fleet Part Issue, which creates
		these records, and both reports, which read them."""
		roles = {p.role for p in frappe.get_meta("Vehicle Tyre").permissions if p.read}
		self.assertTrue(roles, "nobody can read Vehicle Tyre any more")
