# Copyright (c) 2026, GDL and contributors
"""
Driver details shared across every fleet form.

The Driver master already carries the relationships this needs - `employee`,
`license_number` and `site` - so nothing is duplicated here. This is the one
place that reads them, so every form agrees.

A caution that shapes the whole module: "employee" does not mean the same thing
everywhere.

  * Driver Assignment.employee  - the DRIVER's employee record
  * Movement Order Request.employee - the REQUESTER's employee record
  * Vehicle Log.employee        - fetched from the VEHICLE's responsible employee

Only the first is the driver's. The others are deliberately left alone; filling
them from the driver would quietly destroy real information.
"""

import frappe
from frappe import _

DRIVER_FIELDS = ("employee", "license_number", "site", "cell_number", "full_name")


def get_driver_details(driver: str | None) -> dict:
	"""Everything a form may want about a driver, in one read.

	Returns empty strings rather than None so a client-side fetch clears a
	stale value instead of leaving the previous driver's details on screen.
	"""
	blank = dict.fromkeys(DRIVER_FIELDS, "")
	if not driver:
		return blank

	row = frappe.db.get_value("Driver", driver, DRIVER_FIELDS, as_dict=True)
	if not row:
		return blank

	return {field: (row.get(field) or "") for field in DRIVER_FIELDS}


@frappe.whitelist()
def fetch_driver_details(driver: str | None = None) -> dict:
	"""Form-facing version of get_driver_details."""
	frappe.has_permission("Driver", "read", throw=True)
	return get_driver_details(driver)


def validate_driver_employee(doc, driver_field="driver", employee_field="employee"):
	"""Keep the driver and the employee on a record consistent.

	Runs on the server so it holds for the API and for imports too, not only
	for someone typing in the form.

	Three cases:
	  * no driver, or no employee entered - nothing to check;
	  * the driver has no employee on their master - the record is allowed
	    through with a warning, because the data has gaps and blocking it would
	    stop work;
	  * both are set and disagree - refused, because one of them is wrong.
	"""
	driver = doc.get(driver_field)
	employee = doc.get(employee_field)
	if not driver or not employee:
		return

	expected = frappe.db.get_value("Driver", driver, "employee")

	if not expected:
		frappe.msgprint(
			_("Driver {0} has no Employee on their Driver record, so {1} could not "
			  "be verified. Add the Employee to the Driver master to keep these in step.")
			.format(frappe.bold(driver), frappe.bold(employee)),
			title=_("Driver Has No Employee"),
			indicator="orange",
		)
		return

	if expected != employee:
		frappe.throw(
			_("Employee {0} does not belong to Driver {1}, whose Employee is {2}. "
			  "Correct one of them, or clear the Employee to have it fetched again.")
			.format(frappe.bold(employee), frappe.bold(driver), frappe.bold(expected)),
			title=_("Driver and Employee Do Not Match"),
		)


def apply_driver_details(doc, driver_field="driver", mapping=None):
	"""Copy driver details onto a document server-side.

	`mapping` is {document fieldname: driver fieldname}. Only fields the
	DocType actually has are touched, so one helper serves forms that carry
	different subsets.
	"""
	mapping = mapping or {}
	details = get_driver_details(doc.get(driver_field))
	for target, source in mapping.items():
		if not doc.meta.get_field(target):
			continue
		doc.set(target, details.get(source) or None)
