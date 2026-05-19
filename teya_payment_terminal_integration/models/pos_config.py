from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    teya_store_id = fields.Many2one("teya.store", compute="_compute_teya_store_id", store=True)
    teya_terminal_id = fields.Many2one("teya.terminal.device", compute="_compute_teya_terminal_id", store=True)

    @api.depends("payment_method_ids", "payment_method_ids.teya_store_id")
    def _compute_teya_store_id(self):
        for config in self:
            payment_method = config.payment_method_ids.filtered(
                lambda pm: pm.use_payment_terminal == "teya"
            )[:1]
            config.teya_store_id = payment_method.teya_store_id

    @api.depends("teya_store_id")
    def _compute_teya_terminal_id(self):
        Terminal = self.env["teya.terminal.device"]
        for config in self:
            if not config.teya_store_id:
                config.teya_terminal_id = False
                continue
            terminals = Terminal.search(
                [("store_id", "=", config.teya_store_id.id)],
                order="id",
            )
            config.teya_terminal_id = terminals[:1]
