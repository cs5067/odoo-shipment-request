# Task notes

## Context

Build a small, standalone Odoo 19 application for a logistics team to register
shipment requests, maintain shipment types, record cargo, advance delivery
stages, and print a shipment order for a driver. Keep the implementation within
the assignment's approximately eight-hour budget.

Assumptions:

- All authorized shipment users work on a shared team queue. There is no owner
  partitioning or multi-company feature.
- Customers are existing Odoo contacts. Origins and destinations are free-text
  addresses; separate locations would add unnecessary configuration here.
- Requested pickup and delivery are calendar dates. Delivery cannot precede pickup.
- Cargo weight (kg) and volume (m³) are per unit. Quantity may be fractional;
  line totals are quantity × the per-unit measurement. Zero weight/volume is
  permitted for measurements not yet known; negative values are rejected.
- The four lifecycle stages are fixed and forward-only. Cargo can be corrected
  throughout the lifecycle; the initial handoff requires at least one cargo item.
- Shipment type categories are Road, Air, Ocean, Parcel, and Other. Managers may
  create multiple types within a category. Archived types remain on old requests.

## What you did

Implementation and verification results will be recorded as the work is completed.

## Findings, caveats, and setup

Exact setup and test commands will be recorded after runtime verification.

## Data model and why

- `shipment.type`: reusable, archivable configuration with a name, unique code,
  and category. A separate model keeps classification consistent across requests
  and lets managers maintain it without granting users configuration rights.
- `shipment.request`: the business document, linked to a customer (`res.partner`)
  and a shipment type. It owns the generated reference, route, requested dates,
  fixed lifecycle state, cargo collection, and stored computed totals. Inheriting
  `mail.thread` gives each request a standard Odoo history with tracked changes.
- `shipment.cargo`: ordered child lines, each belonging to exactly one request.
  A one-to-many relationship supports arbitrary item counts and independent line
  validation. Quantity, unit weight, and unit volume determine each line's totals;
  dependencies propagate changes and deletions into the request totals.

Fixed states use a selection rather than a configurable stage model because the
assignment specifies exactly four stages and an ordered progression. Types and
customers use restrictive deletion; cargo belongs to its request and is removed
with it. No company, pricing, fleet, project, accounting, portal, or carrier API
models are introduced.
