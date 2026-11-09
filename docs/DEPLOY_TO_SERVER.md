# Installing GDL Fleet Extension on the server

Server: `94.136.184.120` · Package built 2026-11-05

> Run these yourself. Every command is meant to be read before it is run.

---

## 0. Before anything — rotate the root password

The root password was sent in a chat message. Treat it as compromised.

```bash
passwd root
```

While you are there, consider disabling password login for root entirely and
using a key instead (`PermitRootLogin prohibit-password` in `/etc/ssh/sshd_config`).

---

## 1. Read this first — what installing this app does to the site

This is **not** a self-contained app that sits in a corner. Installing it changes
things that the rest of your ERPNext shares. On a site already in production, the
following all happen on `install-app`:

| What | Where it lands | Reversible? |
|---|---|---|
| Writes permissions onto **26 doctypes** — including `Item`, `User`, `Purchase Invoice`, `Employee`, `Account`, `Company`, `Warehouse`, `Address` | Custom DocPerm | See the warning below |
| Makes **Vehicle an Accounting Dimension** | adds a Vehicle field to every accounting doctype | hard to undo |
| Creates **7 GDL locations** (Head Office, Jamjee, Dochula, Dagapela, Gedu, Samcholing, Jigmeling) | Location tree | delete manually |
| **Hides 24 fields** on `Asset Maintenance Log` for every user | Property Setters | yes, delete the rows |
| Adds custom fields to `Vehicle`, `Driver`, `Employee`, `Vehicle Log`, `Asset Maintenance Log`, `Asset Repair`, `Purchase Invoice` | Custom Fields | yes |
| Shows employee **names instead of IDs** in every Employee link, site-wide | Property Setter on Employee | yes |
| Creates 3 workflows, notifications, a dashboard, roles, and GDL Fleet Settings | own records | yes |
| Runs **25 patches** | data migrations | no |

### The one that deserves a decision, not a glance

Granting a permission on a standard doctype makes frappe copy that doctype's
**shipped** permissions into Custom DocPerm and read those from then on. After
this install, future ERPNext upgrades will **no longer update the standard
permissions** of those 26 doctypes on this site — `Item`, `User`,
`Purchase Invoice` and `Employee` among them.

That was an acceptable trade on a fleet-only staging site. On a production
ERPNext that other departments use, it is a decision for whoever owns that
system. It is undone per doctype with
`frappe.permissions.reset_perms("<doctype>")`, but that also drops the fleet
grants.

**If this server runs anything other than the GDL fleet, stop and have that
conversation before step 5.**

---

## 2. Pre-flight checks

Log in as yourself, then:

```bash
cd ~/frappe-bench && bench version
```

You need **frappe 16**, **erpnext 16** and **hrms 16**. `hrms` is not optional —
the app declares `required_apps = ["frappe/erpnext", "frappe/hrms"]` and install
fails without it.

```bash
./env/bin/python --version
```

**This is the likely blocker.** The app's `pyproject.toml` declares
`requires-python = ">=3.14"`. If the server reports 3.11 or 3.12, `pip` will
refuse to install it. That version floor is not something the code actually
needs — it came from the bench scaffold. If the server is older, tell me the
version and I will relax the floor and rebuild the package. Do not edit it on
the server.

```bash
bench --site <your-site> list-apps
ls ~/frappe-bench/sites
```

Confirm the site name, and that `gdl_fleet_extension` is not already there.

---

## 3. Back up — non-negotiable

```bash
cd ~/frappe-bench && bench --site <your-site> backup --with-files
```

Note the path it prints. Copy it off the server before continuing:

```bash
# from your own machine
scp root@94.136.184.120:~/frappe-bench/sites/<your-site>/private/backups/<file>.sql.gz .
```

A database backup is the only thing that undoes step 5 cleanly.

---

## 4. Copy the app across

From **this** machine:

```bash
scp /home/gopynath/erpnext-v16/frappe-bench/gdl_fleet_extension-20261105.tar.gz root@94.136.184.120:/tmp/
```

On the **server**, verify it arrived intact before unpacking:

```bash
sha256sum /tmp/gdl_fleet_extension-20261105.tar.gz
```

Expected:

```
53047364acc3b2db3b9d9bd134280a2d25316575adaacc200356a853787d2c3a
```

If it does not match, the copy is corrupt — delete it and scp again.

```bash
mkdir -p /tmp/gdl-app && tar -xzf /tmp/gdl_fleet_extension-20261105.tar.gz -C /tmp/gdl-app
cd ~/frappe-bench && bench get-app /tmp/gdl-app/gdl_fleet_extension
```

`get-app` only puts the app on the bench and pip-installs it. **No site is
touched yet** — nothing has changed for your users at this point.

---

## 5. Install onto the site

This is the step that changes the site. Everything in section 1 happens here.

```bash
cd ~/frappe-bench && bench --site <your-site> install-app gdl_fleet_extension
```

Then:

```bash
bench --site <your-site> migrate
bench build --app gdl_fleet_extension
bench --site <your-site> clear-cache
```

If you run under supervisor:

```bash
sudo supervisorctl restart all
```

---

## 6. Verify

```bash
cd ~/frappe-bench && bench --site <your-site> list-apps
```

```bash
bench --site <your-site> console
```

```python
import frappe
print(frappe.db.count("Vehicle"), "vehicles")
print(frappe.db.count("Location"), "locations")
print([r.name for r in frappe.get_all("Role", filters={"name": ("like", "Fleet%")})])
print(frappe.get_meta("Asset Maintenance Log").get_field("vehicle").reqd)
```

Then open the desk and check the **GDL Fleet** workspace appears.

---

## 7. If it goes wrong

`install-app` is not cleanly reversible. The honest rollback is the backup:

```bash
cd ~/frappe-bench && bench --site <your-site> restore <path-to-backup>.sql.gz
```

`bench --site <your-site> uninstall-app gdl_fleet_extension` removes the app's
own doctypes but leaves the custom fields, property setters, Custom DocPerm rows
and the accounting dimension behind. Use the backup.

---

## 8. After the install — things that still need GDL's input

These are blank or unset and were never decided. None of them stop the install;
each stops one process the first time somebody tries it.

- **Location Officers** — the MTO per location, and which one is Head Office.
  Without it, location-based approval falls back to the role check alone.
- **BOD Supplier / STCBL Supplier** — no fuel claim can be raised until both are
  named in GDL Fleet Settings.
- **User Permission → Location** for each requester, so they are offered their
  own site's vehicles.
- **Supplier Group on STCBL** — blocks the Purchase Invoice on a fuel claim.
- **Fleet role assignments** — the roles are created empty. Nobody holds them
  until you assign them.
