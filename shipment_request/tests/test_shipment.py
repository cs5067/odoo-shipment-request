from psycopg2.errors import CheckViolation, UniqueViolation

from odoo import Command
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
        values = {
            "customer_id": self.customer.id,
            "shipment_type_id": self.shipment_type.id,
            "origin": "Cairo warehouse",
            "destination": "Alexandria depot",
            "pickup_date": "2026-11-10",
            "delivery_date": "2026-11-12",
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

    def test_valid_cargo_may_have_zero_weight_and_volume(self):
        shipment = self._shipment()
        self.Cargo.create(
            self._cargo_values(shipment_id=shipment.id, quantity=0.5, weight=0, volume=0)
        )
        shipment.action_with_courier()
        self.assertEqual(shipment.state, "with_courier")
        self._assert_totals(shipment, 0, 0)

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
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self._shipment(delivery_date="2026-11-09")
        shipment = self._shipment()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            shipment.write({"pickup_date": "2026-11-13"})
        shipment.write({"delivery_date": "2026-11-10"})
        self.assertEqual(shipment.pickup_date, shipment.delivery_date)

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
        cargo = shipment.cargo_ids
        colleague_record.unlink()
        self.assertFalse(cargo.exists())

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

