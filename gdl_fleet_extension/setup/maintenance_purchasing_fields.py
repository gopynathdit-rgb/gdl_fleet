# Copyright (c) 2026, GDL and contributors
"""Purchasing tracking on the STANDARD Asset Maintenance Log.

Custom fields, shipped as app data - no core file is edited.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

FIELDS = [

	# --- the external service bill the driver brings back -------------------
	{"fieldname": "gdl_bill_section", "label": "Service Bill", "fieldtype": "Section Break",
	 "insert_after": "actions_performed", "module": "GDL Fleet"},
	{"fieldname": "driver", "label": "Driver", "fieldtype": "Link", "options": "Driver",
	 "insert_after": "gdl_bill_section", "module": "GDL Fleet",
	 "description": "The driver who took the vehicle to the service centre."},
	{"fieldname": "driver_employee", "label": "Driver's Employee", "fieldtype": "Link",
	 "options": "Employee", "read_only": 1, "fetch_from": "driver.employee",
	 "insert_after": "driver", "module": "GDL Fleet"},
	{"fieldname": "bill_no", "label": "Bill / Invoice No.", "fieldtype": "Data",
	 "insert_after": "driver_employee", "module": "GDL Fleet",
	 "description": "The service centre's own invoice number, exactly as printed.",
			"permlevel": 1,
		},
	{"fieldname": "bill_date", "label": "Bill Date", "fieldtype": "Date",
	 "insert_after": "bill_no", "module": "GDL Fleet",
			"permlevel": 1,
		},
	{"fieldname": "gdl_bill_cb", "fieldtype": "Column Break",
	 "insert_after": "bill_date", "module": "GDL Fleet"},
	{"fieldname": "bill_attachment", "label": "Bill Attachment", "fieldtype": "Attach",
	 "insert_after": "gdl_bill_cb", "module": "GDL Fleet",
	 "description": "A scan or photograph of the service centre's bill.",
			"permlevel": 1,
		},
	{"fieldname": "bill_status", "label": "Bill Status", "fieldtype": "Select",
	 "options": "Draft\nService Completed\nBill Submitted\nPending Approval\nApproved\nPayment Processed\nRejected",
	 "default": "Draft", "read_only": 1, "in_standard_filter": 1, "no_copy": 1,
	 "insert_after": "bill_attachment", "module": "GDL Fleet",
			"permlevel": 2,
		},
	{"fieldname": "submitted_by", "label": "Submitted By", "fieldtype": "Link", "options": "User",
	 "read_only": 1, "no_copy": 1, "insert_after": "bill_status", "module": "GDL Fleet",
			"permlevel": 2,
		},
	{"fieldname": "submission_date", "label": "Submission Date", "fieldtype": "Datetime",
	 "read_only": 1, "no_copy": 1, "insert_after": "submitted_by", "module": "GDL Fleet",
			"permlevel": 2,
		},
	{"fieldname": "approved_by", "label": "Approved By", "fieldtype": "Link", "options": "User",
	 "read_only": 1, "no_copy": 1, "insert_after": "submission_date", "module": "GDL Fleet",
			"permlevel": 2,
		},
	{"fieldname": "rejection_reason", "label": "Rejection Reason", "fieldtype": "Small Text",
	 "no_copy": 1, "depends_on": "eval:doc.bill_status=='Rejected'",
	 "insert_after": "approved_by", "module": "GDL Fleet",
			"permlevel": 2,
		},
	{"fieldname": "gdl_purchasing_section", "label": "Purchasing", "fieldtype": "Section Break",
	 "insert_after": "actions_performed", "module": "GDL Fleet"},
	{"fieldname": "purchase_order", "label": "Purchase Order", "fieldtype": "Link",
	 "options": "Purchase Order", "read_only": 1, "no_copy": 1,
	 "insert_after": "gdl_purchasing_section", "module": "GDL Fleet",
			"permlevel": 2,
		},
	{"fieldname": "purchasing_status", "label": "Purchasing Status", "fieldtype": "Select",
	 "options": "\nNot Required\nPending\nOrdered\nInvoiced\nFailed", "read_only": 1, "no_copy": 1,
	 "in_standard_filter": 1, "insert_after": "purchase_order", "module": "GDL Fleet",
			"permlevel": 2,
		},
	{"fieldname": "purchase_invoice", "label": "Purchase Invoice", "fieldtype": "Link",
	 "options": "Purchase Invoice", "read_only": 1, "no_copy": 1,
	 "insert_after": "purchasing_status", "module": "GDL Fleet",
			"permlevel": 2,
		},
	{"fieldname": "gdl_purchasing_cb", "fieldtype": "Column Break",
	 "insert_after": "purchase_invoice", "module": "GDL Fleet"},
	{"fieldname": "payment_status", "label": "Payment Status", "fieldtype": "Select",
	 "options": "\nNot Invoiced\nUnpaid\nPartly Paid\nPaid\nOverdue\nCancelled",
	 "read_only": 1, "no_copy": 1, "in_standard_filter": 1,
	 "insert_after": "gdl_purchasing_cb", "module": "GDL Fleet",
	 "description": "Read from the Purchase Invoice. Never set by hand - the accounts are the record.",
			"permlevel": 2,
		},
	{"fieldname": "purchasing_message", "label": "Purchasing Note", "fieldtype": "Small Text",
	 "read_only": 1, "no_copy": 1, "insert_after": "gdl_purchasing_cb", "module": "GDL Fleet",
	 "description": "Why a purchase order was or was not raised.",
			"permlevel": 2,
		},
]


def setup_maintenance_purchasing_fields():
	for field in FIELDS:
		if frappe.db.exists("Custom Field",
		                    {"dt": "Asset Maintenance Log", "fieldname": field["fieldname"]}):
			continue
		create_custom_field("Asset Maintenance Log", field, ignore_validate=True)
	return True
