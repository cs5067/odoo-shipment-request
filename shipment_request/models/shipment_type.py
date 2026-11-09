from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ShipmentType(models.Model):
    _name = "shipment.type"
    _description = "Shipment Type"
    _order = "name, id"
    _rec_names_search = ["name", "code"]

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True, copy=False)
    category = fields.Selection(
        [("road", "Road"), ("air", "Air"), ("ocean", "Ocean"),
         ("parcel", "Parcel"), ("other", "Other")],
        required=True,
        default="road",
    )
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "UNIQUE(code)", "A shipment type with this code already exists (including archived types)."
    )

    @api.model_create_multi
    def create(self, vals_list):
        defaults = self.default_get(["code"]) if any("code" not in vals for vals in vals_list) else {}
        return super().create([self._normalize_code({**defaults, **vals}) for vals in vals_list])

    def write(self, vals):
        return super().write(self._normalize_code(vals))

    @api.model
    def _normalize_code(self, vals):
        vals = dict(vals)
        if vals.get("code"):
            vals["code"] = vals["code"].strip().upper()
        return vals

    @api.constrains("name", "code")
    def _check_labels(self):
        for shipment_type in self:
            if not (shipment_type.name or "").strip() or not (shipment_type.code or "").strip():
                raise ValidationError(_("Please enter a name and code for the shipment type."))
