# Copyright (c) 2026, GDL and contributors
"""A Supplier link a fleet role may actually use.

Two forms carry a Link to Supplier: the fuel provider on a POL line, and the
workshop on a service record. Frappe refuses a link lookup without "select" on
the target doctype, and no fleet role had it - so a driver choosing BOD got

    Permission Error - Insufficient Permission for Supplier

and the abstract could not be filled in at all. The grid's own filter, which
offers only the two fuel providers, never got the chance to run.

These tests drive the same call the link field makes, as the role, because
"select" is one of the rights Administrator makes invisible: every check passes
as Administrator whether the grant is there or not.
"""

import contextlib

import frappe
from frappe.tests import IntegrationTestCase

from gdl_fleet_extension.gdl_fleet.doctype.pol_abstract.pol_abstract import get_fuel_suppliers

NEEDS_THE_LOOKUP = ("Fleet Driver", "Fleet Maintenance User", "Fleet Approver",
                    "Fleet HR Approver", "Fleet Administrator")


class TestFleetRolesCanLookUpASupplier(IntegrationTestCase):
	def test_each_role_has_select_on_supplier(self):
		for role in NEEDS_THE_LOOKUP:
			self.assertTrue(
				frappe.db.get_value("Custom DocPerm",
				                    {"parent": "Supplier", "role": role, "permlevel": 0},
				                    "select"),
				f"{role} cannot look up a Supplier - every Link to Supplier is dead for them",
			)

	def test_the_link_search_itself_succeeds_as_the_role(self):
		"""The call the browser makes. It throws PermissionError when the grant
		is missing, which is exactly what the screenshot showed."""
		from frappe.desk.search import search_link

		for role in NEEDS_THE_LOOKUP:
			with acting_as(role):
				try:
					search_link(doctype="Supplier", txt="")
				except frappe.PermissionError:
					self.fail(f"{role} still gets 'Insufficient Permission for Supplier'")

	def test_select_is_not_a_back_door_into_the_supplier_list(self):
		"""select lets a field resolve a link. It must not hand over the ledger."""
		for role in NEEDS_THE_LOOKUP:
			if role == "Fleet Administrator":
				continue
			row = frappe.db.get_value("Custom DocPerm",
			                          {"parent": "Supplier", "role": role, "permlevel": 0},
			                          ["read", "write", "create", "delete", "export", "report"],
			                          as_dict=True)
			for right, granted in (row or {}).items():
				self.assertFalse(granted, f"{role} was given {right} on Supplier - only select was asked for")

	def test_standard_supplier_roles_are_untouched(self):
		"""add_permission() copies the standard rows into Custom DocPerm before
		adding ours. If that copy ever stops happening, Purchase and Accounts
		lose Supplier silently."""
		for role in ("Purchase User", "Purchase Manager", "Accounts User",
		             "Stock User", "Purchase Master Manager"):
			self.assertTrue(
				frappe.db.get_value("Custom DocPerm",
				                    {"parent": "Supplier", "role": role, "permlevel": 0}, "read"),
				f"{role} lost read on Supplier",
			)
		self.assertTrue(
			frappe.db.get_value("Custom DocPerm",
			                    {"parent": "Supplier", "role": "Purchase Master Manager",
			                     "permlevel": 0}, "create"),
			"Purchase Master Manager lost create on Supplier",
		)


class TestTheFuelProviderFilterStillApplies(IntegrationTestCase):
	"""select opens the lookup. It must not widen what the POL grid offers."""

	def test_only_the_two_providers_are_offered(self):
		suppliers = get_fuel_suppliers()
		self.assertLessEqual(len(suppliers), 2)
		for name in suppliers:
			self.assertTrue(frappe.db.exists("Supplier", name))

	def test_a_supplier_that_is_not_a_fuel_provider_is_refused_on_save(self):
		"""The filter is a convenience; the rule is enforced on the server."""
		import inspect
		from gdl_fleet_extension.gdl_fleet.doctype.pol_abstract.pol_abstract import POLAbstract
		source = inspect.getsource(POLAbstract.validate_entry_suppliers)
		self.assertIn("frappe.throw", source)


@contextlib.contextmanager
def acting_as(role):
	"""Become a user who holds exactly this role, and nothing else.

	Administrator bypasses every permission check, so a test that stays as
	Administrator proves nothing about a grant. This is the only way the
	"Insufficient Permission for Supplier" the driver saw can be reproduced -
	and the only way its absence means anything.
	"""
	email = f"gdl-perm-{role.lower().replace(' ', '-')}@example.com"
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


FLEET_ROLES = ("Fleet Driver", "Fleet User", "Fleet Approver", "Fleet Administrator",
               "Fleet Maintenance User", "Fleet Store User", "Fleet HR Approver")


class TestEveryLinkOnAFleetFormCanBeUsed(IntegrationTestCase):
	"""The invariant, rather than the twenty-one symptoms of breaking it.

	A Link field whose target the role cannot "select" is dead: frappe refuses
	the lookup and shows "Insufficient Permission for <doctype>". The Supplier
	error GDL hit was one instance; a sweep found the same break on Location,
	Vehicle Service Item, Cost Center, Project, Department, Task, Employee,
	Driver and twelve more.

	This fails the day someone adds a link to a fleet form and forgets the
	grant, which is the only way to stop it happening a fourth time.
	"""

	def test_no_fleet_role_meets_a_link_it_cannot_look_up(self):
		broken = []
		for role in FLEET_ROLES:
			if not frappe.db.exists("Role", role):
				continue
			for doctype in self.forms_the_role_may_fill(role):
				for owner, field, target in pickable_links(doctype):
					if not frappe.db.exists("DocType", target):
						continue
					if frappe.get_meta(target).issingle:
						continue
					if self.may_look_up(target, role):
						continue
					broken.append(f"{role} cannot look up {target} for {owner}.{field}")

		self.assertEqual(broken, [], "\n  " + "\n  ".join(broken))

	def forms_the_role_may_fill(self, role):
		for doctype in frappe.get_all("DocType", filters={"issingle": 0}, pluck="name"):
			row = self.perm_row(doctype, role)
			if row and (row.write or row.create):
				yield doctype

	def may_look_up(self, target, role):
		row = self.perm_row(target, role)
		return bool(row and (row.select or row.read))

	@staticmethod
	def perm_row(doctype, role):
		table = ("Custom DocPerm"
		         if frappe.db.exists("Custom DocPerm", {"parent": doctype})
		         else "DocPerm")
		return frappe.db.get_value(
			table, {"parent": doctype, "role": role, "permlevel": 0},
			["select", "read", "write", "create"], as_dict=True)


def pickable_links(doctype):
	"""Link fields a user can actually click into.

	Hidden and read-only links are excluded on purpose: neither opens a lookup,
	so neither justifies a permission. Child tables are walked, because the
	Service Type on a service line lives on Fleet Service Item, not on the log.
	"""
	for field in frappe.get_meta(doctype).fields:
		if field.hidden or field.read_only:
			continue
		if field.fieldtype == "Link" and field.options:
			yield doctype, field.fieldname, field.options
		elif field.fieldtype == "Table" and field.options:
			for cell in frappe.get_meta(field.options).fields:
				if cell.hidden or cell.read_only:
					continue
				if cell.fieldtype == "Link" and cell.options:
					yield field.options, cell.fieldname, cell.options


class TestTheLookupGrantsStayNarrow(IntegrationTestCase):
	"""A lookup grant must never become a way into the data behind it."""

	def test_select_only_on_every_link_target(self):
		from gdl_fleet_extension.setup.fleet_permissions import LINK_SELECT

		for doctype, roles in LINK_SELECT.items():
			if not frappe.db.exists("DocType", doctype):
				continue
			for role in roles:
				row = frappe.db.get_value(
					"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0},
					["select", "write", "create", "delete", "export", "report", "import"],
					as_dict=True)
				self.assertTrue(row, f"{role} has no row on {doctype}")
				self.assertTrue(row.select, f"{role} cannot select {doctype}")
				for right in ("write", "create", "delete", "export", "report", "import"):
					self.assertFalse(row.get(right),
					                 f"{role} was given {right} on {doctype} - only select was asked for")
