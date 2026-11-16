# Installing GDL Fleet Extension on the server

Server: `94.136.184.120` · Package built **2026-11-09**

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
| Runs **26 patches** | data migrations | no |

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

**No longer a blocker.** The package declared `requires-python = ">=3.14"`,
which would have made `pip` refuse on the 3.11/3.12 frappe v16 is usually
deployed on. The code was checked for anything newer than 3.10 — PEP 695
generics, `type` statements, `itertools.batched`, `typing.Self` — and uses none
of it, so the floor is now `>=3.10`. Anything from 3.10 up will install.

Still worth printing: if it reports below 3.10, stop and tell me.

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

## 4. Get the app onto the server

The repo is **private**, so the server cannot clone it anonymously. Give the
server its own read-only credential - a deploy key. It is scoped to this one
repository and puts no token in any config file.

### 4a. A deploy key, on the server

```bash
ssh-keygen -t ed25519 -C "gdl-fleet-server-deploy" -f ~/.ssh/gdl_fleet_deploy -N ""
```

```bash
cat ~/.ssh/gdl_fleet_deploy.pub
```

Copy that line into the repository (not your account):
**github.com/gopynathdit-rgb/gdl_fleet → Settings → Deploy keys → Add deploy key**.
Leave *Allow write access* **unticked** - the server only ever reads.

Tell git to use that key for github.com:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/gdl_fleet_deploy
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
```

```bash
ssh -T git@github.com
```

Expect `Hi gopynathdit-rgb/gdl_fleet! You've successfully authenticated, but
GitHub does not provide shell access.` A deploy key authenticates as the
*repository*, so the name shown is the repo, not your account.

### 4b. Fetch it

```bash
cd ~/frappe-bench && bench get-app git@github.com:gopynathdit-rgb/gdl_fleet.git
```

`get-app` only puts the app on the bench and pip-installs it. **No site is
touched yet** - nothing has changed for your users at this point.

### 4c. Or, without GitHub at all

The tarball route needs no credential on the server and the package is already
built. From this machine:

```bash
scp /home/gopynath/erpnext-v16/frappe-bench/gdl_fleet_extension-20261109.tar.gz root@94.136.184.120:/tmp/
```

On the server, verify it arrived intact before unpacking:

```bash
sha256sum /tmp/gdl_fleet_extension-20261109.tar.gz
```

Expected:

```
52f84f38ac74db474462888f1cbe9ff24da126f5ff8432d5318a052f9e077d33
```

```bash
mkdir -p /tmp/gdl-app && tar -xzf /tmp/gdl_fleet_extension-20261109.tar.gz -C /tmp/gdl-app
cd ~/frappe-bench && bench get-app /tmp/gdl-app/gdl_fleet_extension
```

### Updating later

With the deploy key in place, a later update is:

```bash
cd ~/frappe-bench/apps/gdl_fleet_extension && git pull
cd ~/frappe-bench && bench --site <your-site> migrate && bench build --app gdl_fleet_extension
```

The tarball route has no update path - you would copy a new tarball each time.
That is the reason to prefer 4a/4b if the server will track changes.

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
print(frappe.get_meta("Movement Order").default_print_format)   # Vehicle Movement Order
print(frappe.get_meta("Vehicle Log").get_field("site").permlevel)   # 1
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
- **A password for each fleet account.** None of them has one yet, so nobody can
  log in to test. Set them yourself; do not ask me to.
