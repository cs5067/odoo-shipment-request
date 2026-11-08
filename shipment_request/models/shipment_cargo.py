import math

from odoo import api, fields, models, _
from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.exceptions import ValidationError


class ShipmentCargo(models.Model):
    _name = "shipment.cargo"
    _description = "Shipment Cargo Item"
    _order = "sequence, id"
    _rec_name = "description"

    shipment_id = fields.Many2one("shipment.request", string="Shipment", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    description = fields.Char(required=True)
    quantity = fields.Float(required=True, default=1.0, digits=(16, 3))
    weight = fields.Float(string="Unit Weight (kg)", required=True, default=0.0, digits=(16, 3), help="Weight of one unit in kilograms.")
    volume = fields.Float(string="Unit Volume (m³)", required=True, default=0.0, digits=(16, 3), help="Volume of one unit in cubic metres.")
    total_weight = fields.Float(string="Weight (kg)", compute="_compute_totals", store=True, digits=(16, 3))
    total_volume = fields.Float(string="Volume (m³)", compute="_compute_totals", store=True, digits=(16, 3))

    _quantity_positive = models.Constraint("CHECK(quantity > 0)", "Cargo quantity must be greater than zero.")
    _weight_nonnegative = models.Constraint("CHECK(weight >= 0)", "Cargo weight cannot be negative.")
    _volume_nonnegative = models.Constraint("CHECK(volume >= 0)", "Cargo volume cannot be negative.")

    @api.model_create_multi
    def create(self, vals_list):
        default_shipment = (
            self.default_get(["shipment_id"]).get("shipment_id")
            if any("shipment_id" not in vals for vals in vals_list) else False
        )
        shipment_ids = {vals.get("shipment_id", default_shipment) for vals in vals_list}
        self.env["shipment.request"].browse(shipment_ids - {False, None})._check_cargo_editable()
        return super().create(vals_list)

    def write(self, vals):
        shipments = self.mapped("shipment_id")
        if vals.get("shipment_id"):
            shipments |= self.env["shipment.request"].browse(vals["shipment_id"])
        # Reassignment must be allowed on both the old and the new shipment.
        shipments._check_cargo_editable()
        return super().write(vals)

    @api.ondelete(at_uninstall=True)
    def _unlink_only_preparing(self):
        if self.env.su and self.env.context.get(MODULE_UNINSTALL_FLAG):
            return
        self.mapped("shipment_id")._check_cargo_editable()

    @api.depends("quantity", "weight", "volume")
    def _compute_totals(self):
        for cargo in self:
            cargo.total_weight = cargo.quantity * cargo.weight
            cargo.total_volume = cargo.quantity * cargo.volume

    @api.constrains("description", "quantity", "weight", "volume")
    def _check_cargo(self):
        for cargo in self:
            if not (cargo.description or "").strip():
                raise ValidationError(_("Please add a description for each cargo item."))
            if not all(math.isfinite(value) for value in (cargo.quantity, cargo.weight, cargo.volume)):
                raise ValidationError(_("Cargo quantities, weights, and volumes must be finite numbers."))
            if cargo.quantity <= 0:
                raise ValidationError(_("Cargo quantity must be greater than zero."))
            if cargo.weight < 0 or cargo.volume < 0:
                raise ValidationError(_("Cargo weight and volume cannot be negative."))
