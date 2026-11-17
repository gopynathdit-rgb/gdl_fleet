# Copyright (c) 2026, GDL and contributors
"""The company logo, embedded rather than linked.

GDL, looking at the first PDF with a page header: "logo is not comming" - an
empty box where the mark should be.

A linked <img src="/private/files/..."> is fetched by wkhtmltopdf over HTTP
from the site, and that fails here for three separate reasons:

  * GDL's logo is in /private/files, which needs an authenticated session;
  * its filename contains a space, which breaks an unescaped URL;
  * the page header and footer are written to their own temp files, so a
    relative src has no site to resolve against at all.

A data: URI has none of those failure modes and needs no network, no session
and no correctly configured site URL. The file is read straight off disk.
"""

import base64
import mimetypes
import os

import frappe

# A logo is a few KB. Anything far larger is a photograph somebody has put in
# the wrong field, and embedding it would bloat every page of every PDF.
MAX_BYTES = 2 * 1024 * 1024


def company_logo_data_uri(company: str | None) -> str | None:
	if not company:
		return None

	logo = frappe.db.get_value("Company", company, "company_logo")
	if not logo:
		return None

	path = _local_path(logo)
	if not path or not os.path.isfile(path):
		return None

	if os.path.getsize(path) > MAX_BYTES:
		return None

	content_type = mimetypes.guess_type(path)[0] or "image/png"
	with open(path, "rb") as f:
		encoded = base64.b64encode(f.read()).decode()
	return f"data:{content_type};base64,{encoded}"


def _local_path(url: str) -> str | None:
	"""Where a /files or /private/files URL actually lives on disk.

	Only those two prefixes are accepted, and the result must stay inside the
	site folder - a stored value is data, and nothing here should be able to
	read an arbitrary file because somebody typed ../.. into a field.
	"""
	for prefix, folder in (("/private/files/", "private"), ("/files/", "public")):
		if url.startswith(prefix):
			base = os.path.realpath(frappe.get_site_path(folder, "files"))
			path = os.path.realpath(
				os.path.join(base, url[len(prefix):])
			)
			return path if os.path.commonpath([base, path]) == base else None
	return None
