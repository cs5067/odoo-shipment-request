"""Run through `odoo shell` only, via setup-demo.sh. Not addon installation data."""

from odoo import Command


Users = env["res.users"].with_context(
    active_test=False,
    no_reset_password=True,
    mail_create_nosubscribe=True,
    tracking_disable=True,
)

for login, name, group_xmlid, is_manager in (
    (
        "shipment.manager",
        "Shipment Demo Manager",
        "shipment_request.group_shipment_manager",
        True,
    ),
    (
        "shipment.user",
        "Shipment Demo User",
        "shipment_request.group_shipment_user",
        False,
    ),
):
    user = Users.search([("login", "=", login)], limit=1)
    if user:
        # Do not change an existing person's credentials or permissions.
        print(f"Keeping existing account and password: {login}")
    else:
        user = Users.create({
            "name": name,
            "login": login,
            "password": "ShipmentDemo!2026",
            "tz": "UTC",
            "group_ids": [Command.set([env.ref(group_xmlid).id])],
        })
        print(f"Created demo account: {login}")

    if (
        not user.active
        or user.share
        or not user.has_group("shipment_request.group_shipment_user")
        or user.has_group("shipment_request.group_shipment_manager") != is_manager
        or user.has_group("base.group_system")
        or user.has_group("base.group_erp_manager")
    ):
        raise RuntimeError(
            f"{login} already exists with unexpected access. No demo account "
            "changes were saved. In Settings, use a different login for that "
            "existing account or assign the expected shipment role without "
            "administration access, then rerun setup."
        )

customer_name = "Sample Logistics Customer"
if not env["res.partner"].with_context(active_test=False).search_count(
    [("name", "=", customer_name)]
):
    env["res.partner"].create({
        "name": customer_name,
        "is_company": True,
        "street": "10 Warehouse Road",
        "city": "Cairo",
        "country_id": env.ref("base.eg").id,
    })

env["ir.config_parameter"].sudo().set_param("report.url", "http://127.0.0.1:8069")
env.cr.commit()
print("Reviewer accounts, sample customer, and PDF configuration are ready.")
