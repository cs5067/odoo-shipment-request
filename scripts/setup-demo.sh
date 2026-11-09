#!/usr/bin/env bash
# Opt-in local reviewer environment; never reset the database or existing passwords.
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose build odoo
docker compose up -d --wait db
docker compose stop odoo
docker compose run --rm -T odoo odoo \
    --database=shipment_demo \
    --init=shipment_request \
    --update=shipment_request \
    --without-demo=true \
    --http-interface=0.0.0.0 \
    --stop-after-init
docker compose run --rm -T odoo odoo shell \
    --database=shipment_demo --no-http < scripts/setup-demo.py
docker compose up -d --wait odoo

printf '\nDemo ready: http://127.0.0.1:%s\n' "${SHIPMENT_PORT:-18069}"
printf '%s\n' \
    'New demo accounts: shipment.manager / shipment.user' \
    'Initial password for each: ShipmentDemo!2026' \
    'Existing accounts keep their passwords and profile settings.' \
    'Start as shipment.manager: Shipments > Configuration > Shipment Types > New.'
