# -*- coding: utf-8 -*-
# Copyright (C) 2021-Today: Part of NextFlowIT. 
# @author:  Part of NextFlowIT. 

from odoo import models, fields, _, api


class PosOrder(models.Model):
    _inherit = "pos.order"

    teya_gateway_payment_id = fields.Char(string="Gateway Payment ID")
    teya_transaction_id = fields.Char(string="Transaction ID")
    teya_response = fields.Text(string="Respons")

    @api.model
    def _order_fields(self, ui_order):
        order_fields = super(PosOrder, self)._order_fields(ui_order)
        order_fields['teya_gateway_payment_id'] = ui_order.get('teya_gateway_payment_id', False)
        order_fields['teya_transaction_id'] = ui_order.get('teya_transaction_id', False)
        order_fields['teya_response'] = ui_order.get('teya_response', False)
        return order_fields


    def _export_for_ui(self, order):
        result = super()._export_for_ui(order)

        result.update({
            'teya_gateway_payment_id': order.teya_gateway_payment_id,
            'teya_transaction_id': order.teya_transaction_id,
            'teya_response': order.teya_response
        })

        return result