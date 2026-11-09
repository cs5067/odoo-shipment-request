FROM odoo:19

# The base image declares /mnt/extra-addons as a volume. Keep application code
# outside it so container recreation cannot preserve an older addon snapshot.
USER root
RUN sed -i 's|^addons_path = .*|addons_path = /opt/odoo/custom-addons|' /etc/odoo/odoo.conf
USER odoo

COPY --chown=odoo:odoo shipment_request/ /opt/odoo/custom-addons/shipment_request/
