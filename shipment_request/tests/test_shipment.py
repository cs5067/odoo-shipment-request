from datetime import date, datetime, timedelta
from unittest.mock import patch

from psycopg2.errors import CheckViolation, UniqueViolation

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestShipmentRequest(TransactionCase):
    """Exercise business rules through the ORM and real, non-sudo roles."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shipment_user = new_test_user(
            cls.env,
            login="shipment_test_user",
            groups="shipment_request.group_shipment_user",
        )
        cls.other_shipment_user = new_test_user(
            cls.env,
            login="shipment_test_colleague",
            groups="shipment_request.group_shipment_user",
        )
        cls.shipment_manager = new_test_user(
            cls.env,
            login="shipment_test_manager",
            groups="shipment_request.group_shipment_manager",
        )
        cls.outsider = new_test_user(
            cls.env, login="shipment_test_outsider", groups="base.group_user"
        )
        cls.portal_user = new_test_user(
            cls.env, login="shipment_test_portal", groups="base.group_portal"
        )
        cls.customer = cls.env["res.partner"].create({"name": "Shipment Test Customer"})
        cls.shipment_type = cls.env["shipment.type"].with_user(
            cls.shipment_manager
        ).create({"name": "Test Road", "code": "TEST-ROAD", "category": "road"})
        cls.Request = cls.env["shipment.request"].with_user(cls.shipment_user)
        cls.Cargo = cls.env["shipment.cargo"].with_user(cls.shipment_user)

    def _request_values(self, **overrides):
        today = fields.Date.context_today(self.Request)
        values = {
            "customer_id": self.customer.id,
            "shipment_type_id": self.shipment_type.id,
            "origin": "Cairo warehouse",
            "destination": "Alexandria depot",
            "pickup_date": today + timedelta(days=1),
            "delivery_date": today + timedelta(days=3),
        }
        values.update(overrides)
        return values

    def _cargo_values(self, **overrides):
        values = {
            "description": "Box of spare parts",
            "quantity": 2,
            "weight": 3.5,
            "volume": 0.25,
        }
        values.update(overrides)
        return values

    def _shipment(self, cargo=False, **overrides):
        if cargo:
            overrides.setdefault("cargo_ids", [Command.create(self._cargo_values())])
        return self.Request.create(self._request_values(**overrides))

    def _assert_totals(self, shipment, weight, volume):
        self.assertAlmostEqual(shipment.total_weight, weight)
        self.assertAlmostEqual(shipment.total_volume, volume)

    def test_references_are_generated_unique_in_batch_and_copy(self):
        shipments = self.Request.create(
            [self._request_values(), self._request_values(name="CUSTOM-REFERENCE")]
        )
        duplicate = shipments[0].copy()
        references = (shipments | duplicate).mapped("name")
        self.assertEqual(len(set(references)), 3)
        self.assertTrue(all(name.startswith("SHP/") for name in references))
        self.assertNotIn("CUSTOM-REFERENCE", references)
        self.assertEqual(duplicate.state, "preparing")
        self.assertEqual(duplicate.pickup_date, shipments[0].pickup_date)
        self.assertEqual(duplicate.delivery_date, shipments[0].delivery_date)

    def test_reference_cannot_be_rewritten(self):
        shipment = self._shipment()
        reference = shipment.name
        with self.assertRaises(UserError):
            shipment.write({"name": "SHP/FORGED"})
        self.assertEqual(shipment.name, reference)

    def test_cargo_totals_follow_add_edit_delete_and_reassignment(self):
        shipment = self._shipment()
        other = self._shipment()
        self._assert_totals(shipment, 0, 0)

        first = self.Cargo.create(self._cargo_values(shipment_id=shipment.id))
        second = self.Cargo.create(
            self._cargo_values(shipment_id=shipment.id, quantity=3, weight=4, volume=0.5)
        )
        self.assertAlmostEqual(first.total_weight, 7)
        self.assertAlmostEqual(first.total_volume, 0.5)
        self._assert_totals(shipment, 19, 2)

        first.write({"quantity": 4, "weight": 2, "volume": 0.125})
        self._assert_totals(shipment, 20, 2)
        second.write({"shipment_id": other.id})
        self._assert_totals(shipment, 8, 0.5)
        self._assert_totals(other, 12, 1.5)

        first.unlink()
        self._assert_totals(shipment, 0, 0)
        second.unlink()
        self._assert_totals(other, 0, 0)

    def test_incomplete_measurements_save_in_preparing_but_block_handoff(self):
        for description, measurements in (
            ("Zero weight", {"weight": 0, "volume": 0.25}),
            ("Zero volume", {"weight": 3.5, "volume": 0}),
            ("Both measurements zero", {"weight": 0, "volume": 0}),
            ("Missing weight", {"volume": 0.25}),
            ("Missing volume", {"weight": 3.5}),
            ("Both measurements missing", {}),
        ):
            with self.subTest(description=description):
                shipment = self._shipment()
                line = self.Cargo.create({
                    "shipment_id": shipment.id,
                    "description": description,
                    "quantity": 0.5,
                    **measurements,
                })
                self.assertEqual(shipment.state, "preparing")
                self.assertEqual(line.weight, measurements.get("weight", 0))
                self.assertEqual(line.volume, measurements.get("volume", 0))
                with self.assertRaises(UserError) as raised:
                    shipment.action_with_courier()
                self.assertIn(description, str(raised.exception))
                self.assertEqual(shipment.state, "preparing")

    def test_handoff_requires_positive_measurements_on_every_cargo_line(self):
        shipment = self._shipment(cargo=True)
        incomplete = self.Cargo.create([
            self._cargo_values(
                shipment_id=shipment.id, description="Unweighed box",
                quantity=1, weight=0, volume=0.25,
            ),
            self._cargo_values(
                shipment_id=shipment.id, description="Unmeasured pallet",
                quantity=1, weight=3.5, volume=0,
            ),
        ])
        # Positive shipment totals must not hide incomplete individual items.
        self._assert_totals(shipment, 10.5, 0.75)
        with self.assertRaises(UserError) as raised:
            shipment.action_with_courier()
        for description in incomplete.mapped("description"):
            self.assertIn(description, str(raised.exception))
        self.assertEqual(shipment.state, "preparing")

        incomplete[0].write({"weight": 1})
        with self.assertRaises(UserError) as raised:
            shipment.action_with_courier()
        self.assertIn("Unmeasured pallet", str(raised.exception))
        self.assertEqual(shipment.state, "preparing")

        incomplete[1].write({"volume": 0.1})
        shipment.action_with_courier()
        shipment.action_on_the_way()
        shipment.action_delivered()
        self.assertEqual(shipment.state, "delivered")
        self._assert_totals(shipment, 11.5, 0.85)

    def test_legacy_incomplete_shipments_cannot_advance_further(self):
        for state, action in (
            ("with_courier", "action_on_the_way"),
            ("on_the_way", "action_delivered"),
        ):
            for has_cargo in (True, False):
                with self.subTest(state=state, has_cargo=has_cargo):
                    shipment = self._shipment()
                    if has_cargo:
                        self.Cargo.create(self._cargo_values(
                            shipment_id=shipment.id,
                            description="Incomplete legacy cargo", weight=0, volume=0,
                        ))
                    # Fixture only: represent records saved before measurement
                    # checks existed, without weakening the production workflow.
                    shipment.flush_recordset(["state"])
                    self.cr.execute(
                        "UPDATE shipment_request SET state = %s WHERE id = %s",
                        (state, shipment.id),
                    )
                    shipment.invalidate_recordset(["state"])
                    self.assertEqual(shipment.state, state)

                    with self.assertRaises(UserError) as raised:
                        getattr(shipment, action)()
                    expected = "Incomplete legacy cargo" if has_cargo else "cargo"
                    self.assertIn(expected, str(raised.exception))
                    self.assertEqual(shipment.state, state)

    def test_cargo_is_immutable_after_preparing_for_users_and_managers(self):
        shipment = self._shipment(cargo=True)
        for action in ("action_with_courier", "action_on_the_way", "action_delivered"):
            getattr(shipment, action)()
            for user in (self.shipment_user, self.shipment_manager):
                Cargo = self.Cargo.with_user(user)
                line = shipment.cargo_ids.with_user(user)
                with self.subTest(state=shipment.state, user=user.login):
                    with self.assertRaises(UserError), self.cr.savepoint():
                        Cargo.create(self._cargo_values(shipment_id=shipment.id))
                    with self.assertRaises(UserError), self.cr.savepoint():
                        Cargo.with_context(default_shipment_id=shipment.id).create(
                            self._cargo_values()
                        )
                    for values in (
                        {"description": "Changed cargo"},
                        {"quantity": 9},
                        {"weight": 9},
                        {"volume": 9},
                        {"sequence": 99},
                    ):
                        with self.subTest(values=values):
                            with self.assertRaises(UserError), self.cr.savepoint():
                                line.write(values)
                    with self.assertRaises(UserError), self.cr.savepoint():
                        line.unlink()
                    with self.assertRaises(UserError), self.cr.savepoint():
                        line.with_context(_force_unlink=True).unlink()
            self.assertEqual(len(shipment.cargo_ids), 1)
            self._assert_totals(shipment, 7, 0.5)

    def test_cargo_reassignment_checks_source_and_destination_shipments(self):
        preparing = self._shipment(cargo=True)
        locked = self._shipment(cargo=True)
        preparing_line = preparing.cargo_ids
        locked_line = locked.cargo_ids
        for action in ("action_with_courier", "action_on_the_way", "action_delivered"):
            getattr(locked, action)()
            with self.subTest(state=locked.state):
                with self.assertRaises(UserError), self.cr.savepoint():
                    locked_line.write({"shipment_id": preparing.id})
                with self.assertRaises(UserError), self.cr.savepoint():
                    preparing_line.write({"shipment_id": locked.id})
                self.assertEqual(locked_line.shipment_id, locked)
                self.assertEqual(preparing_line.shipment_id, preparing)
                self._assert_totals(locked, 7, 0.5)
                self._assert_totals(preparing, 7, 0.5)

        # An explicit editable parent takes precedence over a context default.
        line = self.Cargo.with_context(default_shipment_id=locked.id).create(
            self._cargo_values(shipment_id=preparing.id)
        )
        self.assertEqual(line.shipment_id, preparing)

    def test_one2many_commands_cannot_bypass_cargo_immutability(self):
        preparing = self._shipment(cargo=True)
        locked = self._shipment(cargo=True)
        preparing_line = preparing.cargo_ids
        locked_line = locked.cargo_ids
        locked.action_with_courier()
        for command in (
            Command.clear(),
            Command.delete(locked_line.id),
            Command.unlink(locked_line.id),
            Command.update(locked_line.id, {"quantity": 9}),
            Command.create(self._cargo_values()),
            Command.set([]),
            Command.link(preparing_line.id),
        ):
            with self.subTest(command=command):
                with self.assertRaises(UserError), self.cr.savepoint():
                    locked.write({"cargo_ids": [command]})
        for command in (
            Command.link(locked_line.id),
            Command.set([locked_line.id]),
            Command.update(preparing_line.id, {"shipment_id": locked.id}),
        ):
            with self.subTest(reassignment=command):
                with self.assertRaises(UserError), self.cr.savepoint():
                    preparing.write({"cargo_ids": [command]})
        with self.assertRaises(UserError), self.cr.savepoint():
            self._shipment(cargo_ids=[Command.link(locked_line.id)])
        self.assertEqual(locked.cargo_ids, locked_line)
        self.assertEqual(preparing.cargo_ids, preparing_line)
        self._assert_totals(locked, 7, 0.5)
        self._assert_totals(preparing, 7, 0.5)

    def test_in_progress_shipments_cannot_be_deleted_by_either_role(self):
        shipment = self._shipment(cargo=True)
        preparing = self._shipment(cargo=True)
        for action in ("action_with_courier", "action_on_the_way", "action_delivered"):
            getattr(shipment, action)()
            for user in (self.shipment_user, self.shipment_manager):
                with self.subTest(state=shipment.state, user=user.login):
                    with self.assertRaises(UserError), self.cr.savepoint():
                        shipment.with_user(user).unlink()
                    with self.assertRaises(UserError), self.cr.savepoint():
                        shipment.with_user(user).with_context(_force_unlink=True).unlink()
                    with self.assertRaises(UserError), self.cr.savepoint():
                        (preparing | shipment).with_user(user).unlink()
            self.assertTrue(shipment.exists())
            self.assertTrue(preparing.exists())
            self.assertEqual(len(shipment.cargo_ids), 1)
            self.assertEqual(len(preparing.cargo_ids), 1)

    def test_preparing_shipments_can_be_deleted_with_their_cargo(self):
        for user in (self.shipment_user, self.shipment_manager):
            with self.subTest(user=user.login):
                shipment = self._shipment(cargo=True).with_user(user)
                cargo = shipment.cargo_ids
                shipment.unlink()
                self.assertFalse(shipment.exists())
                self.assertFalse(cargo.exists())

    def test_invalid_cargo_quantities_and_measurements_are_rejected(self):
        shipment = self._shipment(cargo=True)
        for invalid_values, constraint in (
            ({"quantity": 0}, "shipment_cargo_quantity_positive"),
            ({"quantity": -1}, "shipment_cargo_quantity_positive"),
            ({"weight": -0.1}, "shipment_cargo_weight_nonnegative"),
            ({"volume": -0.1}, "shipment_cargo_volume_nonnegative"),
        ):
            with self.subTest(values=invalid_values):
                # INSERT hits PostgreSQL before Python constraints. Odoo's RPC
                # error handler translates this into the constraint's message.
                with (
                    mute_logger("odoo.sql_db"),
                    self.assertRaises(CheckViolation) as raised,
                    self.cr.savepoint(),
                ):
                    self.Cargo.create(
                        self._cargo_values(shipment_id=shipment.id, **invalid_values)
                    )
                self.assertEqual(raised.exception.diag.constraint_name, constraint)
                with self.assertRaises(ValidationError), self.cr.savepoint():
                    shipment.cargo_ids.write(invalid_values)
        self._assert_totals(shipment, 7, 0.5)

    def test_delivery_cannot_precede_pickup(self):
        today = fields.Date.context_today(self.Request)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._shipment(delivery_date=today)
        shipment = self._shipment()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            shipment.write({"pickup_date": shipment.delivery_date + timedelta(days=1)})
        shipment.write({"delivery_date": shipment.pickup_date})
        self.assertEqual(shipment.pickup_date, shipment.delivery_date)

    def test_new_or_changed_pickup_cannot_be_in_the_past(self):
        today = fields.Date.context_today(self.Request)
        yesterday = today - timedelta(days=1)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._shipment(pickup_date=yesterday, delivery_date=today)

        values = self._request_values(delivery_date=today)
        values.pop("pickup_date")
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.Request.with_context(default_pickup_date=yesterday).create(values)

        shipment = self._shipment()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            shipment.write({"pickup_date": yesterday})
        self.assertGreaterEqual(shipment.pickup_date, today)

        # Explicit valid values take precedence over a stale context default.
        explicit = self.Request.with_context(default_pickup_date=yesterday).create(
            self._request_values(pickup_date=today, delivery_date=today)
        )
        self.assertEqual(explicit.pickup_date, today)

    def test_pickup_today_future_and_normal_default_are_allowed(self):
        today = fields.Date.context_today(self.Request)
        same_day = self._shipment(pickup_date=today, delivery_date=today)
        self.assertEqual(same_day.pickup_date, today)
        future = self._shipment()
        self.assertGreater(future.pickup_date, today)
        future.write({"pickup_date": today})
        self.assertEqual(future.pickup_date, today)
        values = self._request_values()
        values.pop("pickup_date")
        defaulted = self.Request.create(values)
        self.assertEqual(defaulted.pickup_date, today)

    def test_existing_past_pickup_allows_edits_and_lifecycle_progress(self):
        original_day = fields.Date.context_today(self.Request)
        shipment = self._shipment(
            cargo=True, pickup_date=original_day, delivery_date=original_day
        )
        later_today = original_day + timedelta(days=10)
        with patch.object(fields.Date, "context_today", return_value=later_today):
            shipment.write({"destination": "Updated delivery depot"})
            shipment.write({"delivery_date": later_today})
            for unchanged in (original_day, fields.Date.to_string(original_day)):
                shipment.write({"pickup_date": unchanged})
            self.assertEqual(shipment.pickup_date, original_day)
            with self.assertRaises(ValidationError), self.cr.savepoint():
                shipment.write({"pickup_date": original_day + timedelta(days=1)})
            shipment.action_with_courier()
            shipment.action_on_the_way()
            shipment.action_delivered()
        self.assertEqual(shipment.state, "delivered")
        self.assertEqual(shipment.pickup_date, original_day)

    def test_pickup_cutoff_uses_the_users_timezone(self):
        real_context_today = fields.Date.context_today
        fixed_utc = datetime(2030, 1, 1, 0, 30)
        with patch.object(
            fields.Date, "context_today",
            side_effect=lambda record: real_context_today(record, timestamp=fixed_utc),
        ):
            west = self.Request.with_context(tz="America/Los_Angeles")
            east = self.Request.with_context(tz="Asia/Tokyo")
            self.assertEqual(fields.Date.context_today(west), date(2029, 12, 31))
            self.assertEqual(fields.Date.context_today(east), date(2030, 1, 1))
            values = self._request_values(
                pickup_date=date(2029, 12, 31), delivery_date=date(2030, 1, 1)
            )
            western_shipment = west.create(values)
            self.assertEqual(western_shipment.pickup_date, date(2029, 12, 31))
            with self.assertRaises(ValidationError), self.cr.savepoint():
                east.create(values)
            eastern_shipment = east.create({**values, "pickup_date": date(2030, 1, 1)})
            self.assertEqual(eastern_shipment.pickup_date, date(2030, 1, 1))

    def test_copy_historical_shipment_rolls_past_dates_forward(self):
        original_day = fields.Date.context_today(self.Request)
        source = self._shipment(
            cargo=True, pickup_date=original_day,
            delivery_date=original_day + timedelta(days=2),
        )
        source.action_with_courier()
        source.action_on_the_way()
        source.action_delivered()
        later_delivery = original_day + timedelta(days=20)
        partly_historical = self._shipment(
            pickup_date=original_day, delivery_date=later_delivery
        )
        later_today = original_day + timedelta(days=10)
        with patch.object(fields.Date, "context_today", return_value=later_today):
            duplicate = source.copy()
            self.assertEqual(duplicate.pickup_date, later_today)
            self.assertEqual(duplicate.delivery_date, later_today)
            self.assertEqual(duplicate.state, "preparing")
            self.assertNotEqual(duplicate.name, source.name)
            self.assertNotEqual(duplicate.cargo_ids, source.cargo_ids)
            self._assert_totals(duplicate, 7, 0.5)
            preserved_delivery = partly_historical.copy()
            self.assertEqual(preserved_delivery.pickup_date, later_today)
            self.assertEqual(preserved_delivery.delivery_date, later_delivery)

            explicit_dates = {
                "pickup_date": later_today + timedelta(days=5),
                "delivery_date": later_today + timedelta(days=6),
            }
            explicit = source.copy(explicit_dates)
            self.assertEqual(explicit.pickup_date, explicit_dates["pickup_date"])
            self.assertEqual(explicit.delivery_date, explicit_dates["delivery_date"])
            with self.assertRaises(ValidationError), self.cr.savepoint():
                source.copy({"pickup_date": later_today - timedelta(days=1)})
        self.assertEqual(source.pickup_date, original_day)
        self.assertEqual(source.delivery_date, original_day + timedelta(days=2))
        self.assertEqual(source.state, "delivered")

    def test_empty_shipment_cannot_leave_preparing(self):
        shipment = self._shipment()
        with self.assertRaisesRegex(UserError, "[Cc]argo"):
            shipment.action_with_courier()
        self.assertEqual(shipment.state, "preparing")

    def test_lifecycle_is_sequential_and_cannot_repeat_or_skip(self):
        shipment = self._shipment(cargo=True)
        with self.assertRaises(UserError):
            shipment.action_on_the_way()
        with self.assertRaises(UserError):
            shipment.action_delivered()
        shipment.action_with_courier()
        self.assertEqual(shipment.state, "with_courier")
        with self.assertRaises(UserError):
            shipment.action_with_courier()
        with self.assertRaises(UserError):
            shipment.action_delivered()
        shipment.action_on_the_way()
        self.assertEqual(shipment.state, "on_the_way")
        shipment.action_delivered()
        self.assertEqual(shipment.state, "delivered")
        with self.assertRaises(UserError):
            shipment.action_delivered()

    def test_state_cannot_be_written_or_injected_during_create(self):
        shipment = self._shipment(cargo=True)
        for state in ("with_courier", "on_the_way", "delivered"):
            with self.subTest(state=state):
                with self.assertRaises(UserError):
                    shipment.write({"state": state})
                with self.assertRaises(UserError), self.cr.savepoint():
                    self._shipment(state=state)
        self.assertEqual(shipment.state, "preparing")

    def test_context_defaults_do_not_bypass_reference_or_state_rules(self):
        Request = self.Request.with_context(
            default_state="delivered", default_name="FORGED"
        )
        defaults = Request.default_get(["state", "name"])
        self.assertEqual(defaults, {"state": "preparing", "name": "New"})
        shipment = Request.create(self._request_values())
        self.assertEqual(shipment.state, "preparing")
        self.assertTrue(shipment.name.startswith("SHP/"))
        with self.assertRaises(UserError):
            shipment.with_context(allow_state_change=True).write({"state": "delivered"})

    def test_lifecycle_changes_have_dated_history_even_with_tracking_context(self):
        shipment = self._shipment(cargo=True).with_context(
            tracking_disable=True, mail_notrack=True
        )
        transitions = (
            ("action_with_courier", "Preparing", "With Courier"),
            ("action_on_the_way", "With Courier", "On the Way"),
            ("action_delivered", "On the Way", "Delivered"),
        )
        # mail.thread normally finalizes at commit; flush after each simulated RPC.
        shipment._track_finalize()
        for action, previous, current in transitions:
            getattr(shipment, action)()
            shipment._track_finalize()
            history = shipment.sudo().message_ids.mapped("tracking_value_ids").filtered(
                lambda value: value.field_id.name == "state"
                and value.old_value_char == previous
                and value.new_value_char == current
            )
            self.assertEqual(len(history), 1)
            self.assertTrue(history.mail_message_id.date)

    def test_every_kanban_stage_is_present_even_when_empty(self):
        groups = self.Request.with_context(read_group_expand=True).formatted_read_group(
            [("id", "=", 0)], ["state"], ["__count"]
        )
        self.assertEqual(
            [group["state"] for group in groups],
            ["preparing", "with_courier", "on_the_way", "delivered"],
        )
        self.assertTrue(all(group["__count"] == 0 for group in groups))

    def test_type_code_normalization_and_uniqueness(self):
        Type = self.env["shipment.type"].with_user(self.shipment_manager)
        shipment_type = Type.create(
            {"name": "Test Air", "code": "  test-air  ", "category": "air"}
        )
        self.assertEqual(shipment_type.code, "TEST-AIR")
        with (
            mute_logger("odoo.sql_db"),
            self.assertRaises(UniqueViolation) as raised,
            self.cr.savepoint(),
        ):
            Type.create({"name": "Duplicate", "code": "test-air", "category": "air"})
        self.assertEqual(raised.exception.diag.constraint_name, "shipment_type_code_unique")
        shipment_type.write({"code": "  air-edited  "})
        self.assertEqual(shipment_type.code, "AIR-EDITED")
        default_type = Type.with_context(default_code="  default-parcel  ").create(
            {"name": "Default Parcel", "category": "parcel"}
        )
        self.assertEqual(default_type.code, "DEFAULT-PARCEL")
        explicit_type = Type.with_context(default_code="  test-road  ").create(
            {"name": "Explicit Code", "code": "  explicit-code  ", "category": "road"}
        )
        self.assertEqual(explicit_type.code, "EXPLICIT-CODE")
        with (
            mute_logger("odoo.sql_db"),
            self.assertRaises(UniqueViolation) as raised,
            self.cr.savepoint(),
        ):
            Type.with_context(default_code="  test-road  ").create(
                {"name": "Duplicate From Context", "category": "road"}
            )
        self.assertEqual(raised.exception.diag.constraint_name, "shipment_type_code_unique")

    def test_archived_type_preserves_existing_shipments_but_blocks_new_selection(self):
        shipment = self._shipment()
        self.shipment_type.action_archive()
        self.assertEqual(shipment.shipment_type_id, self.shipment_type)
        shipment.write({"destination": "Updated Alexandria depot"})
        self.assertNotIn(self.shipment_type, self.env["shipment.type"].search([]))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._shipment()
        replacement = self.env["shipment.type"].with_user(self.shipment_manager).create(
            {"name": "Replacement", "code": "TEST-REPLACEMENT", "category": "other"}
        )
        other = self._shipment(shipment_type_id=replacement.id)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            other.write({"shipment_type_id": self.shipment_type.id})

    def test_role_permissions_and_shared_team_records(self):
        for user in (self.shipment_user, self.shipment_manager):
            for model in ("shipment.request", "shipment.cargo"):
                for operation in ("read", "create", "write", "unlink"):
                    with self.subTest(user=user.login, model=model, operation=operation):
                        self.assertTrue(self.env[model].with_user(user).has_access(operation))
        self.assertTrue(self.shipment_manager.has_group("shipment_request.group_shipment_user"))
        shipment = self._shipment(cargo=True)
        colleague_record = shipment.with_user(self.other_shipment_user)
        self.assertEqual(colleague_record.read(["name"])[0]["name"], shipment.name)
        colleague_record.write({"destination": "Team-shared depot"})
        colleague_record.cargo_ids.write({"quantity": 3})
        colleague_record.action_with_courier()
        self.assertEqual(shipment.state, "with_courier")
        self._assert_totals(shipment, 10.5, 0.75)
        with self.assertRaises(UserError):
            colleague_record.unlink()
        self.assertTrue(shipment.exists())

    def test_user_can_read_types_but_only_manager_can_manage_them(self):
        user_type = self.shipment_type.with_user(self.shipment_user)
        self.assertEqual(user_type.read(["code"])[0]["code"], "TEST-ROAD")
        with self.assertRaises(AccessError):
            user_type.write({"name": "Not permitted"})
        with self.assertRaises(AccessError):
            user_type.unlink()
        with self.assertRaises(AccessError):
            self.env["shipment.type"].with_user(self.shipment_user).create(
                {"name": "Not permitted", "code": "DENIED", "category": "other"}
            )
        manager_type = self.env["shipment.type"].with_user(self.shipment_manager).create(
            {"name": "Temporary", "code": "TEMP", "category": "other"}
        )
        manager_type.write({"name": "Edited"})
        manager_type.action_archive()
        self.assertFalse(manager_type.active)
        manager_type.unlink()
        self.assertFalse(manager_type.exists())

    def test_internal_outsider_portal_and_public_have_no_model_access(self):
        for user in (self.outsider, self.portal_user, self.env.ref("base.public_user")):
            for model in ("shipment.request", "shipment.cargo", "shipment.type"):
                Model = self.env[model].with_user(user)
                for operation in ("read", "create", "write", "unlink"):
                    with self.subTest(user=user.login, model=model, operation=operation):
                        self.assertFalse(Model.has_access(operation))
                with self.assertRaises(AccessError):
                    Model.search([])

    def test_shipment_order_renders_required_information(self):
        shipment = self._shipment(cargo=True)
        report = self.env.ref("shipment_request.action_report_shipment_order")
        self.assertEqual(report.report_type, "qweb-pdf")
        self.assertEqual(
            report.group_ids, self.env.ref("shipment_request.group_shipment_user")
        )
        content, output_type = report.with_user(self.shipment_user)._render_qweb_html(
            "shipment_request.action_report_shipment_order", shipment.ids
        )
        self.assertEqual(output_type, "html")
        rendered = content.decode()
        for value in (
            shipment.name,
            self.customer.name,
            shipment.origin,
            shipment.destination,
            shipment.cargo_ids.description,
            "Shipment totals",
            "7.000",
            "0.500",
        ):
            with self.subTest(expected=value):
                self.assertIn(value, rendered)

