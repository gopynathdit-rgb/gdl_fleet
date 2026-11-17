# Copyright (c) 2026, GDL and contributors
"""The repeating page header and footer on the two printed forms.

GDL: "add header footer in my pol abstract report and movement order pdf
reports". Header: the company name and logo. Footer: page X of Y and the date
it was printed.

These are `#header-html` and `#footer-html` divs. frappe extracts them from the
rendered page and hands them to wkhtmltopdf as --header-html/--footer-html, so
they repeat on every page instead of printing once at the top and bottom of a
long abstract (prepare_header_footer() in frappe/utils/pdf.py).
"""

import re

import frappe
from frappe.tests import IntegrationTestCase

FORMATS = (("POL Abstract", "POL Abstract"),
           ("Movement Order", "Vehicle Movement Order"))


def a_document(doctype):
	return frappe.db.get_value(doctype, {"docstatus": ("<", 2)}, "name",
	                           order_by="creation desc")


class TestPrintHeaderAndFooter(IntegrationTestCase):
	def rendered(self, doctype, print_format):
		name = a_document(doctype)
		if not name:
			self.skipTest(f"no {doctype} on this site")
		return frappe.get_print(doctype, name, print_format=print_format)

	def block(self, html, html_id):
		found = re.search(rf'<div id="{html_id}".*?</div>', html, re.S)
		return found.group(0) if found else None

	def test_both_formats_carry_a_header_and_a_footer(self):
		for doctype, print_format in FORMATS:
			with self.subTest(print_format=print_format):
				html = self.rendered(doctype, print_format)
				self.assertIsNotNone(self.block(html, "header-html"),
				                     f"{print_format} has no page header")
				self.assertIsNotNone(self.block(html, "footer-html"),
				                     f"{print_format} has no page footer")

	def test_the_ids_are_exactly_what_frappe_looks_for(self):
		"""frappe finds these by id. A renamed id is a silently missing
		header - the page still prints, just without it."""
		for doctype, print_format in FORMATS:
			with self.subTest(print_format=print_format):
				html = self.rendered(doctype, print_format)
				self.assertIn('id="header-html"', html)
				self.assertIn('id="footer-html"', html)

	def test_the_header_names_the_company(self):
		for doctype, print_format in FORMATS:
			with self.subTest(print_format=print_format):
				header = self.block(self.rendered(doctype, print_format), "header-html")
				text = " ".join(re.sub(r"<[^>]+>", " ", header).split())
				self.assertTrue(text, f"{print_format}'s header is empty")

	def test_the_footer_carries_page_numbers_and_the_date(self):
		"""wkhtmltopdf fills .page and .topage itself; the spans must be there
		for it to find."""
		for doctype, print_format in FORMATS:
			with self.subTest(print_format=print_format):
				footer = self.block(self.rendered(doctype, print_format), "footer-html")
				self.assertIn('class="page"', footer)
				self.assertIn('class="topage"', footer)
				self.assertRegex(footer, r"Printed \d{2}\.\d{2}\.\d{4}")

	def test_the_page_count_is_hidden_on_screen_only(self):
		"""Empty .page spans read as "Page  of  " in the HTML preview, so that
		part is marked visible-pdf - frappe strips the class in the PDF."""
		for doctype, print_format in FORMATS:
			with self.subTest(print_format=print_format):
				html = self.rendered(doctype, print_format)
				footer = self.block(html, "footer-html")
				self.assertIn("visible-pdf", footer)
				self.assertIn(".gdl-pf .visible-pdf { display: none; }", html)

	def test_the_pol_mark_is_in_the_header_and_not_printed_twice(self):
		"""It moved into the page header; leaving it in the title table too
		would put two of them on page one.

		A company with no logo uploaded falls back to its abbreviation as a
		wordmark - that is the designed behaviour, not a missing logo, so this
		accepts either mark.
		"""
		html = self.rendered("POL Abstract", "POL Abstract")
		header = self.block(html, "header-html")

		# MARKUP only. The <style> blocks still define .pol-wordmark and
		# .pol-head-logo, and matching a CSS rule proves nothing about what is
		# drawn on the page - an earlier version of this test failed on exactly
		# that.
		body = re.sub(r"<style.*?</style>", "", html.replace(header, ""), flags=re.S)

		self.assertTrue("<img" in header or "pol-wordmark" in header,
		                "the header carries neither a logo nor a wordmark")
		self.assertNotIn("pol-head-logo", body,
		                 "the old logo cell is still drawn in the sheet as well")
		self.assertNotIn("pol-wordmark", body,
		                 "the wordmark is drawn in the sheet as well as the header")


class TestCompanyLogoEmbedding(IntegrationTestCase):
	"""GDL: "logo is not comming" - an empty box in the page header.

	Three things were wrong at once, and the file being absent is the one that
	actually mattered: this staging database was restored without its files
	directory, so every File record points at nothing on disk.
	"""

	def setUp(self):
		from gdl_fleet_extension.utils import branding
		self.branding = branding
		self.company = frappe.db.get_value("Company", {}, "name")

	def test_a_missing_file_gives_nothing_rather_than_a_broken_image(self):
		"""The File row can exist while the image does not. An <img> pointing
		at it renders as an empty box - which is exactly what GDL saw."""
		original = frappe.db.get_value("Company", self.company, "company_logo")
		try:
			frappe.db.set_value("Company", self.company, "company_logo",
			                    "/private/files/does-not-exist-anywhere.jpg")
			self.assertIsNone(self.branding.company_logo_data_uri(self.company))
		finally:
			frappe.db.set_value("Company", self.company, "company_logo", original)

	def test_no_company_gives_nothing(self):
		self.assertIsNone(self.branding.company_logo_data_uri(None))
		self.assertIsNone(self.branding.company_logo_data_uri(""))

	def test_a_real_file_comes_back_embedded(self):
		"""A data: URI needs no session, no escaped URL and no reachable site -
		the three ways a linked logo failed here."""
		import base64
		import os

		folder = frappe.get_site_path("public", "files")
		os.makedirs(folder, exist_ok=True)
		name = "gdl-test-logo.png"
		# a 1x1 PNG
		blob = base64.b64decode(
			"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
		path = os.path.join(folder, name)
		with open(path, "wb") as f:
			f.write(blob)

		original = frappe.db.get_value("Company", self.company, "company_logo")
		try:
			frappe.db.set_value("Company", self.company, "company_logo", f"/files/{name}")
			uri = self.branding.company_logo_data_uri(self.company)
			self.assertIsNotNone(uri, "a logo that is on disk was not embedded")
			self.assertTrue(uri.startswith("data:image/png;base64,"))
			self.assertIn(base64.b64encode(blob).decode(), uri)
		finally:
			frappe.db.set_value("Company", self.company, "company_logo", original)
			os.remove(path)

	def test_it_cannot_be_walked_out_of_the_site_folder(self):
		"""The value is stored data. Nothing typed into that field should be
		able to read a file elsewhere on the machine."""
		original = frappe.db.get_value("Company", self.company, "company_logo")
		try:
			for attempt in ("/files/../../../../etc/passwd",
			                "/private/files/../../site_config.json"):
				frappe.db.set_value("Company", self.company, "company_logo", attempt)
				self.assertIsNone(self.branding.company_logo_data_uri(self.company),
				                  f"{attempt} escaped the site folder")
		finally:
			frappe.db.set_value("Company", self.company, "company_logo", original)

	def test_the_header_never_renders_an_empty_img(self):
		"""Without a logo the header shows a wordmark. An <img> with an empty
		or missing src is the box GDL photographed."""
		for doctype, print_format in FORMATS:
			name = a_document(doctype)
			if not name:
				continue
			with self.subTest(print_format=print_format):
				html = frappe.get_print(doctype, name, print_format=print_format)
				header = re.search(r'<div id="header-html".*?</div>', html, re.S).group(0)
				self.assertNotRegex(header, r'<img[^>]+src=""')
				self.assertNotRegex(header, r'<img(?![^>]*src=)')


class TestPolSheetAlignment(IntegrationTestCase):
	"""GDL: "alignment is not good in pdf"."""

	def rendered(self):
		name = a_document("POL Abstract")
		if not name:
			self.skipTest("no POL Abstract on this site")
		return frappe.get_print("POL Abstract", name, print_format="POL Abstract")

	def test_the_title_is_not_offset_for_a_logo_that_has_moved(self):
		"""pol-head-mid carried padding-left:90px to balance the logo cell on
		the right. The logo moved to the page header; the offset then pushed
		the title off-centre with nothing to balance."""
		self.assertNotIn("padding-left: 90px", self.rendered())

	def test_the_summary_cells_are_middle_aligned(self):
		"""Each label level with its grey box.

		No !important any more. That was there to beat Bootstrap's `.label`,
		which set vertical-align: baseline on these cells - and it won for that
		one property while three others still applied. Renaming the class
		removed the fight, so the plain rule is enough.
		"""
		html = self.rendered()
		self.assertRegex(html, r"\.pol-sheet \.pol-summary td \{[^}]*vertical-align: middle")
		self.assertNotIn("vertical-align: middle !important", html)

	def test_the_grey_boxes_keep_their_padding(self):
		"""Every .pol-summary rule must be scoped the same way. Scoping only
		the `td` rule made it outrank the box rule and flattened the boxes - a
		regression introduced while fixing the alignment."""
		html = self.rendered()
		self.assertRegex(html, r"\.pol-sheet \.pol-summary \.pol-box \{[^}]*padding: 2px 6px")


class TestPrintFormatClassNames(IntegrationTestCase):
	"""No print-format class may collide with the stylesheet frappe ships.

	GDL photographed a box drawn around every label in the POL PDF. The cause
	was `class="label"` - Bootstrap's own badge component, which frappe's print
	stylesheet ships. It was restyling those cells four ways at once:

	    display: inline            broke the table cell
	    font-size: 75%             shrank the text
	    vertical-align: baseline   pushed the label off its grey box
	    border: 1px solid #000     the box itself - @media print ONLY

	That last one is why it never appeared on screen and only in the PDF, and
	why two rounds of fixing the alignment missed it.

	This checks the real hazard rather than a naming convention. A first
	version demanded a prefix on every class and failed on `right`, `center`
	and the movement order's short column names - none of which Bootstrap
	defines, so none of which could ever have caused this. Collision is what
	matters, and checking it against the actual stylesheet means this also
	catches a name that only becomes dangerous when frappe next ships a
	different Bootstrap.
	"""

	# Deliberately frappe's or wkhtmltopdf's own, and used as such.
	BORROWED = {"page", "topage", "visible-pdf", "hidden-pdf", "print-format"}

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.stylesheet = cls._read_print_stylesheet()

	@staticmethod
	def _read_print_stylesheet():
		import glob
		import os

		import frappe
		pattern = os.path.join(frappe.local.sites_path, "assets", "frappe", "dist",
		                       "css", "print.bundle.*.css")
		found = glob.glob(pattern)
		if not found:
			return None
		with open(found[0], encoding="utf-8") as f:
			return f.read()

	def format_files(self):
		import os

		import gdl_fleet_extension
		root = os.path.join(os.path.dirname(gdl_fleet_extension.__file__),
		                    "gdl_fleet", "print_format")
		for folder in sorted(os.listdir(root)):
			path = os.path.join(root, folder, f"{folder}.html")
			if os.path.isfile(path):
				yield folder, path

	def classes_used(self, path):
		with open(path, encoding="utf-8") as f:
			source = f.read()
		# Only MARKUP counts. A <style> block and a Jinja comment both mention
		# class names without applying any - the comment explaining this very
		# bug contains the word that caused it, and tripped an earlier version
		# of this scan.
		source = re.sub(r"<style.*?</style>", "", source, flags=re.S)
		source = re.sub(r"\{#-.*?-#\}", "", source, flags=re.S)
		source = re.sub(r"<!--.*?-->", "", source, flags=re.S)
		for attr in re.findall(r'class="([^"{}]+)"', source):
			yield from attr.split()

	def defined_in_stylesheet(self, name):
		return re.search(r"(^|[,{}\s])\." + re.escape(name) + r"(?![\w-])", self.stylesheet,
		                 re.M) is not None

	def test_no_class_collides_with_frappes_stylesheet(self):
		if not self.stylesheet:
			self.skipTest("print.bundle css not built on this site")

		checked = 0
		for folder, path in self.format_files():
			for name in self.classes_used(path):
				checked += 1
				if name in self.BORROWED:
					continue
				with self.subTest(print_format=folder, css_class=name):
					self.assertFalse(
						self.defined_in_stylesheet(name),
						f"{folder}: class \"{name}\" is also defined in the stylesheet "
						f"frappe ships, so it silently inherits that styling. Prefix it "
						f"(pol-, mo-, gdl-). This is what put a border round every POL "
						f"label in the PDF - and only in the PDF, because the rule was "
						f"inside @media print.",
					)
		self.assertGreater(checked, 0, "no classes were checked - the scan is broken")

	def test_the_check_would_catch_the_name_that_caused_this(self):
		"""Proves it bites rather than passing vacuously."""
		if not self.stylesheet:
			self.skipTest("print.bundle css not built on this site")
		self.assertTrue(self.defined_in_stylesheet("label"),
		                "the scan cannot see Bootstrap's .label at all")
		self.assertFalse(self.defined_in_stylesheet("pol-label"),
		                 "the prefixed name should NOT collide")
