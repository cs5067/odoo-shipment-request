# Shipment Requests — task notes

## Context

This standalone Odoo 19 application supports a shared logistics queue: register
shipment requests, maintain shipment types, record cargo, advance delivery
stages, and print a shipment order for a driver.

Assumptions and operating rules:

- All Shipment Users share access to the team's requests. There is no owner
  partitioning or multi-company behavior.
- Customers use Odoo contacts. Origins and destinations are free-text addresses.
- Requested pickup and delivery are calendar dates. New requests and pickup
  rescheduling must use today or a later date, based on the active Odoo user
  timezone. Delivery cannot precede pickup. Existing shipments retain their
  original pickup dates as time passes and can still be updated and delivered.
- Cargo weight is kilograms per unit and volume is cubic metres per unit.
  Quantity may be fractional. Line totals are quantity × the unit measurement.
  Quantity must be positive. Weight and volume may be left at zero while
  Preparing, but every item must have positive measurements before handoff.
  Negative measurements are rejected at all stages. Size is recorded as volume;
  separate length, width, and height fields are not part of this module.
- Every request starts in Preparing. The fixed lifecycle is Preparing → With
  Courier → On the Way → Delivered, with no backward transitions.
- Cargo can be added, edited, removed, reordered, or moved between requests only
  while all affected requests are Preparing. Handoff requires at least one
  cargo item with complete measurements and locks the cargo for the rest of
  the lifecycle. An incomplete item blocks handoff even if other items are valid.
- Requests may be deleted only while Preparing, preserving dispatched requests
  and their delivery history.
- Shipment type categories are Road, Air, Ocean, Parcel, and Other. Managers may
  create multiple types within a category. Archiving a type preserves existing
  requests and removes it from new selections.

## What you did

- Delivered an installable Odoo 19 application with shipment requests, separate
  shipment types, and ordered cargo lines.
- Added automatic references such as `SHP/000001`. References cannot be edited;
  duplicating a request creates a new reference and starts it in Preparing.
  A duplicate moves an elapsed pickup date to today, and an elapsed delivery
  date to today if needed. Future dates remain unchanged; the source is untouched.
- Added stored computed cargo and shipment totals that recalculate when cargo
  changes, plus validation of dates, routes, descriptions, and measurements.
- Implemented the three lifecycle buttons with server-side validation. Direct
  status edits, skipped stages, repeated transitions, and an empty handoff are
  rejected. Missing or zero weight/volume blocks handoff with a message naming
  the cargo items to complete. Creation from any kanban column still starts in Preparing.
- Enforced cargo and request-deletion rules on the server, including imports
  and direct ORM/API operations. The form also makes dispatched cargo read-only.
- Recorded status changes in the standard chatter with the acting user and
  timestamp, including when the calling context would normally disable tracking.
- Added Shipment User and Shipment Manager roles. Users manage requests;
  managers also maintain shipment types. No shipment access is granted to
  unrelated internal users, portal users, or the public user.
- Added menus, list/kanban/form/search views, status filters, and grouping by
  status, shipment type, and customer. All four board stages remain visible when
  empty; dragging cards cannot change status.
- Added a PDF shipment order containing the reference, customer, route, dates,
  cargo quantities and unit measurements, line totals, and shipment totals.
- Included automated Odoo tests, a fresh-database test script, a Docker setup,
  an opt-in reviewer setup with both normal roles, and a GitHub Actions workflow
  using the same test script.

Repository: [odoo-shipment-request](https://github.com/cs5067/odoo-shipment-request).
Repository access is required because it is private.

## Findings, caveats, and setup

### Verification

Runtime verification used official Odoo **19.0-20260630**, PostgreSQL **16.14**,
and wkhtmltopdf **0.12.6.1** in Docker.

- A fresh database installed the addon and its dependencies with demo data
  disabled. No installation errors or invalid views remained.
- The fresh-database test run completed successfully: **30 tests, 0 failures,
  0 errors**. Coverage includes reference generation and duplication; totals on
  cargo creation, editing, deletion, and reassignment; cargo locking after
  handoff; missing-measurement checks on every line and on older in-progress
  shipments; request-deletion restrictions; past-date rejection on new and
  rescheduled pickups; timezone boundaries; continued processing and duplication
  of historical shipments; date ordering and cargo validation; archive
  behavior; lifecycle enforcement; dated history; empty board columns; role
  permissions; and report HTML.
- Access checks use real non-superuser accounts. Ordinary internal users
  without a shipment role, portal users, and the public user have no access to
  the three shipment models. Managers inherit users' shipment permissions.
- A real A4 PDF was downloaded using **Print Shipment Order** and visually
  inspected. The final workflow check showed **7.000 kg** and **0.500 m³**, with
  the correct customer, route, dates, cargo, reference, and Delivered status.
  PDF inspection is separate from the automated HTML report test.
- Browser checks covered menu navigation, the four-column board including empty
  stages, and the complete Preparing → Delivered workflow. Zero volume blocked
  handoff and named the affected cargo; filling the missing value allowed all
  three transitions, locked cargo, and recorded the dated history. An older
  in-progress shipment with zero measurements was also blocked. Duplicating a
  delivered request produced a new editable Preparing request and reference.
- A browser check rejected a new request with yesterday's pickup date, then
  saved it successfully after changing pickup to today. The automated tests
  also verify rescheduling, context defaults, and timezone cutoffs.
- The final running container's shipment model matched the tested source by
  SHA-256 after rebuilding, upgrading, and recreating the service. The addon
  path avoids the base image's persistent addon volume, which otherwise retained
  older code during a container recreation.
- Ordinary addon installation creates no reviewer accounts or sample customer.
  The optional reviewer setup script creates them explicitly.
- The reviewer setup was run on a separate fresh Docker project. Both ordinary
  account logins, manager-only type maintenance, user validation errors, all
  three delivery actions and their history, and PDF download as a Shipment User
  were verified. A rejected deletion through an authenticated request preserved
  the shipment and its history. Rerunning setup preserved existing records,
  history, reference sequence, account passwords, and profile settings.
- Remote CI remains blocked before execution: both push and manual GitHub
  Actions runs reported `startup_failure` without creating jobs or runner logs.
  The enabled workflow passes actionlint 1.7.12 and supports manual dispatch.
  The repository owner should check GitHub account/Actions availability before
  relying on CI. Local tests pass; a successful cloud run has not been verified.
  [Manual run details](https://github.com/cs5067/odoo-shipment-request/actions/runs/42507956922).

### Install and try with Docker

Prerequisites: Git, Bash, Docker Desktop (or Docker Engine with the Compose plugin),
and access to the private repository. Authenticate Git with your GitHub account,
then run:

```bash
git clone https://github.com/cs5067/odoo-shipment-request.git
cd odoo-shipment-request
./scripts/setup-demo.sh
```

This opt-in script builds the image, initializes or upgrades `shipment_demo`,
creates missing reviewer accounts and **Sample Logistics Customer**, configures
PDF rendering, starts Odoo, and waits for it to respond. It uses local
development credentials and publishes the web port only on loopback. Ordinary
addon installation does not create these accounts or the sample customer.

Open <http://127.0.0.1:18069> and sign in with:

| Login | Initial password | Role |
| --- | --- | --- |
| `shipment.manager` | `ShipmentDemo!2026` | Shipment Manager |
| `shipment.user` | `ShipmentDemo!2026` | Shipment User |

Both are ordinary internal accounts without Settings administration access.
New accounts use UTC; change the user's timezone in their profile preferences
if needed. Date validation uses the active user's timezone. A fresh database
also has `admin` / `admin` for Settings and manual user management.
If login opens Discuss, use **Home Menu** (the top-left app icon) → **Shipments**.

### Review both roles and the full workflow

1. Sign in as `shipment.manager`. Open **Shipments → Configuration → Shipment
   Types → New**. Create `Road Express`, code `ROAD`, category `Road`, and save.
   Codes are normalized to uppercase and must be unique. On subsequent runs,
   use the existing type instead of creating the same code again.
2. Open the top-right user menu → **Log out**, then sign in as `shipment.user`.
   The Shipments **Configuration** menu is absent. This account can select shipment types but
   cannot create, edit, archive, or delete them. Neither reviewer account can
   administer users through Settings.
3. Open **Shipments → Shipments → New**. Select **Sample Logistics Customer**
   and the type, enter the origin and destination, and choose pickup today or
   later with delivery on or after pickup. Save and note the generated reference.
   Trying yesterday's pickup or delivery before pickup should produce an error.
4. Try **Hand to Courier** with no cargo; the shipment must remain Preparing.
   Add a cargo line with quantity `2`, unit weight `3.5`, and volume `0`. It can
   be saved, but handoff must name the incomplete item and block progression.
   Change volume to `0.25`: totals become **7.000 kg** and **0.500 m³**. Edit,
   add, or remove lines while Preparing to check automatic recomputation, then
   leave at least one line with positive measurements for handoff.
5. Use **Hand to Courier → Mark On the Way → Mark Delivered**. Cargo becomes
   read-only after handoff; attempting to delete the request is rejected by the
   server. Each status change appears in the history with an actor and date.
   The status bar itself cannot be edited.
6. Switch between List and Kanban. All four lifecycle columns remain visible,
   including empty stages. Use the search dropdown for status filters and
   grouping by shipment type or customer.
7. While signed in as `shipment.user`, click **Print Shipment Order**, or choose
   **Shipment Order** in the Print menu. Check the PDF's reference, customer,
   route, cargo, and totals. The standard company layout supplies the header
   and footer. The setup script sets `report.url` to `http://127.0.0.1:8069` so
   the renderer can load assets through the container's internal port.
8. Log out and sign back in as `shipment.manager`. The same shipment is visible
   because both roles share the team queue. Open the type and use **Actions →
   Archive**. It remains on existing shipments but is unavailable for new ones.
   Use the **Archived** filter to find the type and **Actions → Unarchive** to
   restore it. Managers obey the same cargo and request-deletion restrictions.

### Rerun, stop, or use an isolated demo

Rerun `./scripts/setup-demo.sh` after source changes. It rebuilds and upgrades
the addon, briefly stops and restarts Odoo, and preserves existing shipments,
passwords, and profile settings. Initial demo passwords apply only when accounts
are first created. Use an existing password if it has changed; an administrator
can reset it through Settings if needed.

If either demo login already belongs to an inactive, portal, administrative, or
unexpected-role account, setup stops with a clear error without saving account
changes. To resolve it, start Odoo with `docker compose up -d --wait odoo`, sign
in as an administrator, and use Settings to rename that existing login or assign
the expected shipment role without administration access. Then rerun setup.

Use `docker compose stop` to stop services while retaining the database and
filestore. The image stores addon code in `/opt/odoo/custom-addons`, outside the
base image's persistent addon volume, so recreated containers load the rebuilt
code.

For a separate fresh demo alongside an existing one, use both a different
Compose project name and a free host port in the same terminal:

```bash
export COMPOSE_PROJECT_NAME=shipment-review
export SHIPMENT_PORT=18070
./scripts/setup-demo.sh
```

Open <http://127.0.0.1:18070>. Keep these variables set for subsequent setup,
test, and `docker compose stop` commands so they address the same isolated
project. Changing only the port does not isolate database or filestore volumes.

### Install into an existing Odoo 19 server

1. Copy the `shipment_request` directory into a configured custom addons path.
   The repository root itself is not the addon directory.
2. Restart Odoo. Enable developer mode, update the Apps list, search for
   **Shipment Requests**, and install. Dependencies are standard `base`, `mail`,
   and `web`; no Enterprise or third-party addons are required.
3. Alternatively, use the server's own configuration and database credentials:

   ```bash
   odoo -c /path/to/odoo.conf -d DATABASE -i shipment_request --without-demo=true --stop-after-init
   ```

4. Sign in as an administrator and open **Settings → Users & Companies → Users**.
   Create or select an internal user and set **Shipments** access to **Shipment
   User** or **Shipment Manager**. A shipment manager does not need Settings
   administration rights. No shipment role is granted to all internal users by
   default; the administrator is initially a Shipment Manager. Log out and sign
   in as each ordinary user to follow the workflow above with your own contact.
   Normal installation has no predefined reviewer logins or passwords.
5. Configure wkhtmltopdf as required by Odoo to print PDFs. The supplied Docker
   image already contains it. If Odoo cannot reach its public base URL from
   inside the container, set the standard `report.url` system parameter to an
   internally reachable Odoo URL. The local verification database uses
   `http://127.0.0.1:8069`.

### Run the automated tests

From the repository root:

```bash
./scripts/test.sh
```

The script builds the image, starts PostgreSQL, installs on a uniquely named
temporary database, runs `--test-enable --test-tags=/shipment_request`, and
removes only that test database. Its exit status reflects the Odoo test result.
It can run while the local demo is running. GitHub Actions uses the same script.

For a separately configured Odoo server, use a disposable database:

```bash
odoo -c /path/to/odoo.conf -d shipment_test -i shipment_request --without-demo=true --test-enable --test-tags=/shipment_request --stop-after-init
```

### Implementation details and limits

- The addon uses Odoo 19 access privileges, ORM constraints, `<list>` views,
  kanban `card` templates, and standard QWeb reports.
- Explicit group ACLs protect all three shipment models. Record rules are not
  needed for the shared team queue. Workflow restrictions also apply to
  managers; only shipment types have additional manager permissions.
- Referenced customers and types cannot be deleted. Archive unused shipment
  types instead.
- Sequence numbers may have gaps after rolled-back transactions; they remain
  unique identifiers.
- Cargo is locked after handoff. Other shipment details remain editable and the
  PDF is generated from current values; no immutable dispatch document is kept.
- Measurements are checked at every forward transition, including on older
  in-progress records. Upgrading does not reset history or invent measurements
  for records created under earlier validation rules. Review any such records
  before deployment; incomplete dispatched cargo requires an explicit data
  correction, not a workflow bypass.
- Delivery timing is recorded in the status history. There is no separate
  actual-delivery timestamp, cancellation flow, or backward transition.
- Pricing, projects, fleet, accounting, a customer portal, multi-company
  behavior, and external/carrier APIs are outside the module's scope.

Reference documentation:
[Odoo 19 ORM](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html),
[Odoo 19 view architectures](https://www.odoo.com/documentation/19.0/developer/reference/user_interface/view_architectures.html),
and [Odoo 19 security models](https://github.com/odoo/odoo/blob/19.0/odoo/addons/base/models/res_groups.py).

## Data model and why

- **`shipment.type` — reusable configuration.** Each type has a name, a unique
  normalized code, a category, and an active flag for archiving. A separate model
  keeps classification consistent across requests and lets managers maintain
  types without granting users configuration rights.
- **`shipment.request` — the shipment document.** It links a customer
  (`res.partner`) and a shipment type, and owns the reference, route, requested
  dates, lifecycle state, cargo collection, and stored totals. Inheriting
  `mail.thread` provides standard history with tracked changes. Existing contacts
  avoid duplicating customer data; free-text routes avoid unnecessary location
  configuration.
- **`shipment.cargo` — ordered child lines.** Every line belongs to exactly one
  request through `shipment_id`. Quantity, unit weight, and unit volume determine
  the line totals. Computed-field dependencies propagate additions, edits,
  removals, and reassignment into the shipment totals while Preparing. Restricting
  cargo changes after handoff keeps the dispatched cargo stable.

Fixed lifecycle states use a selection field because the workflow has exactly
four stages in a defined order. A configurable stage model would introduce
unneeded setup and could undermine that sequence. Cargo is removed with a deleted
Preparing request; later requests are retained. Customers and types use
restrictive deletion to preserve references.
