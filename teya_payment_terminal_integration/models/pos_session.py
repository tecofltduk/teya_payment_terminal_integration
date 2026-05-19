from odoo import api, models


class PosSessios(models.Model):
    _inherit = "pos.session"

    @api.model_create_multi
    def create(self, vals_list):
        payment_methods = self.env["pos.payment.method"].sudo().search([("use_payment_terminal", "=", "teya")])
        payment_methods.sudo()._cron_regenerate_refresh_token()
        return super().create(vals_list)

    def _validate_session(self, balancing_account=False, amount_to_balance=0, bank_payment_method_diffs=None):
        res = super()._validate_session(balancing_account, amount_to_balance, bank_payment_method_diffs)
        payment_methods = self.env["pos.payment.method"].sudo().search([("use_payment_terminal", "=", "teya")])
        payment_methods.sudo()._cron_regenerate_refresh_token()
        return res
