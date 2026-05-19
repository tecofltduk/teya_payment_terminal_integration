from odoo import fields, models


class PosOrder(models.Model):
    _inherit = "pos.order"

    teya_gateway_payment_id = fields.Char(string="Gateway Payment ID")
    teya_transaction_id = fields.Char(string="Transaction ID")
    teya_response = fields.Text(string="Response")
