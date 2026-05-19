# -*- coding: utf-8 -*-
# Copyright (C) 2021-Today: Part of NextFlowIT.
# @author:  Part of NextFlowIT.

from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    module_teya_payment_terminal_integration = fields.Boolean(
        string='Teya Payment Terminal',
        help='The transactions are processed by Teya.',
    )
    # pos_ prefix required on Odoo 17 so values are written to pos.config on save.
    pos_teya_terminal_id = fields.Many2one(
        'teya.terminal.device',
        related='pos_config_id.teya_terminal_id',
        readonly=False,
    )
    pos_teya_store_id = fields.Many2one(
        'teya.store',
        related='pos_config_id.teya_store_id',
        readonly=False,
    )
