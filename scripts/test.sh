#!/usr/bin/env bash
# Install and test against a fresh database; remove only this run's database.
set -euo pipefail
cd "$(dirname "$0")/.."

test_db="shipment_test_$(date -u +%Y%m%d_%H%M%S)_$$"
cleanup() {
    local result=$?
    trap - EXIT
    docker compose exec -T db dropdb -U odoo --if-exists --force "$test_db" || true
    exit "$result"
}

docker compose up -d --wait db
trap cleanup EXIT
docker compose run --rm --no-deps -T odoo odoo \
    --database="$test_db" \
    --init=shipment_request \
    --without-demo=true \
    --test-enable \
    --test-tags=/shipment_request \
    --stop-after-init \
    --http-interface=0.0.0.0 \
    --data-dir=/tmp/odoo-shipment-tests \
    --log-level=test
