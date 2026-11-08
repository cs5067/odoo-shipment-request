from odoo import api, fields, models, _
from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.exceptions import UserError, ValidationError


class ShipmentRequest(models.Model):
    _name = "shipment.request"
    _description = "Shipment Request"
    _inherit = ["mail.thread"]
    _order = "id desc"

    name = fields.Char(string="Reference", required=True, readonly=True, copy=False, default="New", index=True)
    customer_id = fields.Many2one("res.partner", string="Customer", required=True, ondelete="restrict", tracking=True, index=True)
    shipment_type_id = fields.Many2one("shipment.type", string="Shipment Type", required=True, ondelete="restrict", tracking=True, index=True)
    origin = fields.Text(required=True, tracking=True)
    destination = fields.Text(required=True, tracking=True)
    pickup_date = fields.Date(string="Requested Pickup", required=True, default=fields.Date.context_today, tracking=True)
    delivery_date = fields.Date(string="Requested Delivery", required=True, tracking=True)
    cargo_ids = fields.One2many("shipment.cargo", "shipment_id", string="Cargo Items", copy=True)
    total_weight = fields.Float(string="Total Weight (kg)", compute="_compute_totals", store=True, digits=(16, 3))
    total_volume = fields.Float(string="Total Volume (m³)", compute="_compute_totals", store=True, digits=(16, 3))
    state = fields.Selection(
        [("preparing", "Preparing"), ("with_courier", "With Courier"),
         ("on_the_way", "On the Way"), ("delivered", "Delivered")],
        string="Status", required=True, default="preparing", readonly=True,
        copy=False, tracking=True, index=True, group_expand=True,
    )

    _reference_unique = models.Constraint("UNIQUE(name)", "The shipment reference must be unique.")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        # Creating from any kanban column still opens a Preparing shipment.
        if "state" in fields_list:
            values["state"] = "preparing"
        if "name" in fields_list:
            values["name"] = "New"
        return values

    @api.depends("cargo_ids.total_weight", "cargo_ids.total_volume")
    def _compute_totals(self):
        for shipment in self:
            shipment.total_weight = sum(shipment.cargo_ids.mapped("total_weight"))
            shipment.total_volume = sum(shipment.cargo_ids.mapped("total_volume"))

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for vals in vals_list:
            vals = dict(vals)
            if vals.get("state", "preparing") != "preparing":
                raise UserError(_("New shipments start in Preparing. Use the status buttons to advance them."))
            # Explicit values prevent default_state/default_name contexts bypassing the workflow.
            vals["state"] = "preparing"
            vals["name"] = self.env["ir.sequence"].next_by_code("shipment.request")
            if not vals["name"]:
                raise UserError(_("The shipment reference sequence is missing. Please contact your administrator."))
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        if "state" in vals:
            raise UserError(_("Please use the status buttons to advance a shipment."))
        if "name" in vals and any(shipment.name != vals["name"] for shipment in self):
            raise UserError(_("Shipment references are assigned automatically and cannot be changed."))
        return super().write(vals)

    def _check_cargo_editable(self):
        if any(shipment.state != "preparing" for shipment in self):
            raise UserError(_("Cargo can only be changed while a shipment is Preparing. It is locked after handoff to the courier."))

    @api.ondelete(at_uninstall=True)
    def _unlink_except_preparing(self):
        # Allow Odoo's privileged module cleanup, not a caller-supplied context alone.
        if self.env.su and self.env.context.get(MODULE_UNINSTALL_FLAG):
            return
        if any(shipment.state != "preparing" for shipment in self):
            raise UserError(_("Only shipments in Preparing can be deleted. Shipments handed to the courier are kept with their delivery history."))

    @api.constrains("pickup_date", "delivery_date")
    def _check_dates(self):
        for shipment in self:
            if shipment.pickup_date and shipment.delivery_date and shipment.delivery_date < shipment.pickup_date:
                raise ValidationError(_("The requested delivery date must be on or after the pickup date."))

    @api.constrains("origin", "destination")
    def _check_route(self):
        for shipment in self:
            if not (shipment.origin or "").strip() or not (shipment.destination or "").strip():
                raise ValidationError(_("Please enter both an origin and a destination."))

    @api.constrains("shipment_type_id")
    def _check_active_type(self):
        for shipment in self:
            if not shipment.shipment_type_id.active:
                raise ValidationError(_("This shipment type is archived. Please choose an active shipment type."))

    def _advance(self, expected_state, next_state):
        # Private helper: RPC clients cannot call it with arbitrary target states.
        self.ensure_one()
        self.check_access("write")
        if self.state != expected_state:
            raise UserError(_("This shipment has already moved on, or is not ready for this action. Please refresh it and use the next status button."))
        if expected_state == "preparing" and not self.cargo_ids:
            raise UserError(_("Please add at least one cargo item before handing this shipment to the courier."))
        # Only these validated actions bypass write's state guard; no forgeable context flag.
        # Ensure the status history is retained even if an import/RPC context disables tracking.
        tracked = self.with_context(tracking_disable=False, mail_notrack=False)
        return super(ShipmentRequest, tracked).write({"state": next_state})

    def action_with_courier(self):
        return self._advance("preparing", "with_courier")

    def action_on_the_way(self):
        return self._advance("with_courier", "on_the_way")

    def action_delivered(self):
        return self._advance("on_the_way", "delivered")
