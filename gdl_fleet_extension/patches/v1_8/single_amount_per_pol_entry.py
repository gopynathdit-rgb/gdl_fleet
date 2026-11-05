# Copyright (c) 2026, GDL and contributors
"""
GDL asked for one amount per fuel line instead of two.

A POL Entry used to carry Amount (BOD) and Amount (STCBL) side by side, which
meant saying twice what the Supplier already says once, and left room for a row
credited to both providers or to neither. The row now carries a single Amount
and the supplier decides which claim it lands in.

Both provider columns are kept - the claim, the book balance and every POL
report are split by provider - but they are derived now, not typed.

This fills Total Amount on rows written under the old shape. Those rows stored
the figure in amount_bod/amount_stcbl and left total_amount as their sum, so
the sum is exactly the value the single field should hold. Nothing is
recalculated from litres x rate: an approved amount that was typed by hand must
survive untouched.
"""

import frappe


def execute():
	if not frappe.db.has_column("POL Entry", "total_amount"):
		return

	rows = frappe.db.sql("""
		select name, amount_bod, amount_stcbl, total_amount
		from `tabPOL Entry`
		where ifnull(total_amount, 0) = 0
		  and (ifnull(amount_bod, 0) <> 0 or ifnull(amount_stcbl, 0) <> 0)
	""", as_dict=True)

	for row in rows:
		total = (row.amount_bod or 0) + (row.amount_stcbl or 0)
		frappe.db.set_value("POL Entry", row.name, "total_amount", total,
		                    update_modified=False)

	if rows:
		frappe.db.commit()
		print(f"  Carried the amount onto {len(rows)} existing POL line(s).")
