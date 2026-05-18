# -*- coding: utf-8 -*-
# Copyright (C) 2021-Today: Part of NextFlowIT.
# @author:  Part of NextFlowIT.

from odoo import models, fields, api


class TerminalDevice(models.Model):
    _name = 'teya.terminal.device'
    _description = 'Teya Terminal Device'
    _check_company_auto = True

    name = fields.Char(string='Serial Number')
    store_id = fields.Many2one("teya.store", string="Store", required=True, check_company=True)
    terminal_id = fields.Char(string='Terminal ID', required=True)
    terminal_name = fields.Char(string='Terminal Name')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        compute='_compute_company_id',
        store=True,
        readonly=True,
        index=True,
    )

    @api.depends('store_id', 'store_id.company_id')
    def _compute_company_id(self):
        for terminal in self:
            terminal.company_id = terminal.store_id.company_id
