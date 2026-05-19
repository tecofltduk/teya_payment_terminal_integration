# -*- coding: utf-8 -*-
# Copyright (C) 2021-Today: Part of NextFlowIT.
# @author:  Part of NextFlowIT.

import requests

from odoo import models, fields, _
from odoo.exceptions import UserError

from .pos_payment_methos import _teya_http_error_message


class TeyaStores(models.Model):
    _name = 'teya.store'
    _description = "Teya Terminal Stores"
    _check_company_auto = True

    name = fields.Char(string="Name")
    teya_store_id = fields.Char(string="Store id")
    city = fields.Char(string="City")
    country_id = fields.Many2one("res.country", string="Country")
    street_1 = fields.Char(string="Street 1")
    street_2 = fields.Char(string="Street 2")
    zipcode = fields.Char(string="Zipcode")
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
    )
    paymen_method_id = fields.Many2one('pos.payment.method', string="Payment method")

    def nf_get_store_terminals(self):
        """Fetch terminals for this store from Teya and create local records."""
        Terminal = self.env['teya.terminal.device']
        for store in self:
            payment_method = store.paymen_method_id
            if not payment_method:
                raise UserError(_(
                    'No payment method is linked to this store. '
                    'Use "Get Store" on the Teya payment method first.'
                ))
            if not store.teya_store_id:
                raise UserError(_('This store has no Teya store ID.'))

            if payment_method.teya_payment_mode == 'test':
                url = f'https://api.teya.xyz/poslink/v1/stores/{store.teya_store_id}/terminals'
            else:
                url = f'https://api.teya.com/poslink/v1/stores/{store.teya_store_id}/terminals'

            headers = {
                'Accept': 'application/json',
                'Authorization': payment_method._teya_bearer_authorization(),
            }
            try:
                response = requests.get(url, headers=headers, timeout=30)
            except requests.RequestException as error:
                raise UserError(_('Could not connect to Teya: %s', error)) from error

            if response.status_code == 401:
                if not payment_method.teya_refresh_token:
                    raise UserError(_(
                        'Teya access token expired and no refresh token is available. '
                        'Click Generate Token on the payment method and authorize again.'
                    ))
                if not payment_method._teya_refresh_access_token():
                    raise UserError(_(
                        'Teya access token expired and refresh failed for "%(method)s". '
                        'Click Generate Token on that payment method and authorize again.',
                        method=payment_method.display_name,
                    ))
                payment_method.invalidate_recordset(['teya_auth_token', 'teya_refresh_token'])
                headers['Authorization'] = payment_method._teya_bearer_authorization()
                response = requests.get(url, headers=headers, timeout=30)

            if response.status_code != 200:
                raise UserError(_(
                    'Teya could not load terminals (HTTP %s): %s',
                    response.status_code,
                    _teya_http_error_message(response),
                ))

            for terminal in response.json().get('terminals') or []:
                teya_terminal_id = terminal.get('terminal_id')
                if not teya_terminal_id:
                    continue
                existing = Terminal.search([
                    ('store_id', '=', store.id),
                    ('terminal_id', '=', teya_terminal_id),
                ], limit=1)
                if existing:
                    continue
                Terminal.create({
                    'name': terminal.get('serial_number'),
                    'terminal_id': teya_terminal_id,
                    'terminal_name': terminal.get('terminal_name'),
                    'store_id': store.id,
                })
