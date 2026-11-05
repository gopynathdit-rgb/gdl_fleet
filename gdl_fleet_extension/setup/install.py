# Copyright (c) 2026, GDL and contributors

import frappe

from gdl_fleet_extension.setup.accounting_dimension import setup_vehicle_dimension
from gdl_fleet_extension.setup.fleet_permissions import setup_fleet_permissions
from gdl_fleet_extension.setup.dashboard import setup_dashboard
from gdl_fleet_extension.setup.driver_fields import setup_driver_customisations
from gdl_fleet_extension.setup.fleet_settings import seed_fleet_settings
from gdl_fleet_extension.setup.maintenance_fields import setup_maintenance_customisations
from gdl_fleet_extension.setup.notifications import create_notifications
from gdl_fleet_extension.setup.people_display import setup_people_display
from gdl_fleet_extension.setup.roles import create_roles
from gdl_fleet_extension.setup.sites import create_site_locations
from gdl_fleet_extension.setup.pol_accounting_fields import setup_pol_accounting_fields
from gdl_fleet_extension.setup.desktop_icon import setup_desktop_icon
from gdl_fleet_extension.setup.maintenance_purchasing_fields import setup_maintenance_purchasing_fields
from gdl_fleet_extension.setup.maintenance_simplification import setup_simple_maintenance_form
from gdl_fleet_extension.setup.workspace_visibility import setup_workspace_visibility
from gdl_fleet_extension.setup.workflows import (
	create_pol_workflow,
	create_movement_order_workflow,
	create_movement_request_workflow,
)
from gdl_fleet_extension.setup.vehicle_log_fields import setup_vehicle_log_customisations
from gdl_fleet_extension.setup.vehicle_fields import (
	backfill_vehicle_ids,
	setup_vehicle_customisations,
)


def after_install():
	setup()


def after_migrate():
	setup()


def setup():
	"""Idempotent. Safe to run on install and on every migrate."""
	create_roles()
	# DEF-001: the roles must exist before a permission can reference them.
	setup_fleet_permissions()
	create_site_locations()
	setup_vehicle_customisations()
	setup_vehicle_log_customisations()
	setup_maintenance_customisations()
	setup_driver_customisations()
	backfill_vehicle_ids()
	# Phase 3: Vehicle as an Accounting Dimension. Guarded and idempotent - the
	# heavy field sync only runs when the dimension or its fields are missing.
	setup_vehicle_dimension()
	# Phase 4: approval chain as standard Workflow data (roles, never users).
	create_movement_request_workflow()
	create_movement_order_workflow()
	create_pol_workflow()
	setup_pol_accounting_fields()
	setup_workspace_visibility()
	setup_maintenance_purchasing_fields()
	# Final document 2.1.1.4: the service record holds what that section lists
	# and nothing else. Runs last so it covers every field added above.
	setup_simple_maintenance_form()
	# Links to a person show the person's name, not their record id.
	setup_people_display()
	setup_desktop_icon()
	# Phase 15: alerts are standard Notification records - no scheduler job.
	create_notifications()
	# The fleet dashboard: number cards and charts on the GDL Fleet workspace.
	setup_dashboard()
	# Phase 7: service intervals are configuration, seeded once, editable in the desk.
	seed_fleet_settings()
	frappe.db.commit()
