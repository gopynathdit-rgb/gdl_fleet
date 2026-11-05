# Screenshot evidence — NOT CAPTURED

**Status at 4 November 2026: no screenshot has been captured, and none could be.**

These folders are empty on purpose. This file records why, so that nobody later mistakes
an empty folder for an oversight — and so that nobody is tempted to fill it with anything
that is not a genuine browser screenshot.

## Why no screenshots exist

Two independent blockers, either one sufficient on its own.

### 1. No browser automation is available on this machine

Verified 4 November 2026:

| Tool | Result |
|---|---|
| Claude-in-Chrome extension | `list_connected_browsers` returned `[]` — no browser connected |
| Playwright (Python) | not installed |
| Playwright (Node / CLI) | not installed |
| Selenium | not installed |
| Puppeteer | not installed |
| Cypress | no binary |
| **Any browser at all** (chrome, chromium, edge, firefox) | **none installed on this machine** |

There is no browser on this host to drive, and no library to drive one with. The UAT brief
forbids installing packages without approval, so nothing was installed.

`wkhtmltoimage` **is** present, and is deliberately **not** being used. It renders HTML to
an image. Output from it would be a picture of a web page that no user ever logged into —
exactly the fabricated evidence the brief prohibits.

### 2. No fleet user has a password

Verified against `__Auth`: of 17 enabled System Users, only **two** can log in —
`Administrator`, and one real person's account carried over in the restored database.

All fourteen `@gdl.test` fleet accounts have **no password set**. The brief forbids
resetting passwords, so no named fleet user can be logged in, with or without a browser.

The one account that can log in besides Administrator belongs to a **real person**. It was
not used and must not be.

## What this means

Every test case whose evidence is a screenshot is **BLOCKED**, not failed. See
`GDL_Fleet_UAT_Execution_Report.md`.

## How to unblock

Both are needed. Either alone is not enough.

1. **Credentials.** Have an administrator set passwords for at least:
   `headoffice.mto@gdl.test`, `jamjee.mto@gdl.test`, `dochula.mto@gdl.test`,
   `jamjee.user@gdl.test` — plus, once the roles are assigned, one Fleet Driver,
   one Fleet HR Approver, one Fleet Store User, one Fleet Maintenance User and one
   Fleet Administrator.
2. **A browser.** Either connect the Chrome extension to this machine, or approve the
   installation of Playwright plus a Chromium build.

## Manual screenshot instructions

If automation is not approved, the evidence can be captured by hand. One person with the
credentials above can work through `GDL_Fleet_User_Wise_Test_Scripts.md` in a browser and
capture each step.

**Naming:** `<role folder>/TC-0NN_<short_slug>.png` — e.g.
`02_location_mto/TC-015_review_request.png`. Never overwrite an existing file.

**Capture, for each test case:** the full browser window including the URL bar and the
logged-in user shown in the top-right, so the evidence proves *who* was acting. A cropped
screenshot of a form proves nothing about permissions.

**Before capturing:** log out of Administrator completely. A screenshot taken as
Administrator is not evidence of a user permission test.

**Redact before sharing:** nothing in these flows should expose a password, a session
cookie or a third party's personal data. If a real person's name appears in a record,
blur it.
