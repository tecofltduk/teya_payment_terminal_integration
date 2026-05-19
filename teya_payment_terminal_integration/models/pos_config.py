from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = "pos.config"

    teya_terminal_id = fields.Many2one("teya.terminal.device", string="Terminal Id")
    teya_store_id = fields.Many2one("teya.store", string="Store Id", compute="_compute_store_id", store=True)

    @api.depends("payment_method_ids", "payment_method_ids.teya_store_id")
    def _compute_store_id(self):
        for rec in self:
            payment_method_id = rec.payment_method_ids.filtered(lambda x: x.use_payment_terminal == "teya")
            if payment_method_id.teya_store_id:
                rec.teya_store_id = payment_method_id.teya_store_id.id
            else:
                rec.teya_store_id = False
