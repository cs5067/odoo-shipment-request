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

- Delivered an installable Odoo 19 application with shipment requests, reusable
  shipment types, and editable cargo lines. References are generated as
  `SHP/000001`, cannot be edited, and stay unique when records are duplicated.
- Added automatic stored totals, positive quantities, nonnegative measurements,
  nonempty route/description validation, and pickup/delivery date validation.
- Implemented Preparing → With Courier → On the Way → Delivered as three
  sequential button actions. The server rejects direct status writes, skipped
  stages, repeated transitions, and handing an empty request to a courier.
  Creation always starts in Preparing, including creation from another kanban
  column or an import with context defaults.
- Recorded status changes in the standard chatter, with the acting user and
  timestamp. The transition actions retain tracking even if their caller has a
  context that normally suppresses tracking.
- Added the two roles, complete menus, list/kanban/form/search views, status
  filters and customer/type grouping. All four board stages remain visible when
  empty. Dragging cards cannot change status.
- Added a PDF shipment order with the reference, customer, route, dates, cargo
  quantities and measurements, line totals, and shipment totals.
- Added 18 automated Odoo tests, an isolated fresh-database test script, a Docker
  development setup, and GitHub Actions running the same test script.
- Created a Git repository with incremental implementation, UI, test, runtime
  correction, and documentation commits:
  <https://github.com/cs5067/odoo-shipment-request> (private repository).

## Findings, caveats, and setup

### Verification

Verified on official Odoo **19.0-20260630**, PostgreSQL **16.14**, and
wkhtmltopdf **0.12.6.1** in Docker:

- A fresh database installed the addon and its dependencies successfully with
  demo data disabled. No module installation errors or invalid views remained.
- The final test run reported **0 failed, 0 errors across 18 tests**. Coverage
  includes reference generation/copy, totals on create/edit/delete/reassignment,
  date and cargo validation, archive behavior, lifecycle bypass attempts,
  timestamped history, empty kanban columns, role permissions, and report HTML.
- Access tests used real non-superuser accounts. Ordinary internal users without
  a shipment role, portal users, and the public user had no access to any of the
  three shipment models. Managers inherited users' shipment permissions.
- A real A4 PDF was generated and visually inspected, including two cargo lines
  totaling **60.000 kg** and **1.320 m³**. This check used wkhtmltopdf, separately
  from the automated HTML report test.
- The browser check verified menu navigation, the four-column board with three
  empty columns, the form, totals, and a courier handoff recorded in the chatter.
- The test script removed its temporary database; the local `shipment_demo`
  database remains available with one sample request for inspection. Sample data
  is not installed by the addon on other databases.
- Remote CI caveat: the initial GitHub Actions run reported `startup_failure`
  before creating any jobs or runner logs, and GitHub refused a retry. The
  workflow is present and enabled, but a passing cloud run has not been verified.
  This is separate from the successful local fresh-database test run above.
  [Initial run details](https://github.com/cs5067/odoo-shipment-request/actions/runs/42437943754).

### Install and try with Docker

Prerequisite: Docker Desktop, or Docker Engine with the Compose plugin. Run
these commands from the repository root (the folder containing `compose.yaml`):

```bash
docker compose build odoo
docker compose up -d --wait db
docker compose run --rm -T odoo odoo -d shipment_demo -i shipment_request --without-demo=true --stop-after-init
docker compose up -d odoo
```

1. Open <http://127.0.0.1:18069>. A newly initialized development database uses
   login `admin`, password `admin`. Compose uses local development credentials
   and publishes the Odoo port only on loopback.
2. The administrator is initially a Shipment Manager. For other internal users,
   open **Settings → Users & Companies → Users**, select a user, and set their
   **Shipments** access to **Shipment User** or **Shipment Manager**. No shipment
   role is granted to all internal users by default.
3. As a manager, open **Shipments → Configuration → Shipment Types**. Create
   `Road Express`, code `ROAD`, category `Road`. Archive/unarchive is available
   in the record's Actions menu; use the Archived filter to find archived types.
4. Open **Shipments → Shipments → New**. Select or create a contact, choose the
   type, enter origin/destination and dates, then save. A reference is assigned.
5. Try **Hand to Courier** without cargo to see the friendly validation message.
   Add cargo: quantity `2`, unit weight `3.5`, unit volume `0.25`. The totals are
   `7.000 kg` and `0.500 m³`. Edit or remove the line to check recomputation.
6. Use **Hand to Courier**, **Mark On the Way**, and **Mark Delivered**. Each
   change appears in the history. The status bar itself cannot be edited.
7. Switch between List and Kanban. Open the search dropdown for status filters
   and grouping by status, shipment type, or customer.
8. Click **Print Shipment Order**, or select **Shipment Order** in the Print
   menu. The standard company report layout supplies the logo/header/footer.

The Docker image contains a copy of the addon so that runtime file access does
not depend on host file-sharing behavior. To apply later source changes:

```bash
docker compose build odoo
docker compose stop odoo
docker compose run --rm -T odoo odoo -d shipment_demo -u shipment_request --stop-after-init
docker compose up -d odoo
```

Stop services and keep their data with `docker compose stop`. Database and
filestore contents are retained in named Docker volumes.

### Install into an existing Odoo 19 server

1. Copy the `shipment_request` directory into a configured custom addons path.
   The repository root itself is not the addon directory.
2. Restart Odoo. Enable developer mode, update the Apps list, search for
   **Shipment Requests**, and install. Dependencies are standard `base`, `mail`,
   and `web`; no Enterprise or third-party addons are required.
3. Alternatively, with the server's own configuration and database credentials:

   ```bash
   odoo -c /path/to/odoo.conf -d DATABASE -i shipment_request --without-demo=true --stop-after-init
   ```

4. Configure wkhtmltopdf as required by Odoo to print PDFs. The supplied official
   Docker image already contains it. If a reverse proxy or host-only port makes
   the public base URL unreachable from Odoo's container, set the standard
   `report.url` system parameter to an internally reachable Odoo URL. The local
   verification database uses `http://127.0.0.1:8069` for this purpose.

### Run the automated tests

From the repository root:

```bash
./scripts/test.sh
```

The script builds the image, starts PostgreSQL, installs on a uniquely named
temporary database, runs `--test-enable --test-tags=/shipment_request`, then
removes only that test database. Its exit status reflects the Odoo test result.
It can run while the local demo is running. GitHub Actions uses the same script.

For a separately configured Odoo server, use a disposable database:

```bash
odoo -c /path/to/odoo.conf -d shipment_test -i shipment_request --without-demo=true --test-enable --test-tags=/shipment_request --stop-after-init
```

### Implementation findings and limits

- Odoo 19 uses `res.groups.privilege` / `privilege_id` for the access-rights UI,
  `models.Constraint` for SQL constraints, `<list>` views, and the kanban
  `card` template. The implementation was checked against the official 19.0
  source and documentation, then installed in the actual runtime.
- PostgreSQL constraint exceptions reach direct ORM tests as `CheckViolation`
  or `UniqueViolation`; Odoo's request layer translates them using the supplied
  friendly constraint messages. Tests assert the specific database constraint,
  while Python-validation tests assert `ValidationError`.
- A transient macOS Docker bind-mount read error was resolved by building the
  addon into the image. The same image-build approach is used in CI.
- There are no global ACLs for these models. Explicit shipment roles control
  access; no record rules are needed for the deliberately shared team queue.
  Users may create, edit, and delete requests/cargo. Only managers maintain
  types. Referenced customers/types cannot be deleted; archive types instead.
- Standard sequence numbers can have gaps after rolled-back transactions. They
  are unique identifiers, not accounting numbers.
- Cargo remains editable after handoff and the PDF reflects current values.
  There is no cancellation, rollback, immutable dispatch snapshot, or separate
  actual-delivery timestamp; status history supplies the progression times.
  These are deliberate scope choices, not unfinished required features.
- No pricing, projects, fleet, accounting, customer portal, multi-company
  behavior, or external/carrier API was added. If the operational policy later
  needs it, a useful next step would be deciding whether dispatched cargo should
  be locked or versioned. Nothing required by this assignment remains unfinished.

Reference documentation:
[Odoo 19 ORM](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html),
[Odoo 19 view architectures](https://www.odoo.com/documentation/19.0/developer/reference/user_interface/view_architectures.html),
and [Odoo 19 security models](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_groups.py).

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
