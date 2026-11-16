# Copyright (c) 2026, GDL and contributors
"""The simple service record.

Final document 2.1.1.4 lists what a service record holds. These tests read the
form the way a workshop clerk meets it and check two things: everything that
section names is on it, and nothing else is.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from gdl_fleet_extension.setup.maintenance_simplification import (
	ERPNEXT_SCAFFOLDING,
	PURCHASING_CYCLE,
)

DOCTYPE = "Asset Maintenance Log"

# Section 2.1.1.4, field for field.
THE_DOCUMENT_ASKS_FOR = {
	"vehicle": "Vehicle",
	"location": "Location",
	"completion_date": "Service Date",
	"odometer": "Odometer Reading",
	"service_items": "Service Type / Parts used - one row per item",
	"service_provider": "Service Provider",
	"actions_performed": "Service Description",
	"labour_cost": "Labour/Service Cost",
	"parts_cost": "Parts cost, which totals with labour",
	"total_cost": "Total Cost",
	"bill_no": "Invoice/Reference No",
	"next_due_date": "next service date",
	"next_due_odometer": "next service odometer",
	"cost_center": "Cost Center",
	"project": "Project",
}


class TestTheFormMatchesTheDocument(IntegrationTestCase):
	def setUp(self):
		self.meta = frappe.get_meta(DOCTYPE)

	def test_every_field_the_document_names_is_on_the_form(self):
		for fieldname, why in THE_DOCUMENT_ASKS_FOR.items():
			field = self.meta.get_field(fieldname)
			self.assertIsNotNone(field, f"{fieldname} is missing - the document asks for {why}")
			self.assertFalse(field.hidden, f"{fieldname} is hidden - the document asks for {why}")

	def test_the_erpnext_scaffolding_is_off_the_form(self):
		"""Asset Maintenance, Task, Periodicity, Certificate and the rest.

		A maintenance plan fills them. A clerk recording an oil change cannot.
		"""
		for fieldname in ERPNEXT_SCAFFOLDING:
			field = self.meta.get_field(fieldname)
			if field:
				self.assertTrue(field.hidden, f"{fieldname} is still on the form")

	def test_the_purchasing_cycle_is_off_the_form(self):
		"""The document asks for an Invoice/Reference No, not a procurement chain."""
		for fieldname in PURCHASING_CYCLE:
			field = self.meta.get_field(fieldname)
			if field:
				self.assertTrue(field.hidden, f"{fieldname} is still on the form")

	def test_nothing_was_deleted(self):
		"""Hidden, not dropped - ACC-AML records already carry these values, and
		the purchasing code still reads them."""
		for fieldname in ERPNEXT_SCAFFOLDING + PURCHASING_CYCLE:
			if fieldname.startswith(("column_break", "gdl_")):
				continue
			self.assertIsNotNone(self.meta.get_field(fieldname),
			                     f"{fieldname} must be hidden, never deleted")

	def test_no_more_than_the_document_asks_for_is_visible(self):
		"""The one that actually keeps the form simple.

		A field added later shows up here and has to be justified against the
		document or hidden, instead of quietly joining the form.
		"""
		allowed = set(THE_DOCUMENT_ASKS_FOR) | {
			"naming_series", "maintenance_status", "amended_from",
			"bill_date", "bill_attachment",       # the invoice the number refers to
			"driver", "driver_employee",          # who took the vehicle in
			# GDL asked for the Create Purchase Invoice button, so the record
			# has to show what it produced. The approval chain around these
			# stays off - this is the one invoice and nothing else.
			"purchase_invoice", "purchasing_status",
		}
		visible = {f.fieldname for f in self.meta.fields
		           if not f.hidden
		           and f.fieldtype not in ("Section Break", "Column Break", "Tab Break")}
		self.assertEqual(visible - allowed, set())

	def test_the_vehicle_is_required(self):
		"""Without one the record joins no service history and no due list."""
		self.assertTrue(self.meta.get_field("vehicle").reqd)

	def test_the_form_uses_the_document_s_words(self):
		for fieldname, label in (("odometer", "Odometer Reading"),
		                         ("actions_performed", "Service Description"),
		                         ("bill_no", "Invoice / Reference No")):
			self.assertEqual(self.meta.get_field(fieldname).label, label)

	def test_the_service_line_names_the_service_type(self):
		meta = frappe.get_meta("Fleet Service Item")
		self.assertEqual(meta.get_field("service_item").label, "Service Type")
		self.assertEqual(meta.get_field("part_brand").label, "Part / Material Used")

	def test_the_invoice_number_is_asked_for_once(self):
		"""It was on the record and on every line. One is the document's answer."""
		self.assertTrue(frappe.get_meta("Fleet Service Item").get_field("invoice_reference").hidden)


class TestPurchasingIsStoodDown(IntegrationTestCase):
	"""Hiding a cycle that still runs would be worse than leaving it visible."""

	def test_the_switch_is_off_on_this_site(self):
		"""Reads what the site holds, not what a fixture sets - the shape of bug
		that let maintenance_bill_requires_attachment sit at 0 unnoticed."""
		self.assertFalse(
			frappe.db.get_single_value("GDL Fleet Settings", "maintenance_po_on_completion"),
			"purchasing on completion is still on - patches/v1_9 did not run",
		)

	def test_no_record_is_left_waiting_on_a_purchase_order(self):
		self.assertEqual(
			frappe.get_all("Asset Maintenance Log",
			               filters={"purchasing_status": "Pending"}, limit=1), [],
			"a completed service is still stuck at Purchasing: Pending",
		)

	def test_the_code_is_still_there_for_the_day_gdl_wants_it(self):
		from gdl_fleet_extension.overrides import asset_maintenance
		self.assertTrue(hasattr(asset_maintenance, "maintenance_log_purchasing"))


class TestNoHiddenBreakSwallowsAField(IntegrationTestCase):
	"""The bug this class of change actually produces.

	frappe's Column.refresh() puts hide-control on the column WRAPPER:

	    const hide = this.df.hidden || this.df.hidden_due_to_dependency;
	    this.wrapper.toggleClass("hide-control", !!hide);

	Every field in that column is a child of that wrapper, so hiding a Column
	Break hides every field after it until the next break - while the meta goes
	on reporting each of them as perfectly visible.

	That is how Status, Service Date, Odometer Reading and Service Provider
	vanished from the maintenance log. Nothing caught it: every test here reads
	`hidden` off the meta, and the meta was right. GDL found it when a log
	could not be submitted, with no Status field on screen to change.

	This reads the layout the way the browser builds it.
	"""

	FORMS = ("Asset Maintenance Log", "POL Abstract", "Vehicle Log",
	         "Movement Order", "Movement Order Request")

	def test_no_visible_field_sits_behind_a_hidden_break(self):
		lost = []
		for doctype in self.FORMS:
			if not frappe.db.exists("DocType", doctype):
				continue
			lost += self.swallowed_fields(doctype)

		self.assertEqual(lost, [], "these fields are on no screen:\n  " + "\n  ".join(lost))

	@staticmethod
	def swallowed_fields(doctype):
		"""Walk the fields as the layout does: a hidden break takes the column
		or section with it until the next one opens."""
		out = []
		hiding = None
		for field in frappe.get_meta(doctype).fields:
			if field.fieldtype in ("Section Break", "Column Break", "Tab Break"):
				# A section break opens a new section AND a new column, so it
				# ends a hidden column. A column break only ends a hidden column.
				if hiding == "column" or field.fieldtype != "Column Break":
					hiding = None
				hiding = field.fieldtype.split()[0].lower() if field.hidden else hiding
				continue
			if hiding and not field.hidden:
				out.append(f"{doctype}.{field.fieldname} "
				           f"(visible, but behind a hidden {hiding} break)")
		return out

	def test_the_four_fields_that_went_missing_are_reachable(self):
		"""Named, because these are the ones GDL could not submit without."""
		lost = {f.split(".")[1].split(" ")[0]
		        for f in self.swallowed_fields("Asset Maintenance Log")}
		for fieldname in ("maintenance_status", "completion_date",
		                  "odometer", "service_provider"):
			self.assertNotIn(fieldname, lost)

	def test_the_status_field_can_be_reached_at_all(self):
		"""Submit refuses anything but Completed or Cancelled, so a form with no
		Status field is a form that can never be submitted."""
		field = frappe.get_meta("Asset Maintenance Log").get_field("maintenance_status")
		self.assertFalse(field.hidden)
		self.assertEqual(field.permlevel, 0)
		self.assertNotIn("maintenance_status",
		                 {f.split(".")[1].split(" ")[0]
		                  for f in self.swallowed_fields("Asset Maintenance Log")})


class TestAServiceCanBeRecordedWithoutAPlan(IntegrationTestCase):
	"""The driver's form, end to end.

	GDL: "when driver will serviced the vehicle then enter the simple form".
	Blueprint 2.1.1.4 asks for a service record against the vehicle and its
	odometer, and says nothing about maintenance plans. None of GDL's vehicles
	is linked to an Asset.

	ERPNext's Asset Maintenance Log is built as a child of an Asset Maintenance
	plan, and its on_submit does

	    frappe.get_doc("Asset Maintenance Task", self.task)

	with no check that a task exists. A standalone service could be saved and
	then died on submit with "Asset Maintenance Task None not found" - so the
	record was unfinishable. GDLAssetMaintenanceLog skips that step when there
	is no plan, and leaves it alone when there is.
	"""

	def setUp(self):
		from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
		self.vehicle = new_vehicle(last_odometer=30000)
		self.vehicle.insert()

	def service(self, **kwargs):
		from frappe.utils import nowdate
		values = {
			"doctype": "Asset Maintenance Log",
			"vehicle": self.vehicle.name,
			"maintenance_status": "Completed",
			"completion_date": nowdate(),
			"odometer": 30500,
			"actions_performed": "<p>Engine oil and filter</p>",
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		return doc

	def test_the_override_is_the_class_in_use(self):
		"""A doc_event cannot stop a controller's own on_submit - only an
		override_doctype_class can, which is why this is a subclass."""
		from gdl_fleet_extension.overrides.asset_maintenance import GDLAssetMaintenanceLog
		self.assertIsInstance(frappe.new_doc("Asset Maintenance Log"), GDLAssetMaintenanceLog)

	def test_a_service_with_no_plan_submits(self):
		doc = self.service()
		doc.insert()
		self.assertIsNone(doc.task)
		self.assertIsNone(doc.asset_maintenance)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_the_status_default_is_NOT_on_the_doctype(self):
		"""It belongs on the form and nowhere else.

		A DocType default reaches Asset Maintenance's sync_maintenance_tasks(),
		which creates a log for every SCHEDULED task. Those defaulted to
		Completed and were then refused for having no completion date - a
		maintenance plan could not be saved at all. Fourteen tests caught it.
		"""
		self.assertFalse(
			frappe.get_meta("Asset Maintenance Log").get_field("maintenance_status").default,
			"the default is back on the DocType and will break maintenance plans")

	def test_the_service_date_is_required_only_once_completed(self):
		"""Conditional, for the same reason: a scheduled service has no
		completion date yet, and a flat reqd refused every one."""
		field = frappe.get_meta("Asset Maintenance Log").get_field("completion_date")
		self.assertFalse(field.reqd, "a flat reqd breaks ERPNext's maintenance plan")
		self.assertEqual(field.mandatory_depends_on,
		                 'eval:doc.maintenance_status=="Completed"')

	def test_a_scheduled_log_can_still_be_created(self):
		"""The path the defaults broke, driven directly."""
		from frappe.utils import add_days, nowdate
		doc = frappe.get_doc({
			"doctype": "Asset Maintenance Log",
			"vehicle": self.vehicle.name,
			"maintenance_status": "Planned",
			"due_date": add_days(nowdate(), 30),
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		self.assertEqual(doc.maintenance_status, "Planned")
		self.assertFalse(doc.completion_date)

	def test_a_planned_service_still_updates_its_task(self):
		"""The half that must NOT change: when a plan is behind the log,
		ERPNext's own behaviour runs untouched."""
		import inspect
		from gdl_fleet_extension.overrides.asset_maintenance import GDLAssetMaintenanceLog
		source = inspect.getsource(GDLAssetMaintenanceLog.update_maintenance_task)
		self.assertIn("super().update_maintenance_task()", source,
		              "the planned path no longer reaches ERPNext's own handling")

	def test_the_odometer_reaches_the_vehicle(self):
		"""A service record carries a reading; the vehicle should learn from it."""
		doc = self.service(odometer=30800)
		doc.insert()
		doc.submit()
		self.assertGreaterEqual(
			frappe.db.get_value("Vehicle", self.vehicle.name, "last_odometer"), 30800)


class TestTheInvoiceButton(IntegrationTestCase):
	"""GDL: "once the service log completed need here create purchase invoice
	option here after that the account person see all the details in purchase
	invoice page."

	A button, not automation. The old automation fired on bill approval through
	a chain nobody uses and needed a Service Item nobody had set, so every
	completed service stopped at "Purchasing: Pending" with an error only the
	record could see. This runs when somebody asks, and says what is missing
	when it cannot.
	"""

	ACCOUNT_SETTING = "maintenance_expense_account"

	def setUp(self):
		from gdl_fleet_extension.tests.test_vehicle_extension import new_vehicle
		self.company = frappe.defaults.get_user_default("Company") \
			or frappe.get_all("Company", limit=1, pluck="name")
		if not self.company:
			self.skipTest("no Company on this site")
		self.company = self.company if isinstance(self.company, str) else self.company[0]

		self.account = frappe.get_all(
			"Account", filters={"company": self.company, "is_group": 0,
			                    "root_type": "Expense"}, limit=1, pluck="name")
		if not self.account:
			self.skipTest("no expense account on this site")
		self.account = self.account[0]

		self.supplier = "_Test Fleet Workshop"
		if not frappe.db.exists("Supplier", self.supplier):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": self.supplier,
			                "supplier_group": "All Supplier Groups"}).insert(ignore_permissions=True)

		self.vehicle = new_vehicle(company=self.company, last_odometer=40000)
		self.vehicle.insert()
		self.set_account(self.account)

	def tearDown(self):
		self.set_account(None)

	def set_account(self, value):
		frappe.db.set_single_value("GDL Fleet Settings", self.ACCOUNT_SETTING, value)
		frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def completed_service(self, **kwargs):
		from frappe.utils import nowdate
		values = {
			"doctype": "Asset Maintenance Log", "vehicle": self.vehicle.name,
			"maintenance_status": "Completed", "completion_date": nowdate(),
			"odometer": 40500, "service_provider": self.supplier,
			"labour_cost": 1500, "bill_no": f"WS-{frappe.generate_hash(length=6)}",
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert()
		doc.submit()
		return doc

	# --- the happy path ---------------------------------------------------
	def test_it_raises_a_draft_invoice(self):
		from gdl_fleet_extension.utils.fleet_purchase_automation import make_maintenance_invoice
		doc = self.completed_service()
		invoice = frappe.get_doc("Purchase Invoice", make_maintenance_invoice(doc.name))

		self.assertEqual(invoice.docstatus, 0, "a draft, for Accounts to check against the bill")
		self.assertEqual(invoice.supplier, self.supplier)
		self.assertEqual(flt(invoice.grand_total), flt(doc.total_cost))

	def test_accounts_can_see_what_they_are_paying_for(self):
		"""The whole reason for the button: the invoice has to carry the detail."""
		from gdl_fleet_extension.utils.fleet_purchase_automation import make_maintenance_invoice
		doc = self.completed_service()
		invoice = frappe.get_doc("Purchase Invoice", make_maintenance_invoice(doc.name))

		description = invoice.items[0].description
		self.assertIn(self.vehicle.name, description, "the invoice does not say which vehicle")
		self.assertIn(str(doc.odometer), description)
		self.assertEqual(invoice.bill_no, doc.bill_no)
		self.assertEqual(invoice.get("asset_maintenance_log"), doc.name,
		                 "Accounts cannot click back to the service record")

	def test_it_needs_no_item_master(self):
		"""An Item invented for 'vehicle service' would be a second thing to
		maintain; the posting needs an account, not an Item."""
		from gdl_fleet_extension.utils.fleet_purchase_automation import make_maintenance_invoice
		doc = self.completed_service()
		invoice = frappe.get_doc("Purchase Invoice", make_maintenance_invoice(doc.name))
		self.assertFalse(invoice.items[0].item_code)
		self.assertEqual(invoice.items[0].expense_account, self.account)

	def test_the_invoice_is_found_from_the_invoice_side(self):
		"""The service stores no link to its invoice. A stored Link makes
		frappe refuse to cancel the invoice:

		    Cannot delete or cancel because Purchase Invoice ... is linked
		    with Asset Maintenance Log ...

		and cancelling a wrong invoice is how Accounts fix one. POL points the
		same way for the same reason."""
		from gdl_fleet_extension.utils.fleet_purchase_automation import (
			get_maintenance_invoice, make_maintenance_invoice)
		doc = self.completed_service()
		name = make_maintenance_invoice(doc.name)
		self.assertEqual(get_maintenance_invoice(doc.name), name)
		self.assertFalse(
			frappe.db.get_value("Asset Maintenance Log", doc.name, "purchase_invoice"),
			"a link stored here makes the invoice impossible to cancel")

	# --- what it refuses ---------------------------------------------------
	def test_pressing_it_twice_returns_the_same_invoice(self):
		from gdl_fleet_extension.utils.fleet_purchase_automation import make_maintenance_invoice
		doc = self.completed_service()
		first = make_maintenance_invoice(doc.name)
		self.assertEqual(make_maintenance_invoice(doc.name), first,
		                 "a second press raised a second invoice")

	def test_an_unsubmitted_service_is_refused(self):
		"""Bill work that is confirmed done, not work somebody typed in."""
		from frappe.utils import nowdate
		from gdl_fleet_extension.utils.fleet_purchase_automation import make_maintenance_invoice
		doc = frappe.get_doc({
			"doctype": "Asset Maintenance Log", "vehicle": self.vehicle.name,
			"maintenance_status": "Completed", "completion_date": nowdate(),
			"service_provider": self.supplier, "labour_cost": 100})
		doc.flags.ignore_permissions = True
		doc.insert()
		self.assertRaises(frappe.ValidationError, make_maintenance_invoice, doc.name)

	def test_the_same_workshop_bill_cannot_be_paid_twice(self):
		from gdl_fleet_extension.utils.fleet_purchase_automation import make_maintenance_invoice
		first = self.completed_service()
		make_maintenance_invoice(first.name)

		again = self.completed_service(bill_no=first.bill_no)
		self.assertRaises(frappe.ValidationError, make_maintenance_invoice, again.name)

	def test_a_missing_expense_account_says_so(self):
		"""The old automation failed into a hidden field. This one speaks."""
		from gdl_fleet_extension.utils.fleet_purchase_automation import make_maintenance_invoice
		doc = self.completed_service()
		self.set_account(None)
		with self.assertRaises(frappe.ValidationError) as caught:
			make_maintenance_invoice(doc.name)
		self.assertIn("Expense Account", str(caught.exception))

	def test_a_group_account_is_refused_with_the_accounts_underneath_it(self):
		"""GDL set this to "52 - Expense - Running and Maintenance Costs", a
		heading in the chart. ERPNext refuses a group account deep inside the
		invoice save, complaining about the item rather than the setting, so
		this catches it where the setting can be named."""
		from gdl_fleet_extension.utils.fleet_purchase_automation import make_maintenance_invoice
		group = frappe.get_all("Account", filters={
			"company": self.company, "is_group": 1, "root_type": "Expense"},
			limit=1, pluck="name")
		if not group:
			self.skipTest("no group expense account on this site")

		doc = self.completed_service()
		self.set_account(group[0])
		with self.assertRaises(frappe.ValidationError) as caught:
			make_maintenance_invoice(doc.name)
		self.assertIn("group account", str(caught.exception).lower())

	def test_a_submitted_invoice_can_still_be_cancelled(self):
		"""The reason the link lives on the invoice. Accounts cancel a wrong
		invoice; nothing on the service record may stand in the way."""
		from gdl_fleet_extension.utils.fleet_purchase_automation import make_maintenance_invoice
		doc = self.completed_service()
		invoice = frappe.get_doc("Purchase Invoice", make_maintenance_invoice(doc.name))
		invoice.flags.ignore_permissions = True
		invoice.submit()
		invoice.cancel()
		self.assertEqual(invoice.docstatus, 2)

	def test_the_record_says_it_is_invoiced(self):
		from gdl_fleet_extension.utils.fleet_purchase_automation import make_maintenance_invoice
		doc = self.completed_service()
		make_maintenance_invoice(doc.name)
		self.assertEqual(
			frappe.db.get_value("Asset Maintenance Log", doc.name, "purchasing_status"),
			"Invoiced")

	def test_a_cancelled_invoice_lets_the_record_be_billed_again(self):
		"""Cancelling is how Accounts reject a wrong invoice. The service still
		happened and still has to be paid for."""
		from gdl_fleet_extension.utils.fleet_purchase_automation import make_maintenance_invoice
		doc = self.completed_service()
		first = frappe.get_doc("Purchase Invoice", make_maintenance_invoice(doc.name))
		first.flags.ignore_permissions = True
		first.submit()
		first.cancel()

		doc.reload()
		again = make_maintenance_invoice(doc.name)
		self.assertNotEqual(again, first.name,
		                    "a cancelled invoice still blocks the record from being billed")
