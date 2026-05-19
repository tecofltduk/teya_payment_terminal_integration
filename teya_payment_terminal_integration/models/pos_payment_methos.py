# -*- coding: utf-8 -*-
# Copyright (C) 2021-Today: Part of NextFlowIT. 
# @author:  Part of NextFlowIT. 

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
import base64
from urllib.parse import urlencode

from .teya_credential_provider import (
    get_partner_basic_auth_header,
    get_partner_ref_alpha,
    get_partner_ref_beta,
)

_logger = logging.getLogger(__name__)


def _safe_response_json(response):
    """Parse Teya HTTP body safely; empty or non-JSON bodies must not crash the POS RPC."""
    if not response.text or not response.text.strip():
        return {}
    try:
        return response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        _logger.warning(
            'Teya non-JSON response (HTTP %s): %s',
            response.status_code,
            (response.text or '')[:500],
        )
        return {}


def _teya_http_error_message(response):
    body = _safe_response_json(response)
    if not body and response.text:
        return (response.text or response.reason or '')[:500]
    if not body:
        return response.reason or _('Empty response from Teya')
    if isinstance(body, dict):
        error = body.get('error')
        if error == 'invalid_client':
            desc = body.get('error_description') or body.get('message')
            return _(
                'Teya rejected the integration credentials (invalid_client). '
                'Contact your provider to update OAuth client settings.'
            ) + (f' {desc}' if desc else '')
        return (
            body.get('error_description')
            or body.get('detail')
            or body.get('message')
            or body.get('description')
            or body.get('title')
            or str(body)
        )
    return str(body)


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    def _teya_bearer_authorization(self):
        token = self.teya_auth_token
        if not token:
            raise UserError(_(
                'No Teya access token on this payment method. '
                'Click Generate Token, complete device authorization, then try Get Store again.'
            ))
        return f'Bearer {token}'

    def _get_payment_terminal_selection(self):
        return super(PosPaymentMethod, self)._get_payment_terminal_selection() + [('teya', 'Teya')]

    teya_payment_mode = fields.Selection([('production', "Production"), ("test", "Sandbox")], string="Payment Mode", default='production')
    teya_auth_token = fields.Char(string="Teya Auth Token")
    teya_refresh_token = fields.Char(string="Teya Refresh Token")
    teya_store_id = fields.Many2one("teya.store", string="Store", check_company=True)

    def _is_write_forbidden(self, fields):
        whitelisted_fields = {'sequence', 'teya_auth_token', 'teya_refresh_token' }
        result = super()._is_write_forbidden(fields)
        new_fields = bool(fields - whitelisted_fields and self.open_session_ids)
        if result:
            if not new_fields:
                return new_fields
            else:
                return result
        else:
            return result

    def _teya_refresh_access_token(self):
        """Refresh OAuth tokens for this payment method only. Returns True on success."""
        self.ensure_one()
        payment_method = self.sudo()
        if not payment_method.teya_refresh_token:
            _logger.warning(
                'Teya token refresh skipped for %s: no refresh token.',
                payment_method.display_name,
            )
            return False

        if payment_method.teya_payment_mode == 'test':
            url = 'https://id.teya.xyz/oauth/v2/oauth-token'
        else:
            url = 'https://id.teya.com/oauth/v2/oauth-token'

        payload = urlencode({
            'refresh_token': payment_method.teya_refresh_token,
            'grant_type': 'refresh_token',
        })
        headers = {
            'Authorization': get_partner_basic_auth_header(),
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        _logger.info('Teya token refresh for payment method %s', payment_method.display_name)
        try:
            response = requests.post(url, headers=headers, data=payload, timeout=30)
        except requests.RequestException as error:
            _logger.warning(
                'Teya token refresh connection error for %s: %s',
                payment_method.display_name,
                error,
            )
            return False

        _logger.info('Teya token refresh response status %s', response.status_code)
        if response.status_code != 200:
            _logger.warning(
                'Teya token refresh failed for %s (HTTP %s): %s',
                payment_method.display_name,
                response.status_code,
                _teya_http_error_message(response),
            )
            return False

        tokens = response.json()
        payment_method.write({
            'teya_auth_token': tokens.get('access_token'),
            'teya_refresh_token': tokens.get('refresh_token'),
        })
        return True

    @api.model
    def _cron_regenerate_refresh_token(self):
        """Scheduled job: refresh tokens for all Teya payment methods."""
        for payment_method in self.sudo().search([('use_payment_terminal', '=', 'teya')]):
            payment_method._teya_refresh_access_token()

    def get_teya_payment_url(self):
        if self.teya_payment_mode == 'test':
            return "https://id.teya.xyz/oauth/v2"
        else:
            return "https://id.teya.com/oauth/v2"
    
    def nf_generate_auth_token(self):
        if self._is_write_forbidden(set(['teya_auth_token','teya_refresh_token'])):
            raise UserError(_('Please close and validate the following open PoS Sessions before modifying this payment method.\n'
                            'Open sessions: %s', (' '.join(self.open_session_ids.mapped('name')),)))
        
        if self.teya_payment_mode == 'test':
            devide_url =  "https://id.teya.xyz/oauth/v2/device"
        else:
            devide_url =  "https://id.teya.com/oauth/v2/device"

        divice_payload = (
            f'client_id={get_partner_ref_alpha()}&client_secret={get_partner_ref_beta()}'
        )
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        try:
            response = requests.request("POST", devide_url, headers=headers, data=divice_payload, timeout=30)
        except requests.RequestException as error:
            raise UserError(_('Could not connect to Teya: %s', error)) from error

        if response.status_code != 200:
            raise UserError(_(
                'Teya device authorization failed (HTTP %s): %s',
                response.status_code,
                _teya_http_error_message(response),
            ))

        qr_code_str = response.json().get('qr_code')
        if not qr_code_str:
            raise UserError(_('Teya did not return a QR code. Please try again.'))

        if qr_code_str.startswith("data:image"):
            qr_code_str = qr_code_str.split(",")[1]
        missing_padding = len(qr_code_str) % 4
        if missing_padding:
            qr_code_str += '=' * (4 - missing_padding)
        qr_code_bytes = base64.b64decode(qr_code_str)
        qr_code_bin = base64.b64encode(qr_code_bytes)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Verify Device'),
            'res_model': 'teya.verify.wizard',
            'view_mode': 'form',
            'context': {
                'default_qr_code': qr_code_bin,
                'default_verification_uri': response.json().get('verification_url_complete'),
                'default_device_code': response.json().get('device_code'),
                'default_payment_method_id': self.id,
            },
            'target': 'new',
        }

    def nf_get_teya_stores(self):
        payment_method = self

        if self._is_write_forbidden(set(['teya_auth_token','teya_refresh_token'])):
            raise UserError(_('Please close and validate the following open PoS Sessions before modifying this payment method.\n'
                            'Open sessions: %s', (' '.join(self.open_session_ids.mapped('name')),)))
                            

        if payment_method:
            url = ""
            if payment_method.teya_payment_mode == "test":
                url = f"https://api.teya.xyz/poslink/v1/stores"
            else:
                url = f"https://api.teya.com/poslink/v1/stores"
            payload = {}
            headers = {
                'Accept': 'application/json',
                'Authorization': payment_method._teya_bearer_authorization(),
            }
            try:
                response = requests.request("GET", url, headers=headers, data=payload, timeout=30)
            except requests.RequestException as error:
                raise UserError(_('Could not connect to Teya: %s', error)) from error

            if response.status_code == 401:
                if not payment_method.teya_refresh_token:
                    raise UserError(_(
                        'Teya access token expired and no refresh token is available. '
                        'Click Generate Token and authorize the device again.'
                    ))
                if not payment_method._teya_refresh_access_token():
                    raise UserError(_(
                        'Teya access token expired and refresh failed for "%(method)s". '
                        'Click Generate Token on that payment method and authorize the device again.',
                        method=payment_method.display_name,
                    ))
                payment_method.invalidate_recordset(['teya_auth_token', 'teya_refresh_token'])
                headers['Authorization'] = payment_method._teya_bearer_authorization()
                response = requests.request("GET", url, headers=headers, data=payload, timeout=30)

            if response.status_code != 200:
                raise UserError(_(
                    'Teya could not load stores (HTTP %s): %s',
                    response.status_code,
                    _teya_http_error_message(response),
                ))

            if response.status_code == 200:
                response_data = response.json()

                stores = response_data.get('stores')
                for store in stores:
                    address = store.get('address')
                    country_id = self.env['res.country'].search([('code', '=', address.get('country'))], limit=1)

                    company = payment_method.company_id
                    get_store = self.env['teya.store'].search([
                        ('teya_store_id', '=', store.get('id')),
                        '|', ('company_id', '=', False), ('company_id', '=', company.id),
                    ], limit=1)
                    if not get_store:
                        get_store = self.env['teya.store'].create({
                            'teya_store_id': store.get('id'),
                            'name': store.get('name'),
                            'city': address.get("city"),
                            'country_id': country_id.id,
                            'street_1': address.get('street_address_line_1'),
                            'street_2': address.get('street_address_line_2'),
                            'zipcode': address.get('zipcode'),
                            'paymen_method_id': payment_method.id,
                            'company_id': company.id,
                        })
                    elif not get_store.company_id and company:
                        get_store.company_id = company

                    # Get Terminals and create 
                    if self.teya_payment_mode == "test":
                        url = f"https://api.teya.xyz/poslink/v1/stores/{get_store.teya_store_id}/terminals"
                    else:
                        url = f"https://api.teya.com/poslink/v1/stores/{get_store.teya_store_id}/terminals"

                    terminal_response = requests.request("GET", url, headers=headers, data=payload, timeout=30)

                    if terminal_response.status_code == 200:
                        terminals = terminal_response.json().get('terminals')
                        for terminal in terminals:
                            find_store = self.env['teya.terminal.device'].search([('name', '=', terminal.get('serial_number'))])
                            if not find_store:
                                self.env['teya.terminal.device'].create({'name': terminal.get('serial_number'), 'terminal_id': terminal.get('terminal_id'), 'terminal_name': terminal.get('terminal_name'), 'store_id': get_store.id})   
        else:
            raise UserError(_("Can not found any integrated pos payment method!"))
        

    def proxy_teya_payment_request(self, data, config_id, order_token, operation=False):
        url =  ""
        if self.teya_payment_mode == "test":
            url = f"https://api.teya.xyz/poslink/v2/payment-requests"
        else:
            url = f"https://api.teya.com/poslink/v2/payment-requests"


        config = self.env['pos.config'].browse(config_id)
        terminal_id = config.teya_terminal_id
        store_id = self.teya_store_id
        if not terminal_id:
            raise UserError(_('No Teya terminal configured on this Point of Sale.'))
        if not store_id:
            raise UserError(_(
                'No Teya store on this payment method. '
                'Open the payment method, click Get Store, then try again.'
            ))
        data.update({
            "store_id": store_id.teya_store_id,
            "terminal_id": terminal_id.terminal_id,
        })

        headers = {
            "Idempotency-Key": order_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": self._teya_bearer_authorization(),
        }
        _logger.info('\n\n\n -----headers----->%s, %s',data,headers)

        try:
            response = requests.post(url, json=data, headers=headers, timeout=60)
        except requests.RequestException as error:
            _logger.exception('Teya payment request failed: %s', error)
            return {
                'status_code': 500,
                'message': str(error),
            }
        _logger.info('Teya payment request HTTP %s', response.status_code)

        if response.status_code == 401:
            _logger.info('Teya access token expired. Refreshing token for %s.', self.display_name)
            if not self._teya_refresh_access_token():
                return {
                    'status_code': 401,
                    'message': _(
                        'Teya authentication failed for "%(method)s". '
                        'The access token expired and the refresh token is invalid or expired. '
                        'Open Point of Sale → Configuration → Payment Methods → %(method)s, '
                        'click Generate Token, complete device authorization, then try the payment again.'
                    ) % {'method': self.display_name},
                }
            self.invalidate_recordset(['teya_auth_token', 'teya_refresh_token'])
            headers['Authorization'] = self._teya_bearer_authorization()
            response = requests.post(url, json=data, headers=headers, timeout=60)
            _logger.info('Teya payment request after refresh HTTP %s', response.status_code)

        body = _safe_response_json(response)

        if response.status_code == 401:
            return {
                'status_code': response.status_code,
                'message': body.get('message') or _teya_http_error_message(response) or _(
                    'Teya rejected the payment (unauthorized). Re-authorize the payment method with Generate Token.'
                ),
            }
        if response.status_code == 400:
            return {
                'status_code': response.status_code,
                'message': body.get('description') or body.get('message') or _teya_http_error_message(response),
            }
        if response.status_code >= 400:
            return {
                'status_code': response.status_code,
                'message': _teya_http_error_message(response),
            }
        if not body:
            return {
                'status_code': response.status_code or 500,
                'message': _('Empty response from Teya payment API. Please retry.'),
            }
        return body
        
    def teya_payment_request_status(self, payment_req_id, pos_session_id):
        if self.teya_payment_mode == "test":
            url = f"https://api.teya.xyz/poslink/v1/payment-requests/{payment_req_id}"
        else:
            url = f"https://api.teya.com/poslink/v1/payment-requests/{payment_req_id}"
            
        pos_session = self.env['pos.session'].browse(pos_session_id)
        headers = {
            "Accept": "application/json",
            "Authorization": self._teya_bearer_authorization(),
        }

        _logger.info('\n\n\n -----teya payemnt request status start ----->',)
        response = requests.get(url, headers=headers)

        body = _safe_response_json(response)
        _logger.info('teya_payment_request_status HTTP %s body %s', response.status_code, body)

        if response.status_code == 401:
            _logger.info('Teya access token expired. Refreshing token for %s.', self.display_name)
            if not self._teya_refresh_access_token():
                return {
                    'status_code': 401,
                    'message': _(
                        'Teya authentication failed for "%(method)s". '
                        'Re-authorize with Generate Token on the payment method.'
                    ) % {'method': self.display_name},
                }
            self.invalidate_recordset(['teya_auth_token', 'teya_refresh_token'])
            headers['Authorization'] = self._teya_bearer_authorization()
            response = requests.get(url, headers=headers, timeout=30)
            body = _safe_response_json(response)

        if response.status_code == 401:
            return {
                'status_code': response.status_code,
                'message': body.get('message') or _teya_http_error_message(response),
            }
        if body.get('status') in ("SUCCESSFUL", "CANCELLED", "FAILED"):
            self.env['bus.bus'].sudo()._sendone(
                pos_session._get_bus_channel_name(),
                'TEYA_LATEST_RESPONSE',
                {
                    'config_id': pos_session.config_id.id,
                    'payment_request_id': payment_req_id,
                    'response': body,
                },
            )
        return body
        
        # return {
        #         "payment_request_id": "dfc4fc52-8293-45b6-9f3e-b3b0f8f88188",
        #         "requested_amount": {
        #             "currency": "GBP",
        #             "amount": 10,
        #             "tip": 0
        #         },
        #         "status": "Success",
        #         "transaction_type": "SALE",
        #         "created_at": "2022-06-15T16:24:120Z",
        #         "updated_at": "2022-06-15T16:26:120Z",
        #         "source_reference_id": "423897410",
        #         "merchant_reference": "423897410",
        #         "terminal_id": "70dc65ba-1c13-492a-82a0-15821e5f63ba",
        #         "store_id": "f04fe1ce-e7bd-4c5b-b873-b156643c0bc3"
        #     }

