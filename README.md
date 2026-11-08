# Odoo 19 Shipment Requests

A focused logistics module for registering shipment requests, managing cargo,
advancing delivery stages, and printing a driver shipment order.

The installable addon is [`shipment_request/`](shipment_request/).
See [`TASK_NOTES.md`](shipment_request/TASK_NOTES.md) for the data model,
assumptions, installation instructions, and verification results.

## Run locally

Install Docker Desktop (or Docker Engine with Compose), then run from this folder:

```bash
docker compose build odoo
docker compose up -d --wait db
docker compose run --rm -T odoo odoo -d shipment_demo -i shipment_request --without-demo=true --stop-after-init
docker compose up -d odoo
```

Open <http://127.0.0.1:18069> and sign in with `admin` / `admin` on this fresh
development database. This local setup uses development credentials and binds
the web port to loopback only. The administrator initially has Shipment Manager.
Create a shipment type under **Shipments → Configuration → Shipment Types**,
then register a shipment under **Shipments → Shipments**.

The image contains a snapshot of the addon. After source edits, rebuild and
upgrade it using the commands in the task notes. `docker compose stop` stops
the local services while retaining their data.

## Tests

```bash
./scripts/test.sh
```

This builds the addon image, installs on a fresh temporary PostgreSQL database,
runs the Odoo tests, and removes only that test database. GitHub Actions runs the
same command on pushes and pull requests.

Only Odoo's standard `base`, `mail`, and `web` addons are required. Pricing,
carrier integrations, fleet, accounting, portals, and multi-company behavior
are deliberately outside this module's scope.
