# -*- coding: utf-8 -*-
# Copyright (C) 2021-Today: Part of NextFlowIT.
# @author:  Part of NextFlowIT.

from odoo import models, fields, api


class PosConfig(models.Model):
    _inherit = "pos.config"

    teya_terminal_id = fields.Many2one(
        'teya.terminal.device',
        string='Terminal Id',
        domain="[('store_id', '=', teya_store_id)]",
    )
    teya_store_id = fields.Many2one(
        'teya.store',
        string='Store Id',
        compute='_compute_store_id',
        store=True,
    )

    @api.depends('payment_method_ids', 'payment_method_ids.teya_store_id')
    def _compute_store_id(self):
        for rec in self:
            teya_pm = rec.payment_method_ids.filtered(
                lambda pm: pm.use_payment_terminal == 'teya'
            )[:1]
            rec.teya_store_id = teya_pm.teya_store_id if teya_pm else False
