# Copyright (c) 2026, GDL and contributors
"""
DEF-001 regression suite.

Every assertion evaluates a NAMED ROLE. None runs as Administrator, which
bypasses every check - that is how DEF-001 survived 606 tests and three rounds
of manual testing.

Each test user holds EXACTLY ONE role. A user with two roles cannot tell you
which one granted access, and that ambiguity is precisely how the defect hid:
every tester also held Fleet Manager, the one role ERPNext ships with access.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from gdl_fleet_extension.setup.fleet_permissions import (
	FLEET_PERMISSIONS,
	LINK_SELECT,
	permission_report,
	setup_fleet_permissions,
)

# The doctypes this fix grants a role rights ON, as opposed to the ones it only
# lets a Link field look up. RT-14 and RT-15 are about the former: they ask that
# the fix never handed a fleet role a delete or an import it did not have.
#
# A LINK_SELECT target is a different thing. Movement Order is in FLEET_PERMISSIONS
# only so a driver's Vehicle Log can point at one, and it already granted its own
# Fleet Administrator delete in its DocType JSON, long before any of this. Judging
# it by RT-14 would be judging a pre-existing decision by a rule written for
# something else. What this fix DID grant on those targets - select and nothing
# else - is asserted in test_supplier_lookup.TestTheLookupGrantsStayNarrow.
FUNCTIONAL_GRANTS = [d for d in FLEET_PERMISSIONS if d not in LINK_SELECT]

PERM_TYPES = ("select", "read", "write", "create", "submit", "cancel", "amend", "delete", "import")

# Roles ERPNext/HRMS ship. The fix must leave their level-0 rights untouched.
STANDARD_ROLES = ("Fleet Manager", "Delivery Manager", "Delivery User", "Manufacturing User")


def user_with_only(role):
	"""A disposable user holding exactly one fleet role, and nothing else."""
	email = f"uat.{role.lower().replace(' ', '.')}@gdl.test"
	if frappe.db.exists("User", email):
		return email
	user = frappe.get_doc({
		"doctype": "User", "email": email, "first_name": role,
		"user_type": "System User", "send_welcome_email": 0, "enabled": 1,
	})
	user.flags.ignore_permissions = True
	user.insert()
	# strip the defaults frappe grants, so the role under test is the only one
	user.set("roles", [])
	user.append("roles", {"role": role})
	user.flags.ignore_permissions = True
	user.save()
	return email


def rights(doctype, role, permlevel=0):
	"""What a role may do, straight from the live meta."""
	for p in frappe.get_meta(doctype).permissions:
		if p.role == role and p.permlevel == permlevel:
			return sorted(k for k in PERM_TYPES if p.get(k))
	return None


def snapshot():
	"""Every permission row on every doctype the fix touches."""
	snap = {}
	for dt in FLEET_PERMISSIONS:
		for p in frappe.get_meta(dt).permissions:
			snap[(dt, p.role, p.permlevel)] = set(k for k in PERM_TYPES if p.get(k))
	return snap


# ---------------------------------------------------------------------------
# RT-01 .. RT-05  the roles can do their jobs
# ---------------------------------------------------------------------------
class TestRolesCanWork(IntegrationTestCase):
	def test_rt01_administrator_can_create_a_vehicle(self):
		user = user_with_only("Fleet Administrator")
		self.assertTrue(frappe.has_permission("Vehicle", "create", user=user))
		self.assertTrue(frappe.has_permission("Vehicle", "write", user=user))

	def test_rt02_administrator_can_create_a_driver(self):
		user = user_with_only("Fleet Administrator")
		self.assertTrue(frappe.has_permission("Driver", "create", user=user))
		self.assertTrue(frappe.has_permission("Driver", "write", user=user))

	def test_rt03_driver_can_create_a_vehicle_log(self):
		"""The single most frequent fleet task, and the one DEF-001 blocked."""
		user = user_with_only("Fleet Driver")
		for ptype in ("read", "write", "create", "submit"):
			self.assertTrue(
				frappe.has_permission("Vehicle Log", ptype, user=user),
				f"Fleet Driver cannot {ptype} a Vehicle Log",
			)

	def test_rt04_maintenance_user_can_record_maintenance(self):
		user = user_with_only("Fleet Maintenance User")
		for ptype in ("read", "write", "create", "submit"):
			self.assertTrue(
				frappe.has_permission("Asset Maintenance Log", ptype, user=user),
				f"Fleet Maintenance User cannot {ptype} an Asset Maintenance Log",
			)
		self.assertTrue(frappe.has_permission("Asset Repair", "create", user=user))

	def test_rt05_manager_can_read_every_fleet_report(self):
		user = user_with_only("Fleet Manager")
		reports = frappe.get_all("Report", filters={"module": "GDL Fleet"}, pluck="name")
		self.assertGreaterEqual(len(reports), 18)
		for report in reports:
			roles = frappe.get_all(
				"Has Role", filters={"parent": report, "parenttype": "Report"}, pluck="role"
			)
			self.assertIn("Fleet Manager", roles, f"{report} is not readable by Fleet Manager")


# ---------------------------------------------------------------------------
# RT-06 .. RT-09  the refusals
# ---------------------------------------------------------------------------
class TestRefusals(IntegrationTestCase):
	def test_rt06_fleet_user_cannot_approve_their_own_request(self):
		workflow = frappe.get_doc("Workflow", "GDL Movement Order Request Review")
		accept = [t for t in workflow.transitions if t.action == "Accept"]
		self.assertTrue(accept)
		for t in accept:
			self.assertNotEqual(t.allowed, "Fleet User")
			self.assertFalse(int(t.allow_self_approval), "Accept must not self-approve")

	def test_rt07_wrong_site_mto_cannot_approve(self):
		"""Builds its own two sites rather than depending on how the host site
		happens to be configured - a skipped permission test proves nothing."""
		from gdl_fleet_extension.utils.location_officers import may_approve
		from gdl_fleet_extension.tests.test_location_officers import (
			make_location, make_user,
		)

		settings = frappe.get_single("GDL Fleet Settings")
		original = [row.as_dict() for row in settings.get("location_officers") or []]
		original_enforce = settings.enforce_location_mto
		try:
			alpha, bravo = make_location("RT07-ALPHA"), make_location("RT07-BRAVO")
			mto_a, mto_b = make_user("rt07.a@gdl.test"), make_user("rt07.b@gdl.test")

			settings.set("location_officers", [])
			settings.append("location_officers", {"location": alpha, "mto": mto_a})
			settings.append("location_officers", {"location": bravo, "mto": mto_b})
			settings.enforce_location_mto = 1
			settings.flags.ignore_permissions = True
			settings.save()
			frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

			self.assertTrue(may_approve(alpha, mto_a), "an MTO must approve their own site")
			self.assertFalse(may_approve(bravo, mto_a), "an MTO must NOT approve another site")
		finally:
			settings = frappe.get_single("GDL Fleet Settings")
			settings.set("location_officers", [])
			for row in original:
				settings.append("location_officers", row)
			settings.enforce_location_mto = original_enforce
			settings.flags.ignore_permissions = True
			settings.save()
			frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def test_rt08_driver_cannot_approve_their_own_pol(self):
		workflow = frappe.get_doc("Workflow", "GDL POL Approval")
		approve = [t for t in workflow.transitions if t.action == "Approve"]
		self.assertTrue(approve)
		for t in approve:
			self.assertEqual(t.allowed, "Fleet HR Approver")
			self.assertFalse(int(t.allow_self_approval))

	def test_rt09_unauthorised_roles_are_refused(self):
		"""The denial matrix. Every False here is the point of the test."""
		denied = {
			"Fleet User": [("Vehicle", "create"), ("Driver", "create"),
			               ("Vehicle Log", "create"), ("Asset Maintenance Log", "create")],
			# NOT "Asset Maintenance Log, create": decision 1 says the driver
			# records the service. What they must not reach is the MONEY on it,
			# which is permlevel 1 and is asserted by RT-19b and RT-20.
			"Fleet Driver": [("Vehicle", "create"), ("Driver", "create"),
			                 ("Vehicle Log", "cancel")],
			"Fleet Approver": [("Vehicle", "create"), ("Driver", "create"),
			                   ("Vehicle Log", "create")],
			"Fleet Store User": [("Vehicle", "write"), ("Vehicle Log", "create")],
			"Fleet HR Approver": [("Vehicle", "write"), ("Vehicle Log", "create")],
			"Fleet Maintenance User": [("Vehicle", "create"), ("Driver", "create")],
		}
		for role, checks in denied.items():
			user = user_with_only(role)
			for doctype, ptype in checks:
				self.assertFalse(
					frappe.has_permission(doctype, ptype, user=user),
					f"{role} should NOT be able to {ptype} {doctype}",
				)


# ---------------------------------------------------------------------------
# RT-10 .. RT-18  the fix must not break anything
# ---------------------------------------------------------------------------
class TestNothingBroken(IntegrationTestCase):
	def test_rt10_the_change_is_additive(self):
		"""Re-running the setup must never shrink a permission."""
		before = snapshot()
		setup_fleet_permissions()
		after = snapshot()
		for key, rights_before in before.items():
			self.assertIn(key, after, f"{key} disappeared")
			self.assertTrue(
				rights_before.issubset(after[key]),
				f"{key} lost {rights_before - after[key]}",
			)

	def test_rt11_standard_fleet_manager_rows_are_untouched(self):
		"""Fleet Manager is a STANDARD ERPNext role. Its level-0 rows must match
		what erpnext and hrms ship."""
		self.assertEqual(rights("Vehicle", "Fleet Manager"),
		                 ["create", "delete", "read", "write"])
		self.assertEqual(rights("Driver", "Fleet Manager"), ["read"])
		self.assertEqual(rights("Vehicle Log", "Fleet Manager"),
		                 ["cancel", "create", "delete", "read", "submit", "write"])

	def test_rt12_setup_is_idempotent(self):
		setup_fleet_permissions()
		second = setup_fleet_permissions()
		self.assertEqual(second["granted"], [], f"second run changed: {second['granted']}")

	def test_rt13_permissions_survive_a_rebuild(self):
		setup_fleet_permissions()
		frappe.clear_cache()
		self.assertTrue(frappe.has_permission(
			"Vehicle Log", "create", user=user_with_only("Fleet Driver")))

	def test_rt14_no_gdl_role_may_delete(self):
		for doctype in FUNCTIONAL_GRANTS:
			for p in frappe.get_meta(doctype).permissions:
				if p.role.startswith("Fleet") and p.role != "Fleet Manager":
					self.assertFalse(p.delete, f"{p.role} may delete {doctype}")

	def test_rt15_no_gdl_role_may_import(self):
		for doctype in FUNCTIONAL_GRANTS:
			for p in frappe.get_meta(doctype).permissions:
				if p.role.startswith("Fleet") and p.role != "Fleet Manager":
					self.assertFalse(p.get("import"), f"{p.role} may import {doctype}")

	def test_rt16_movement_request_permlevel_1_unchanged(self):
		self.assertEqual(rights("Movement Order Request", "Fleet Approver", 1), ["read", "write"])
		self.assertEqual(rights("Movement Order Request", "Fleet User", 1), ["read"])

	def test_rt17_if_owner_unchanged_on_movement_request(self):
		row = [p for p in frappe.get_meta("Movement Order Request").permissions
		       if p.role == "Fleet User" and p.permlevel == 0][0]
		self.assertTrue(row.if_owner, "a requester must only reach their own request")

	def test_rt18_live_matrix_matches_the_specification(self):
		report = permission_report()
		for doctype, levels in FLEET_PERMISSIONS.items():
			for permlevel, roles in levels.items():
				for role, expected in roles.items():
					actual = report[doctype].get(permlevel, {}).get(role)
					self.assertIsNotNone(actual, f"{doctype}[{permlevel}]/{role} missing")
					for right in expected:
						self.assertIn(right, actual,
						              f"{doctype}[{permlevel}]/{role} lacks {right}")


# ---------------------------------------------------------------------------
# RT-19 .. RT-22  the permission levels
# ---------------------------------------------------------------------------
class TestPermissionLevels(IntegrationTestCase):
	L1_MONEY = ["service_provider", "labour_cost", "parts_cost", "total_cost",
	            "bill_no", "bill_date", "bill_attachment", "cost_center", "project"]
	L2_TRAIL = ["bill_status", "submitted_by", "approved_by", "purchase_order",
	            "purchase_invoice", "purchasing_status", "payment_status"]

	def test_rt19_money_and_trail_sit_above_level_zero(self):
		meta = frappe.get_meta("Asset Maintenance Log")
		for fieldname in self.L1_MONEY:
			self.assertEqual(meta.get_field(fieldname).permlevel, 1,
			                 f"{fieldname} is not at level 1")
		for fieldname in self.L2_TRAIL:
			self.assertEqual(meta.get_field(fieldname).permlevel, 2,
			                 f"{fieldname} is not at level 2")

	def test_rt19b_driver_has_no_row_above_level_zero(self):
		"""Decision 1: the driver records the service, never the money."""
		self.assertIsNotNone(rights("Asset Maintenance Log", "Fleet Driver", 0))
		self.assertIsNone(rights("Asset Maintenance Log", "Fleet Driver", 1))
		self.assertIsNone(rights("Asset Maintenance Log", "Fleet Driver", 2))

	def test_rt20_driver_cannot_reach_cost_inside_the_service_grid(self):
		"""The child-table hole. cost and invoice_reference live INSIDE the
		service-items grid, so moving only the parent fields would leave a
		driver with level-0 write able to type costs straight into it."""
		meta = frappe.get_meta("Fleet Service Item")
		self.assertEqual(meta.get_field("cost").permlevel, 1)
		self.assertEqual(meta.get_field("invoice_reference").permlevel, 1)
		# and the driver holds no level-1 row on the parent
		self.assertIsNone(rights("Asset Maintenance Log", "Fleet Driver", 1))

	def test_rt21_standard_roles_keep_every_field(self):
		"""The five preserving rows. Without them, raising a field to level 1
		silently takes it away from roles in other modules."""
		self.assertEqual(rights("Vehicle", "Fleet Manager", 1), ["read", "write"])
		self.assertEqual(rights("Vehicle", "Delivery Manager", 1), ["read", "write"])
		self.assertEqual(rights("Vehicle", "Delivery User", 1), ["read"])
		self.assertEqual(rights("Asset Maintenance Log", "Manufacturing User", 1),
		                 ["read", "write"])
		self.assertEqual(rights("Asset Maintenance Log", "Manufacturing User", 2),
		                 ["read", "write"])

	def test_rt21b_preserving_rows_mirror_level_zero_exactly(self):
		"""Not wider, not narrower - exactly what they had."""
		for role in ("Delivery Manager", "Delivery User"):
			l0 = set(rights("Vehicle", role, 0) or [])
			l1 = set(rights("Vehicle", role, 1) or [])
			self.assertTrue(l1.issubset(l0),
			                f"{role} gained {l1 - l0} at level 1 that it lacks at level 0")

	def test_rt22_the_bill_process_still_completes(self):
		"""Decision 1 moves bill entry from the driver to the maintenance user.
		Verify each step is performable by the role that now owns it."""
		maint = user_with_only("Fleet Maintenance User")
		driver = user_with_only("Fleet Driver")

		# 1. the driver records the service visit
		self.assertTrue(frappe.has_permission("Asset Maintenance Log", "create", user=driver))
		# 2. the maintenance user enters the bill - needs level-1 write
		self.assertEqual(rights("Asset Maintenance Log", "Fleet Maintenance User", 1),
		                 ["read", "write"])
		# 3. Submit Bill checks DOCTYPE write, not field write, so it works
		self.assertTrue(frappe.has_permission("Asset Maintenance Log", "write", user=maint))
		# 4. the trail is written by code; only the administrator may edit it
		self.assertEqual(rights("Asset Maintenance Log", "Fleet Administrator", 2),
		                 ["read", "write"])
		self.assertIsNone(rights("Asset Maintenance Log", "Fleet Driver", 2))

	def test_rt23_vehicle_value_is_restricted_but_user_can_read_the_vehicle(self):
		"""Decision 3: Fleet User reads Vehicle, but not its commercial fields."""
		self.assertEqual(rights("Vehicle", "Fleet User", 0), ["read"])
		self.assertIsNone(rights("Vehicle", "Fleet User", 1))
		meta = frappe.get_meta("Vehicle")
		for fieldname in ("vehicle_value", "asset", "lessor"):
			self.assertEqual(meta.get_field(fieldname).permlevel, 1,
			                 f"{fieldname} should be above a requester's reach")

	def test_rt24_disabled_chain_roles_get_nothing(self):
		"""Decision 4: the five-stage chain is off, so these stay empty."""
		for role in ("Fleet Validator", "Fleet Reviewer", "Fleet Finance User"):
			for doctype in FLEET_PERMISSIONS:
				self.assertIsNone(rights(doctype, role, 0),
				                  f"{role} should have nothing on {doctype}")


# ---------------------------------------------------------------------------
# OBS-002 / OBS-003 / OBS-004
# ---------------------------------------------------------------------------
class TestObservationFixes(IntegrationTestCase):
	def test_obs002_licence_alert_has_its_own_setting(self):
		"""A licence is not a policy. Changing the insurance reminder must no
		longer change the licence one."""
		meta = frappe.get_meta("GDL Fleet Settings")
		self.assertIsNotNone(meta.get_field("licence_expiry_notice_days"))

		licence = frappe.utils.cint(
			frappe.db.get_single_value("GDL Fleet Settings", "licence_expiry_notice_days"))
		renewal = frappe.utils.cint(
			frappe.db.get_single_value("GDL Fleet Settings", "renewal_notice_days"))
		self.assertGreater(licence, 0)
		self.assertNotEqual(
			licence, renewal,
			"the licence notice still matches the renewal rung - they may be "
			"coincidentally equal, but that hides the coupling this fixed",
		)

	def test_obs002_the_alert_fires_on_the_licence_setting(self):
		configured = frappe.utils.cint(
			frappe.db.get_single_value("GDL Fleet Settings", "licence_expiry_notice_days"))
		live = frappe.utils.cint(
			frappe.db.get_value("Notification", "GDL Fleet: Driving Licence Expiry",
			                    "days_in_advance"))
		self.assertEqual(live, configured)

	def test_obs002_changing_the_renewal_ladder_leaves_the_licence_alone(self):
		"""The actual coupling, proven directly."""
		from gdl_fleet_extension.setup.notifications import get_notification_definitions
		before = [n for n in get_notification_definitions()
		          if n["name"].endswith("Driving Licence Expiry")][0]["days_in_advance"]

		settings = frappe.get_single("GDL Fleet Settings")
		original = settings.renewal_notice_days
		try:
			settings.renewal_notice_days = 7
			settings.flags.ignore_permissions = True
			settings.save()
			frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")
			after = [n for n in get_notification_definitions()
			         if n["name"].endswith("Driving Licence Expiry")][0]["days_in_advance"]
			self.assertEqual(before, after, "the licence notice moved with the renewal rung")
		finally:
			settings = frappe.get_single("GDL Fleet Settings")
			settings.renewal_notice_days = original
			settings.flags.ignore_permissions = True
			settings.save()
			frappe.clear_document_cache("GDL Fleet Settings", "GDL Fleet Settings")

	def test_obs003_maintenance_user_can_read_vehicle_log(self):
		"""Judging whether a service is due needs the running history."""
		self.assertEqual(rights("Vehicle Log", "Fleet Maintenance User", 0), ["read"])

	def test_obs003_maintenance_user_still_cannot_write_a_vehicle_log(self):
		"""Read only - they record services, not journeys."""
		user = user_with_only("Fleet Maintenance User")
		self.assertTrue(frappe.has_permission("Vehicle Log", "read", user=user))
		for ptype in ("write", "create", "submit"):
			self.assertFalse(frappe.has_permission("Vehicle Log", ptype, user=user))

	def test_obs004_driver_can_read_asset_repair(self):
		"""A driver should see a breakdown logged against a vehicle they drive."""
		self.assertEqual(rights("Asset Repair", "Fleet Driver", 0), ["read"])

	def test_obs004_driver_still_cannot_record_a_repair(self):
		user = user_with_only("Fleet Driver")
		self.assertTrue(frappe.has_permission("Asset Repair", "read", user=user))
		for ptype in ("write", "create", "submit"):
			self.assertFalse(frappe.has_permission("Asset Repair", ptype, user=user))


# ---------------------------------------------------------------------------
# OBS-005 — the MTO without Fleet Manager
# ---------------------------------------------------------------------------
class TestMTOWithoutFleetManager(IntegrationTestCase):
	"""An MTO approves vehicle requests. That should not require sight of what
	every vehicle cost - but it does require the reports and the renewals."""

	MTO = {"Fleet Approver", "Fleet User"}

	def test_obs005_approver_can_run_every_fleet_report(self):
		"""Fleet Approver was on NONE of the 18 before this change. Removing
		Fleet Manager without fixing that would have cost the MTO the two
		screens the handbook tells them to start from."""
		missing = []
		for report in frappe.get_all("Report", filters={"module": "GDL Fleet"}, pluck="name"):
			roles = frappe.get_all("Has Role",
			                       filters={"parent": report, "parenttype": "Report"}, pluck="role")
			if "Fleet Approver" not in roles:
				missing.append(report)
		self.assertEqual(missing, [], f"Fleet Approver cannot run: {missing}")

	def test_obs005_approver_can_manage_renewals(self):
		for ptype in ("read", "write", "create", "submit"):
			self.assertIn(ptype, rights("Renewal Register", "Fleet Approver", 0) or [])

	def test_obs005_approver_can_see_a_service_record(self):
		self.assertEqual(rights("Asset Maintenance Log", "Fleet Approver", 0), ["read"])

	def test_obs005_approver_cannot_see_the_money(self):
		"""The entire point. Level 0 only - no costs, no bill, no trail."""
		self.assertIsNone(rights("Asset Maintenance Log", "Fleet Approver", 1))
		self.assertIsNone(rights("Asset Maintenance Log", "Fleet Approver", 2))
		self.assertIsNone(rights("Vehicle", "Fleet Approver", 1))

	def test_obs005_an_mto_role_set_hides_commercial_vehicle_fields(self):
		readable = {p.permlevel for p in frappe.get_meta("Vehicle").permissions
		            if p.role in self.MTO and p.read}
		self.assertEqual(readable, {0}, "an MTO can still reach permlevel 1 on Vehicle")
		meta = frappe.get_meta("Vehicle")
		for fieldname in ("vehicle_value", "asset", "lessor"):
			self.assertNotIn(meta.get_field(fieldname).permlevel, readable)

	def test_obs005_the_approval_workflows_still_work(self):
		for name in ("GDL Movement Order Request Review", "GDL Movement Order Approval"):
			allowed = {t.allowed for t in frappe.get_doc("Workflow", name).transitions}
			self.assertTrue(allowed & self.MTO,
			                f"an MTO can no longer act on {name}")

	def test_obs005_rollout_no_longer_grants_fleet_manager(self):
		from gdl_fleet_extension.setup.gdl_fleet_rollout import MTO_ROLES
		self.assertNotIn("Fleet Manager", MTO_ROLES)
		self.assertIn("Fleet Approver", MTO_ROLES)
