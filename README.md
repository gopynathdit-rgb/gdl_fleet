# GDL Fleet Extension

Extends **standard ERPNext 16 Fleet** (Vehicle, Vehicle Log, Driver) and the standard
Assets, Stock, HR and Accounting modules with GDL-specific fleet requirements.

This app **does not** duplicate any standard DocType. It adds:

* Custom fields and Property Setters on standard DocTypes
* A small number of custom DocTypes for genuine business gaps
* Workflow, Notification and Role fixtures
* Reports, a workspace and two scheduler dispatchers

It never modifies ERPNext core and posts no GL entries of its own — all value
reaches the ledger through standard vouchers.

Requires: `frappe`, `erpnext`, `hrms` (Vehicle Log lives in HRMS).
