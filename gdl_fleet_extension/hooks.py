app_name = "gdl_fleet_extension"
app_title = "GDL Fleet Extension"
app_publisher = "GDL"
app_description = "GDL Fleet Extension - extends standard ERPNext 16 Fleet"
app_email = "gopynath.dit@gmail.com"
app_license = "mit"

# Vehicle + Driver live in erpnext, Vehicle Log + Vehicle Service live in hrms.
required_apps = ["frappe/erpnext", "frappe/hrms"]

# ---------------------------------------------------------------------------
# Apps screen
#
# Puts GDL Fleet on the desk landing grid and routes it straight at the
# workspace. Without this the module is reachable only by scrolling the
# workspace list, where it sorts last.
# ---------------------------------------------------------------------------
add_to_apps_screen = [
	{
		"name": app_name,
		"title": "GDL Fleet",
		"route": "/desk/gdl-fleet",
		"has_permission": "gdl_fleet_extension.setup.workspace_visibility.has_app_permission",
	}
]

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
after_install = "gdl_fleet_extension.setup.install.after_install"
after_migrate = "gdl_fleet_extension.setup.install.after_migrate"

# ---------------------------------------------------------------------------
# Document events
#
# Additive only. The standard controllers still run; these hooks add GDL rules
# on top of them. No core controller is replaced in this phase.
# ---------------------------------------------------------------------------
doc_events = {
	"Vehicle": {
		"validate": "gdl_fleet_extension.overrides.vehicle.validate",
	},
	# Phase 7 - preventive service record (standard erpnext Assets module)
	"Asset Maintenance Log": {
		"validate": "gdl_fleet_extension.overrides.asset_maintenance.maintenance_log_validate",
		"on_submit": "gdl_fleet_extension.overrides.asset_maintenance.maintenance_log_on_submit",
		# CR3 - completion may raise a purchase order; off until configured
		"on_update_after_submit": "gdl_fleet_extension.overrides.asset_maintenance.maintenance_log_purchasing",
		"on_cancel": "gdl_fleet_extension.overrides.asset_maintenance.maintenance_log_on_cancel",
		"on_update": "gdl_fleet_extension.overrides.asset_maintenance.maintenance_log_purchasing",
	},
	# Payment status on a maintenance record is READ from the invoice, never
	# asserted by the maintenance record itself.
	"Purchase Invoice": {
		"on_submit": "gdl_fleet_extension.utils.fleet_purchase_automation.on_purchase_invoice_change",
		"on_cancel": "gdl_fleet_extension.utils.fleet_purchase_automation.on_purchase_invoice_change",
		"on_update_after_submit": "gdl_fleet_extension.utils.fleet_purchase_automation.on_purchase_invoice_change",
	},
	"Payment Entry": {
		"on_submit": "gdl_fleet_extension.utils.fleet_purchase_automation.on_payment_entry_change",
		"on_cancel": "gdl_fleet_extension.utils.fleet_purchase_automation.on_payment_entry_change",
	},
	# Phase 7 - corrective repair (standard erpnext Asset Repair)
	"Asset Repair": {
		"validate": "gdl_fleet_extension.overrides.asset_maintenance.asset_repair_validate",
		"on_submit": "gdl_fleet_extension.overrides.asset_maintenance.asset_repair_on_submit",
		"on_cancel": "gdl_fleet_extension.overrides.asset_maintenance.asset_repair_on_cancel",
	},
}

# ---------------------------------------------------------------------------
# Form scripts on STANDARD DocTypes
# ---------------------------------------------------------------------------
doctype_js = {
	"Asset Maintenance Log": "public/js/asset_maintenance_log.js",
}


# ---------------------------------------------------------------------------
# Class overrides
#
# Used only where a standard method must be REPLACED rather than added to.
# Vehicle Log qualifies: hrms' on_cancel drags the vehicle odometer backwards
# when an older log is cancelled. See overrides/vehicle_log.py.
# ---------------------------------------------------------------------------
override_doctype_class = {
	"Vehicle Log": "gdl_fleet_extension.overrides.vehicle_log.GDLVehicleLog",
}

# ---------------------------------------------------------------------------
# Fixtures
#
# Everything this app customises on a standard DocType ships as versioned
# fixture data, never as an edit to a core JSON file.
# ---------------------------------------------------------------------------
fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "GDL Fleet"]]},
	{"dt": "Property Setter", "filters": [["module", "=", "GDL Fleet"]]},
	# DEF-001: "Fleet %" also matches the STANDARD ERPNext role "Fleet Manager",
	# which this app must never export or overwrite. The ten roles it does create
	# are listed literally - not imported from setup.roles, because hooks.py is
	# read very early in the boot and importing an app module here invites a
	# circular import.
	{"dt": "Role", "filters": [["role_name", "in", [
		"Fleet Administrator", "Fleet User", "Fleet Driver", "Fleet Validator",
		"Fleet Reviewer", "Fleet Approver", "Fleet Maintenance User",
		"Fleet Store User", "Fleet Finance User", "Fleet HR Approver",
	]]]},
	{"dt": "Workflow", "filters": [["name", "like", "GDL %"]]},
	{"dt": "Workflow State", "filters": [["name", "in", [
		"Pending Validation", "Pending Review", "Pending MTO/CEO", "Pending FAS",
		"Pending Approval",
		"Assigned", "In Use", "Completed", "Cancelled",
	]]]},
	{"dt": "Workflow Action Master", "filters": [["name", "in", [
		"Submit for Validation", "Validate", "Assign Vehicle", "Start Trip", "Complete", "Cancel",
		"Submit for Approval", "Approve", "Reject", "Resubmit", "Dispatch", "Review", "Clear",
	]]]},
]


# ---------------------------------------------------------------------------
# Scheduled jobs
#
# The app ran with none of these by design. CR4 needs one: an insurance policy
# expires on a date whether or not anyone opens the record, so a form hook
# would never fire. This is the only scheduled job, it runs once a day, and it
# does nothing at all until insurance purchasing is switched on in settings.
# ---------------------------------------------------------------------------
scheduler_events = {
	"daily": [
		"gdl_fleet_extension.utils.fleet_purchase_automation.daily_fleet_purchasing",
	]
}
