# Odoo 19 Shipment Requests

A focused logistics module for registering shipment requests, managing cargo,
advancing delivery stages, and printing a driver shipment order.

The installable addon is [`shipment_request/`](shipment_request/).
See [`TASK_NOTES.md`](shipment_request/TASK_NOTES.md) for the data model,
installation alternatives, full review walkthrough, and verification results.

## Run the reviewer demo

Prerequisites: Git, Bash, Docker Desktop (or Docker Engine with Compose), and access
to this private GitHub repository. Authenticate Git with your GitHub account,
then run:

```bash
git clone https://github.com/cs5067/odoo-shipment-request.git
cd odoo-shipment-request
./scripts/setup-demo.sh
```

The opt-in script builds and starts Odoo, installs or updates the addon, creates
missing reviewer accounts and a sample customer, and configures PDF rendering.
Open <http://127.0.0.1:18069> and use either ordinary internal account:

| Login | Initial password | Role |
| --- | --- | --- |
| `shipment.manager` | `ShipmentDemo!2026` | Shipment Manager: requests and shipment types |
| `shipment.user` | `ShipmentDemo!2026` | Shipment User: requests and existing types |

Neither reviewer account has Settings administration access. These local demo
accounts and the sample customer are created only by the script; ordinary addon
installation does not create them.
If login opens Discuss, use **Home Menu** (the top-left app icon) → **Shipments**.

1. Sign in as `shipment.manager`. Open **Shipments → Configuration → Shipment
   Types → New**. Enter `Road Express`, code `ROAD`, category `Road`, and save.
   If you have run the walkthrough before, use the existing type.
2. Open the top-right user menu and choose **Log out**, then sign in as
   `shipment.user`. The Shipments **Configuration** menu is absent.
3. Open **Shipments → Shipments → New**. Select **Sample Logistics Customer**
   and the shipment type, enter the route, choose pickup today or later and
   delivery on or after pickup, then save.
4. Try **Hand to Courier** without cargo to see the validation. Add cargo with
   quantity `2`, unit weight `3.5`, and unit volume `0.25`: totals become
   **7.000 kg** and **0.500 m³**. Every item's measurements must be positive
   before handoff.
5. Use **Hand to Courier → Mark On the Way → Mark Delivered**. Cargo locks after
   handoff and each transition appears in the history. Click **Print Shipment
   Order** to download the PDF while still signed in as the Shipment User.

New reviewer accounts use UTC. Set another timezone in the user's profile
preferences if needed; pickup-date validation uses that timezone.

Rerun `./scripts/setup-demo.sh` to apply source changes. Existing records,
passwords, and profile settings are preserved; the initial passwords above
apply only to newly created accounts. An incompatible existing login stops
setup without modifying account credentials or permissions. See the task notes
for recovery and isolated runs on another port.

Use `docker compose stop` to stop services while preserving the database and
filestore. On a fresh development database, `admin` / `admin` remains available
separately for Settings and user management.

## Tests

```bash
./scripts/test.sh
```

This builds the addon image, installs on a fresh temporary PostgreSQL database,
runs the Odoo tests, and removes only that test database. GitHub Actions uses the
same command; the task notes record its current verification status.

Only Odoo's standard `base`, `mail`, and `web` addons are required. Pricing,
carrier integrations, fleet, accounting, portals, and multi-company behavior
are outside this module's scope.
