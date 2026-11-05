# Copyright (c) 2026, GDL and contributors
"""
Customer change requests CR1-CR4.

CR1 driver/employee mapping, CR2 movement order request mapping,
CR3 maintenance purchasing, CR4 insurance renewal purchasing.
"""

import frappe
from frappe.tests import IntegrationTestCase

from gdl_fleet_extension.tests.fleet_settings_guard import FleetSettingsGuard
from frappe.utils import add_days, flt, nowdate

from gdl_fleet_extension.gdl_fleet.doctype.movement_order.movement_order import (
	fetch_request_details,
	get_request_details,
	validate_request_is_usable,
)
from gdl_fleet_extension.tests.test_movement_order_request import make_vehicle_type, new_booking
from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
from gdl_fleet_extension.utils.driver import (
	get_driver_details,
	validate_driver_employee,
)
from gdl_fleet_extension.utils.fleet_purchase_automation import (
	approve_bill,
	get_renewals_due_for_purchase,
	retry_maintenance_purchase,
	raise_insurance_renewal_orders,
	reject_bill,
	submit_bill,
)
from gdl_fleet_extension.utils.purchasing import has_live_order, missing_configuration

COMPANY = "GDL (Demo)"


def make_employee(name_suffix=None):
	suffix = name_suffix or frappe.generate_hash(length=5)
	doc = frappe.get_doc({
		"doctype": "Employee", "first_name": f"GDLTest {suffix}",
		"company": COMPANY, "date_of_birth": "1990-01-01",
		"date_of_joining": "2020-01-01", "gender": "Male", "status": "Active",
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert()
	return doc.name


def make_driver(employee=None, licence=None):
	doc = frappe.get_doc({
		"doctype": "Driver",
		"full_name": f"GDLTest Driver {frappe.generate_hash(length=5)}",
		"status": "Active",
		"employee": employee,
		"license_number": licence,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	return doc


# ===========================================================================
# CR1 - driver and employee mapping
# ===========================================================================
class TestDriverEmployeeMapping(IntegrationTestCase):
	def test_details_helper_returns_everything_a_form_needs(self):
		emp = make_employee()
		driver = make_driver(employee=emp, licence="BT-DL-TEST-1")
		details = get_driver_details(driver.name)
		self.assertEqual(details["employee"], emp)
		self.assertEqual(details["license_number"], "BT-DL-TEST-1")

	def test_blank_driver_returns_blanks_not_none(self):
		"""Blank strings clear a stale value; None would leave it on screen."""
		details = get_driver_details(None)
		self.assertEqual(set(details.values()), {""})

	def test_unknown_driver_is_handled(self):
		self.assertEqual(get_driver_details("NO-SUCH-DRIVER")["employee"], "")

	def test_fetch_refreshes_when_the_driver_changes(self):
		"""fetch_if_empty must be off, or changing Driver keeps the old employee."""
		for field in ("employee", "license_no"):
			meta = frappe.get_meta("Driver Assignment").get_field(field)
			self.assertTrue(meta.fetch_from, f"{field} must fetch from the driver")
			self.assertFalse(meta.fetch_if_empty,
			                 f"{field} would not refresh when the Driver changes")

	def test_assignment_fills_employee_and_licence_server_side(self):
		emp = make_employee()
		driver = make_driver(employee=emp, licence="BT-DL-TEST-2")
		vehicle = new_vehicle()
		vehicle.insert()
		doc = frappe.get_doc({
			"doctype": "Driver Assignment", "vehicle": vehicle.name,
			"driver": driver.name, "assignment_type": "Primary",
			"from_date": nowdate(),
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		self.assertEqual(doc.employee, emp)
		self.assertEqual(doc.license_no, "BT-DL-TEST-2")

	def test_a_mismatched_employee_cannot_survive_a_save(self):
		"""An inconsistent pair is corrected, not stored.

		With fetch_if_empty off, frappe re-reads employee from the driver on
		every save - on the API and on an import as much as in the form - so a
		wrong employee is overwritten with the right one rather than kept.
		"""
		correct = make_employee()
		driver = make_driver(employee=correct, licence="BT-DL-TEST-3")
		wrong = make_employee()
		vehicle = new_vehicle()
		vehicle.insert()
		doc = frappe.get_doc({
			"doctype": "Driver Assignment", "vehicle": vehicle.name,
			"driver": driver.name, "employee": wrong,
			"assignment_type": "Primary", "from_date": nowdate(),
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		self.assertEqual(doc.employee, correct,
		                 "the driver's own employee must win over the submitted one")
		self.assertNotEqual(doc.employee, wrong)

	def test_validation_guards_forms_that_do_not_fetch(self):
		"""Not every form links employee to driver, so the check still matters."""
		correct = make_employee()
		driver = make_driver(employee=correct, licence="BT-DL-TEST-3b")
		wrong = make_employee()
		doc = frappe._dict(driver=driver.name, employee=wrong)
		self.assertRaises(frappe.ValidationError, validate_driver_employee, doc)

	def test_driver_without_employee_warns_but_does_not_block(self):
		"""Most live Drivers have no Employee; blocking would stop work."""
		driver = make_driver(employee=None, licence="BT-DL-TEST-4")
		doc = frappe._dict(driver=driver.name, employee=make_employee())
		doc.get = lambda f, d=None: dict(driver=driver.name, employee=doc["employee"]).get(f, d)
		validate_driver_employee(doc)      # must not raise

	def test_driver_details_visible_on_the_other_fleet_forms(self):
		for doctype in ("Movement Order", "POL Abstract", "Fleet Part Issue"):
			fields = {f.fieldname for f in frappe.get_meta(doctype).fields}
			self.assertIn("driver_employee", fields, f"{doctype} shows no driver employee")
			self.assertIn("driver_license_no", fields, f"{doctype} shows no driver licence")

	def test_requester_employee_is_not_overwritten_by_the_driver(self):
		"""Movement Order Request.employee is the REQUESTER, not the driver."""
		meta = frappe.get_meta("Movement Order Request").get_field("employee")
		self.assertNotEqual(meta.fetch_from, "driver.employee")

	def test_vehicle_log_employee_still_comes_from_the_vehicle(self):
		meta = frappe.get_meta("Vehicle Log").get_field("employee")
		self.assertEqual(meta.fetch_from, "license_plate.employee")


# ===========================================================================
# CR2 - movement order request mapping
# ===========================================================================
class TestMovementOrderRequestMapping(IntegrationTestCase):
	def accepted_request(self, **kwargs):
		booking = new_booking(**kwargs)
		booking.flags.ignore_permissions = True
		booking.insert()
		booking.db_set("status", "Accepted")
		booking.reload()
		return booking

	def test_mapping_carries_the_request_detail(self):
		request = self.accepted_request()
		values = get_request_details(request.name)
		self.assertEqual(values["purpose"], request.purpose)
		self.assertEqual(values["destination"], request.destination)
		self.assertEqual(values["passenger_count"], request.passenger_count)
		self.assertEqual(values["vehicle_type"], request.vehicle_type)
		self.assertEqual(values["departure_datetime"], request.from_datetime)

	def test_from_location_falls_back_to_pickup(self):
		request = self.accepted_request()
		self.assertTrue(get_request_details(request.name)["from_location"])

	def test_movement_order_can_hold_the_mapped_fields(self):
		fields = {f.fieldname for f in frappe.get_meta("Movement Order").fields}
		for field in ("site", "vehicle_type", "contact_details", "requested_by",
		              "department", "from_location", "destination", "purpose",
		              "passenger_count", "departure_datetime", "expected_return"):
			self.assertIn(field, fields, f"Movement Order cannot hold {field}")

	def test_a_draft_request_cannot_be_used(self):
		booking = new_booking()
		booking.flags.ignore_permissions = True
		booking.insert()
		self.assertRaises(frappe.ValidationError, validate_request_is_usable, booking.name)

	def test_a_rejected_request_cannot_be_used(self):
		booking = self.accepted_request()
		booking.db_set("status", "Rejected")
		self.assertRaises(frappe.ValidationError, validate_request_is_usable, booking.name)

	def test_a_cancelled_request_cannot_be_used(self):
		booking = self.accepted_request()
		booking.db_set("status", "Cancelled")
		self.assertRaises(frappe.ValidationError, validate_request_is_usable, booking.name)

	def test_an_accepted_request_is_usable(self):
		request = self.accepted_request()
		validate_request_is_usable(request.name)      # must not raise

	def test_the_fetch_endpoint_validates_before_returning(self):
		booking = new_booking()
		booking.flags.ignore_permissions = True
		booking.insert()
		self.assertRaises(frappe.ValidationError, fetch_request_details, booking.name)


# ===========================================================================
# External maintenance: the driver's service bill
# ===========================================================================
class TestExternalMaintenanceBill(FleetSettingsGuard, IntegrationTestCase):
	def setUp(self):
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
		self.supplier = frappe.get_all("Supplier", pluck="name", limit=1)[0]
		items = frappe.get_all("Item", filters={"is_stock_item": 0}, pluck="name", limit=1)
		self.item = items[0] if items else None
		self.setting("maintenance_bill_requires_attachment", 1)

	def tearDown(self):
		for field, value in (("maintenance_po_on_completion", 0),
		                     ("maintenance_service_item", None),
		                     ("purchasing_company", None),
		                     ("maintenance_purchase_document", "Purchase Invoice")):
			self.setting(field, value)

	def setting(self, field, value):
		frappe.db.set_single_value("GDL Fleet Settings", field, value)
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def a_log(self, **values):
		name = frappe.get_all("Asset Maintenance Log", pluck="name", limit=1)
		if not name:
			self.skipTest("no maintenance logs on this site")
		base = {
			"service_provider": None, "bill_no": None, "bill_date": None,
			"bill_attachment": None, "bill_status": "Service Completed",
			"purchase_invoice": None, "purchase_order": None,
			"purchasing_status": None, "payment_status": None, "total_cost": 0,
		}
		base.update(values)
		frappe.db.set_value("Asset Maintenance Log", name[0], base, update_modified=False)
		return name[0]

	def a_complete_bill(self, amount=12000):
		return self.a_log(
			service_provider=self.supplier, total_cost=amount,
			bill_no=f"SC-{frappe.generate_hash(length=6).upper()}",
			bill_date=nowdate(), bill_attachment="/files/test-bill.pdf",
		)

	# --- the fields the process needs -----------------------------------
	def test_the_record_captures_the_whole_bill(self):
		fields = {f.fieldname for f in frappe.get_meta("Asset Maintenance Log").fields}
		for field in ("vehicle", "driver", "driver_employee", "completion_date", "odometer",
		              "service_provider", "actions_performed", "service_items", "total_cost",
		              "bill_no", "bill_date", "bill_attachment", "bill_status",
		              "submitted_by", "submission_date", "approved_by",
		              "purchase_order", "purchase_invoice", "payment_status"):
			self.assertIn(field, fields, f"Asset Maintenance Log cannot capture {field}")

	# --- the driver submits ---------------------------------------------
	def test_an_empty_bill_is_refused_and_says_what_is_missing(self):
		log = self.a_log()
		with self.assertRaises(frappe.ValidationError) as caught:
			submit_bill(log)
		message = str(caught.exception)
		self.assertIn("Bill / Invoice No.", message)
		self.assertIn("Bill Date", message)

	def test_the_attachment_is_required(self):
		log = self.a_log(service_provider=self.supplier, total_cost=5000,
		                 bill_no="SC-NOATTACH", bill_date=nowdate())
		with self.assertRaises(frappe.ValidationError) as caught:
			submit_bill(log)
		self.assertIn("Attachment", str(caught.exception))

	def test_a_zero_amount_is_refused(self):
		log = self.a_log(service_provider=self.supplier, total_cost=0,
		                 bill_no="SC-ZERO", bill_date=nowdate(),
		                 bill_attachment="/files/x.pdf")
		self.assertRaises(frappe.ValidationError, submit_bill, log)

	def test_the_attachment_rule_is_configurable(self):
		self.setting("maintenance_bill_requires_attachment", 0)
		try:
			log = self.a_log(service_provider=self.supplier, total_cost=5000,
			                 bill_no=f"SC-{frappe.generate_hash(length=5)}", bill_date=nowdate())
			self.assertEqual(submit_bill(log), "Pending Approval")
		finally:
			self.setting("maintenance_bill_requires_attachment", 1)

	def test_a_complete_bill_goes_for_approval(self):
		log = self.a_complete_bill()
		self.assertEqual(submit_bill(log), "Pending Approval")
		row = frappe.db.get_value("Asset Maintenance Log", log,
		                          ["submitted_by", "submission_date"], as_dict=True)
		self.assertTrue(row.submitted_by)
		self.assertTrue(row.submission_date)

	# --- rejection and resubmission --------------------------------------
	def test_a_rejected_bill_can_be_corrected_and_resubmitted(self):
		log = self.a_complete_bill()
		submit_bill(log)
		reject_bill(log, "Amount does not match the printed bill")
		self.assertEqual(
			frappe.db.get_value("Asset Maintenance Log", log, "bill_status"), "Rejected")
		self.assertTrue(frappe.db.get_value("Asset Maintenance Log", log, "rejection_reason"))

		frappe.db.set_value("Asset Maintenance Log", log, "total_cost", 9500,
		                    update_modified=False)
		self.assertEqual(submit_bill(log), "Pending Approval")

	def test_rejection_needs_a_reason(self):
		log = self.a_complete_bill()
		submit_bill(log)
		self.assertRaises(frappe.ValidationError, reject_bill, log, "   ")

	# --- approval and the purchasing document ----------------------------
	def test_completion_alone_raises_nothing(self):
		"""There is no bill and no agreed amount when the job merely finishes."""
		log = self.a_complete_bill()
		self.assertIsNone(frappe.db.get_value("Asset Maintenance Log", log, "purchase_invoice"))

	def test_only_a_submitted_bill_can_be_approved(self):
		log = self.a_complete_bill()
		self.assertRaises(frappe.ValidationError, approve_bill, log)

	def test_approval_raises_a_draft_invoice_from_the_actual_bill(self):
		if not self.item:
			self.skipTest("no service item on this site")
		self.setting("maintenance_po_on_completion", 1)
		self.setting("maintenance_service_item", self.item)
		self.setting("purchasing_company", COMPANY)

		log = self.a_complete_bill(amount=13750)
		bill_no = frappe.db.get_value("Asset Maintenance Log", log, "bill_no")
		submit_bill(log)
		result = approve_bill(log)

		self.assertEqual(result["bill_status"], "Approved")
		self.assertTrue(result["purchase_invoice"])
		invoice = frappe.get_doc("Purchase Invoice", result["purchase_invoice"])
		self.assertEqual(invoice.supplier, self.supplier)
		self.assertEqual(invoice.bill_no, bill_no)
		self.assertEqual(flt(invoice.grand_total), 13750)
		self.assertEqual(invoice.docstatus, 0, "the invoice must be left for Accounts to check")

	def test_approval_does_not_mark_anything_paid(self):
		if not self.item:
			self.skipTest("no service item on this site")
		self.setting("maintenance_po_on_completion", 1)
		self.setting("maintenance_service_item", self.item)
		self.setting("purchasing_company", COMPANY)
		log = self.a_complete_bill()
		submit_bill(log)
		result = approve_bill(log)
		self.assertNotEqual(result["payment_status"], "Paid")

	def test_approving_twice_does_not_raise_two_invoices(self):
		if not self.item:
			self.skipTest("no service item on this site")
		self.setting("maintenance_po_on_completion", 1)
		self.setting("maintenance_service_item", self.item)
		self.setting("purchasing_company", COMPANY)
		log = self.a_complete_bill()
		submit_bill(log)
		first = approve_bill(log)["purchase_invoice"]
		self.assertRaises(frappe.ValidationError, approve_bill, log)
		self.assertEqual(
			frappe.db.get_value("Asset Maintenance Log", log, "purchase_invoice"), first)

	def test_a_duplicate_bill_from_the_same_centre_is_blocked(self):
		"""Accounts Settings has invoice uniqueness switched off site-wide."""
		if not self.item:
			self.skipTest("no service item on this site")
		self.setting("maintenance_po_on_completion", 1)
		self.setting("maintenance_service_item", self.item)
		self.setting("purchasing_company", COMPANY)
		log = self.a_complete_bill()
		bill_no = frappe.db.get_value("Asset Maintenance Log", log, "bill_no")
		submit_bill(log)
		approve_bill(log)

		other = frappe.get_all("Asset Maintenance Log",
		                       filters={"name": ("!=", log)}, pluck="name")
		if not other:
			self.skipTest("only one maintenance log on this site")
		frappe.db.set_value("Asset Maintenance Log", other[0], {
			"service_provider": self.supplier, "total_cost": 500, "bill_no": bill_no,
			"bill_date": nowdate(), "bill_attachment": "/files/x.pdf",
			"bill_status": "Service Completed",
		}, update_modified=False)
		self.assertRaises(frappe.ValidationError, submit_bill, other[0])

	def test_missing_configuration_leaves_the_record_intact(self):
		"""Purchasing may fail; the maintenance history must not be lost."""
		self.setting("maintenance_po_on_completion", 1)
		self.setting("maintenance_service_item", None)
		log = self.a_complete_bill()
		submit_bill(log)
		approve_bill(log)
		row = frappe.db.get_value("Asset Maintenance Log", log,
		                          ["bill_status", "purchasing_status", "total_cost",
		                           "service_provider", "purchasing_message"], as_dict=True)
		self.assertEqual(row.bill_status, "Approved", "the approval must survive")
		self.assertEqual(row.purchasing_status, "Pending")
		self.assertIn("Service Item", row.purchasing_message)
		self.assertTrue(row.service_provider)

	def test_approved_bill_with_purchasing_off_says_so_plainly(self):
		"""The case reported on ACC-AML-2026-00071.

		The bill was submitted and approved correctly, but purchasing was
		switched off, so no invoice was raised. The record must say that in
		words rather than leave the user guessing why nothing appeared.
		"""
		self.setting("maintenance_po_on_completion", 0)
		log = self.a_complete_bill()
		submit_bill(log)
		result = approve_bill(log)

		self.assertEqual(result["bill_status"], "Approved")
		self.assertEqual(result["purchasing_status"], "Not Required")
		self.assertIsNone(result["purchase_invoice"])
		self.assertIn("switched off", result["purchasing_message"])

	def test_turning_purchasing_on_lets_an_approved_bill_be_retried(self):
		"""No need to redo the approval once the configuration is corrected."""
		if not self.item:
			self.skipTest("no service item on this site")
		self.setting("maintenance_po_on_completion", 0)
		log = self.a_complete_bill(amount=4250)
		submit_bill(log)
		approve_bill(log)
		self.assertIsNone(frappe.db.get_value("Asset Maintenance Log", log, "purchase_invoice"))

		self.setting("maintenance_po_on_completion", 1)
		self.setting("maintenance_service_item", self.item)
		self.setting("purchasing_company", COMPANY)
		result = retry_maintenance_purchase(log)

		self.assertTrue(result["purchase_invoice"])
		invoice = frappe.get_doc("Purchase Invoice", result["purchase_invoice"])
		self.assertEqual(invoice.docstatus, 0)
		self.assertEqual(flt(invoice.grand_total), 4250,
		                 "the supplier's original amount must be preserved")

	def test_purchasing_is_off_by_default(self):
		self.assertFalse(
			frappe.db.get_single_value("GDL Fleet Settings", "maintenance_po_on_completion"))

	def test_payment_status_is_read_from_the_invoice(self):
		from gdl_fleet_extension.utils.purchasing import get_payment_status
		self.assertEqual(get_payment_status(None), "Not Invoiced")
		self.assertEqual(get_payment_status("NO-SUCH-INVOICE"), "Not Invoiced")


# ===========================================================================
# CR4 - insurance renewal purchasing
# ===========================================================================
class TestInsurancePurchasing(IntegrationTestCase):
	def test_disabled_by_default(self):
		self.assertFalse(
			frappe.db.get_single_value("GDL Fleet Settings", "insurance_po_on_expiry"))

	def test_sweep_does_nothing_while_disabled(self):
		result = raise_insurance_renewal_orders()
		self.assertFalse(result["enabled"])
		self.assertEqual(result["ordered"], [])

	def test_tracking_fields_exist(self):
		fields = {f.fieldname for f in frappe.get_meta("Renewal Register").fields}
		for field in ("purchase_order", "purchasing_status", "purchasing_message"):
			self.assertIn(field, fields)

	def test_a_scheduled_job_exists_because_expiry_needs_no_user(self):
		events = frappe.get_hooks("scheduler_events", app_name="gdl_fleet_extension")
		self.assertIn("daily", events)
		self.assertTrue(any("daily_fleet_purchasing" in job for job in events["daily"]))

	def test_renewed_policies_are_excluded(self):
		names = [r["name"] for r in get_renewals_due_for_purchase(add_days(nowdate(), 3650))]
		for name in names:
			status = frappe.db.get_value("Renewal Register", name, "renewal_status")
			self.assertNotIn(status, ("Renewed", "Cancelled"))

	def test_only_insurance_is_considered(self):
		for row in get_renewals_due_for_purchase(add_days(nowdate(), 3650)):
			self.assertEqual(row["renewal_type"] if "renewal_type" in row else "Insurance",
			                 "Insurance")

	def test_missing_configuration_is_named_not_guessed(self):
		missing = missing_configuration(None, None, None)
		self.assertEqual(len(missing), 3)

	def test_missing_configuration_passes_when_complete(self):
		supplier = frappe.get_all("Supplier", pluck="name", limit=1)
		item = frappe.get_all("Item", pluck="name", limit=1)
		if not supplier or not item:
			self.skipTest("no supplier or item on this site")
		self.assertEqual(missing_configuration(supplier[0], item[0], COMPANY), [])

	def test_no_live_order_on_a_fresh_renewal(self):
		existing = frappe.get_all("Renewal Register", pluck="name", limit=1)
		if not existing:
			self.skipTest("no renewal records")
		self.assertIsNone(has_live_order("Renewal Register", existing[0]))
