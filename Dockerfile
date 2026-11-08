FROM odoo:19

COPY --chown=odoo:odoo shipment_request/ /mnt/extra-addons/shipment_request/
