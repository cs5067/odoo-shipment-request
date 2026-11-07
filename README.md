# Odoo 19 Shipment Requests

A focused logistics module for registering shipment requests, managing cargo,
advancing delivery stages, and printing a driver shipment order.

The installable addon is [`shipment_request/`](shipment_request/).
See [`TASK_NOTES.md`](shipment_request/TASK_NOTES.md) for the data model,
assumptions, installation instructions, and verification results.

## Implementation sequence

1. Scaffold the addon and document the scope.
2. Implement the models, permissions, and lifecycle invariants.
3. Add views and a printable order.
4. Test against a clean Odoo 19 database and record the results.

Only Odoo's standard `base`, `mail`, and `web` addons are required. Pricing,
carrier integrations, fleet, accounting, portals, and multi-company behavior
are deliberately outside this module's scope.
