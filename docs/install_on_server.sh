#!/usr/bin/env bash
#
# Install GDL Fleet Extension on a server that already runs ERPNext 16.
#
#   ./install_on_server.sh <site-name>
#
# Stops at the first problem rather than half-installing. Everything before
# "POINT OF NO RETURN" is read-only or additive and touches no site.
#
set -euo pipefail

SITE="${1:-}"
REPO="git@github.com:gopynathdit-rgb/gdl_fleet.git"
APP="gdl_fleet_extension"
BENCH="$HOME/frappe-bench"

die() { echo; echo "FAILED: $*" >&2; exit 1; }
say() { echo; echo "=== $* ==="; }

[ -n "$SITE" ] || die "give the site name: ./install_on_server.sh <site-name>"
[ -d "$BENCH" ] || die "no bench at $BENCH - edit BENCH at the top of this script"
cd "$BENCH"

# ---------------------------------------------------------------- pre-flight
say "Pre-flight"
bench version | sed 's/^/  /'
./env/bin/python --version | sed 's/^/  python: /'

for required in frappe erpnext hrms; do
	line="$(bench version | grep -E "^$required " || true)"
	[ -n "$line" ] || die "$required is not installed. The app declares it as required and cannot run without it."
	major="$(echo "$line" | awk '{print $2}' | cut -d. -f1)"
	[ "$major" = "16" ] || die "$required is version $major, not 16. This app is built against v16 APIs."
	echo "  ok: $line"
done

py="$(./env/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
./env/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
	|| die "python $py is below the 3.10 this app needs"

bench --site "$SITE" list-apps >/dev/null 2>&1 || die "site '$SITE' not found on this bench"

say "Apps already on $SITE"
bench --site "$SITE" list-apps | sed 's/^/  /'

if bench --site "$SITE" list-apps | grep -qw "$APP"; then
	die "$APP is already installed on $SITE. Use 'git pull' + 'bench migrate' to update instead."
fi

# Another app on the same doctypes is the one thing this script cannot judge.
if bench --site "$SITE" list-apps | grep -qiE 'fleet|vehicle'; then
	echo
	echo "  WARNING: another fleet-looking app is on this site. Both may add fields"
	echo "           and permissions to Vehicle, Driver and Vehicle Log. Check for"
	echo "           overlap before continuing."
fi

# ------------------------------------------------------------------- backup
say "Backup (the only clean rollback)"
bench --site "$SITE" backup --with-files | sed 's/^/  /'
echo "  Copy that backup off the server before going further."

# ------------------------------------------------------------------ fetch it
say "Fetching the app"
if [ -d "apps/$APP" ]; then
	echo "  already on the bench, skipping get-app"
else
	bench get-app "$REPO"
fi

# ------------------------------------------------------- POINT OF NO RETURN
cat <<'WARN'

============================ POINT OF NO RETURN ============================
Everything so far was additive. The next step changes the SITE, and
uninstall-app does NOT fully reverse it - only the backup does.

install-app will:
  * write permissions onto 26 doctypes, including Item, User, Purchase
    Invoice, Employee, Account, Company, Warehouse and Address.
    SIDE EFFECT: frappe then reads Custom DocPerm for those doctypes and
    ignores the shipped ones, so future ERPNext upgrades will no longer
    update their standard permissions on this site.
  * make Vehicle an Accounting Dimension - a Vehicle field on every
    accounting doctype
  * create 7 GDL locations in the Location tree
  * hide 24 fields on Asset Maintenance Log, for everyone
  * show employee names instead of ids in every Employee link, site-wide
  * run 26 patches

If this server runs anything other than the GDL fleet, stop and settle that
first.
============================================================================

WARN
read -r -p "Type INSTALL to continue, anything else to stop: " answer
[ "$answer" = "INSTALL" ] || die "stopped at your request - nothing on the site was changed"

# ------------------------------------------------------------------ install
say "Installing onto $SITE"
bench --site "$SITE" install-app "$APP"
bench --site "$SITE" migrate
bench build --app "$APP"
bench --site "$SITE" clear-cache

# ------------------------------------------------------------------- verify
say "Verifying"
bench --site "$SITE" list-apps | sed 's/^/  /'
bench --site "$SITE" execute frappe.client.get_count --args '["Location"]' 2>/dev/null \
	| sed 's/^/  locations: /' || true

say "Done"
cat <<'NEXT'
Still to configure - none of these stop the install, each stops one process
the first time somebody tries it:

  * Location Officers - the MTO per location, and which is Head Office
  * BOD Supplier / STCBL Supplier - no fuel claim until both are named
  * User Permission -> Location per requester, so each sees their own fleet
  * Fleet roles are created empty - nobody holds them until you assign them
  * No fleet account has a password yet

If supervisor runs this bench:  sudo supervisorctl restart all
NEXT
