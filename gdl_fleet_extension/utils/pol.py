# Copyright (c) 2026, GDL and contributors
"""
POL calculation service layer.

Every formula here is taken from the customer's own POL.xlsx workbook
(sheets BG-1-A2397 and BG-1-A3812), not from a generic fuel-consumption
model. The cell formulas these reproduce are:

    Total litres          =SUM(E6:E8)
    Amount (STCBL)        =F6*E6          (typed by hand on sheet 1)
    Total KM              =D18-D16
    Total fuel consumed   =(E9+D22)-D24   <- supplied + PREVIOUS - PRESENT
    Performance per litre =D20/D30
    Fuel book balance     =D14-H9

The consumption formula is the stock equation - consumed = supplied plus
opening stock minus closing stock - and is confirmed by the workbook itself:
BG-1-A3812 carries a hand-typed performance of 9, and 2223 / 247 is exactly 9,
whereas the inverted formula would give 8.6498.

This module is deliberately free of any Frappe document dependency so the
arithmetic can be tested on its own. Everything monetary is Decimal; nothing
here uses float.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# The workbook's own display precision for KM/L. Overridable through
# GDL Fleet Settings; this is only the fallback.
DEFAULT_PERFORMANCE_PRECISION = 2


def to_decimal(value) -> Decimal:
	"""Coerce a Frappe field value to Decimal without going through float.

	Frappe hands back float for Float/Currency fields, so the value is
	stringified first - Decimal(0.1) is not 0.1, but Decimal("0.1") is.
	"""
	if value is None or value == "":
		return Decimal("0")
	if isinstance(value, Decimal):
		return value
	try:
		return Decimal(str(value))
	except (InvalidOperation, ValueError, TypeError):
		return Decimal("0")


def quantize(value, precision: int = 2) -> Decimal:
	"""Round half-up to `precision` places, the convention ERPNext money uses."""
	exponent = Decimal(1).scaleb(-int(precision))
	return to_decimal(value).quantize(exponent, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Fuel supplied
# ---------------------------------------------------------------------------
def total_litres(entries) -> Decimal:
	"""Workbook: =SUM(E6:E8). Never entered by hand."""
	return sum((to_decimal(row.get("litres")) for row in entries), Decimal("0"))


def line_amount(litres, rate, precision: int = 2) -> Decimal:
	"""Workbook: =F6*E6, rounded to currency precision.

	Used only to DEFAULT the amount. The stored amount stays overridable,
	because sheet BG-1-A2397 carries hand-entered amounts that do not equal
	the raw product (41.81 x 105.55 = 4413.0455, typed as 4413.04), and the
	customer's approved total must be preserved rather than silently
	re-rounded.
	"""
	return quantize(to_decimal(litres) * to_decimal(rate), precision)


def total_amount(entries, fieldname: str) -> Decimal:
	"""Sum of a money column across the POL entries, as stored.

	Reads whatever amount the entry actually carries, so an authorised
	override survives into the total and into the book balance.
	"""
	return sum((to_decimal(row.get(fieldname)) for row in entries), Decimal("0"))


# ---------------------------------------------------------------------------
# Distance
# ---------------------------------------------------------------------------
def total_km(opening, closing) -> Decimal:
	"""Workbook: =D18-D16.

	The caller validates closing >= opening; this returns the raw difference
	so a bad pair surfaces as a negative rather than being silently clamped.
	"""
	return to_decimal(closing) - to_decimal(opening)


# ---------------------------------------------------------------------------
# Consumption
# ---------------------------------------------------------------------------
def total_fuel_consumed(supplied, previous_tank, present_tank) -> Decimal:
	"""Workbook: =(E9+D22)-D24.

	    consumed = supplied + previous tank balance - present tank balance

	Note the order. Supplied + PRESENT - PREVIOUS is a different number and
	is not what the customer's workbook computes.
	"""
	return to_decimal(supplied) + to_decimal(previous_tank) - to_decimal(present_tank)


def performance_per_litre(km, consumed, precision: int | None = None):
	"""Workbook: =D20/D30. Distance per litre of fuel CONSUMED.

	Returns None when consumption is zero or negative - a performance figure
	is not computable there, and reporting 0 would read as a real measurement.
	Deliberately NOT km / supplied.
	"""
	consumed = to_decimal(consumed)
	if consumed <= 0:
		return None

	value = to_decimal(km) / consumed
	if precision is None:
		return value
	return quantize(value, precision)


# ---------------------------------------------------------------------------
# Fuel book balance
# ---------------------------------------------------------------------------
def fuel_book_balance(recoupment, amount, precision: int = 2, opening=0) -> Decimal:
	"""Workbook: =D14-H9 (STCBL) and =D12-G9 (BOD), plus what was left over.

	Business Blueprint, POL Management: "There is a provision to maintain the
	fuel coupon from two different fuel provider - BOD and STCBL where to
	to-date amount should be maintained."

	A coupon book is not emptied and reissued each period. Whatever was left
	unspent carries into the next one, so the balance is

	    opening (last period's closing) + recouped this period - spent this period

	`opening` defaults to 0, which is both the right answer for a vehicle's
	FIRST abstract and exactly the figure this returned before the carry
	forward existed - so no abstract already on file changes value.

	On both sample sheets the BOD amount cell is empty, so BOD book balance
	evaluates to the bare recoupment. That behaviour is preserved: a blank
	BOD amount is treated as nothing deducted, never as a fabricated figure.
	"""
	return quantize(
		to_decimal(opening) + to_decimal(recoupment) - to_decimal(amount), precision
	)


# ---------------------------------------------------------------------------
# Whole-abstract roll-up
# ---------------------------------------------------------------------------
def compute_abstract(
	entries,
	opening_km,
	closing_km,
	previous_tank_balance,
	present_tank_balance,
	recoupment_bod,
	recoupment_stcbl,
	currency_precision: int = 2,
	performance_precision: int = DEFAULT_PERFORMANCE_PRECISION,
	opening_book_balance_bod=0,
	opening_book_balance_stcbl=0,
) -> dict:
	"""Every derived figure on the POL abstract, in one pass.

	`entries` is a sequence of mappings carrying litres, rate, amount_bod and
	amount_stcbl. Returns Decimals; the caller is responsible for writing them
	onto the document.
	"""
	supplied = total_litres(entries)
	amount_bod = total_amount(entries, "amount_bod")
	amount_stcbl = total_amount(entries, "amount_stcbl")

	km = total_km(opening_km, closing_km)
	consumed = total_fuel_consumed(supplied, previous_tank_balance, present_tank_balance)

	return {
		"total_fuel_supplied": supplied,
		"total_amount_bod": quantize(amount_bod, currency_precision),
		"total_amount_stcbl": quantize(amount_stcbl, currency_precision),
		"total_km": km,
		"total_fuel_consumed": consumed,
		"performance_per_litre": performance_per_litre(km, consumed, performance_precision),
		"fuel_book_balance_bod": fuel_book_balance(
			recoupment_bod, amount_bod, currency_precision, opening_book_balance_bod
		),
		"fuel_book_balance_stcbl": fuel_book_balance(
			recoupment_stcbl, amount_stcbl, currency_precision, opening_book_balance_stcbl
		),
	}
