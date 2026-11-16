# Copyright (c) 2026, GDL and contributors
"""The Connections strip on the Vehicle form.

GDL, looking at the Vehicle's Insurance Details beside a Renewal Register
record holding the same dates: "then what is Renewal Register? need link with
that". There was no way to get from a vehicle to its renewals except by
opening the Renewal Register list and filtering it by hand.

An override_doctype_dashboards hook is called by frappe as

    frappe.get_attr(hook)(data=data)

- see Meta.get_dashboard_data() in frappe/model/meta.py. The `data` handed in
is ALREADY the finished dashboard: ERPNext's own vehicle_dashboard plus any
DocType Link rows frappe added. So this EXTENDS what it is given rather than
building its own; anything ERPNext or GDL adds later still appears.

The first version of this took no arguments and rebuilt the dashboard from
ERPNext's. That broke the Vehicle list outright -
"TypeError: get_data() got an unexpected keyword argument 'data'".
"""

import frappe
from frappe import _

RENEWAL_DOCTYPE = "Renewal Register"


def get_data(data=None):
	if data is None:
		# Only reached when something calls this directly. frappe always passes
		# the built dashboard in.
		from erpnext.setup.doctype.vehicle.vehicle_dashboard import (
			get_data as erpnext_get_data,
		)
		data = erpnext_get_data()

	data = frappe._dict(data)

	# ERPNext links its own transactions on `license_plate`; the fleet
	# documents all carry a `vehicle` Link instead.
	non_standard = frappe._dict(data.get("non_standard_fieldnames") or {})
	non_standard[RENEWAL_DOCTYPE] = "vehicle"
	data.non_standard_fieldnames = non_standard

	transactions = list(data.get("transactions") or [])
	already_linked = any(
		RENEWAL_DOCTYPE in (group.get("items") or []) for group in transactions
	)
	if not already_linked:
		transactions.append({"label": _("Renewals"), "items": [RENEWAL_DOCTYPE]})
	data.transactions = transactions

	return data
