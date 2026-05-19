from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    module_teya_payment_terminal_integration = fields.Boolean(
        string="Teya Payment Terminal",
        help="The transactions are processed by Teya.",
    )
    teya_terminal_id = fields.Many2one("teya.terminal.device", related="pos_config_id.teya_terminal_id", readonly=False)
    teya_store_id = fields.Many2one("teya.store", related="pos_config_id.teya_store_id", readonly=False)
