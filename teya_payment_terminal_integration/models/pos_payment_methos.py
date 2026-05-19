import base64
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .teya_credential_provider import (
    get_partner_basic_auth_header,
    get_partner_ref_alpha,
    get_partner_ref_beta,
)

_logger = logging.getLogger(__name__)


def _teya_http_error_message(response):
    try:
        body = response.json()
    except (ValueError, requests.exceptions.JSONDecodeError):
        return (response.text or response.reason or "")[:500]
    if isinstance(body, dict):
        error = body.get("error")
        if error == "invalid_client":
            desc = body.get("error_description") or body.get("message")
            return _(
                "Teya rejected the integration credentials (invalid_client). "
                "Contact your provider to update OAuth client settings."
            ) + (f" {desc}" if desc else "")
        return (
            body.get("error_description")
            or body.get("detail")
            or body.get("message")
            or body.get("description")
            or body.get("title")
            or str(body)
        )
    return str(body)


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    def _teya_bearer_authorization(self):
        token = self.teya_auth_token
        if not token:
            raise UserError(
                _(
                    "No Teya access token on this payment method. "
                    "Click Generate Token, complete device authorization, then try Get Store again."
                )
            )
        return f"Bearer {token}"

    def _get_payment_terminal_selection(self):
        return super()._get_payment_terminal_selection() + [("teya", "Teya")]

    teya_payment_mode = fields.Selection(
        [("production", "Production"), ("test", "Sandbox")],
        string="Payment Mode",
        default="production",
    )
    teya_auth_token = fields.Char(string="Teya Auth Token")
    teya_refresh_token = fields.Char(string="Teya Refresh Token")
    teya_store_id = fields.Many2one("teya.store", string="Store")

    def _is_write_forbidden(self, fields):
        whitelisted_fields = {"sequence", "teya_auth_token", "teya_refresh_token"}
        return bool(fields - whitelisted_fields and self.open_session_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("use_payment_terminal") == "teya":
                vals.setdefault("teya_payment_mode", "production")
        records = super().create(vals_list)
        return records

    def write(self, vals):
        if vals.get("use_payment_terminal") == "teya":
            vals.setdefault("teya_payment_mode", "production")
        return super().write(vals)

    @api.onchange("use_payment_terminal")
    def _onchange_use_payment_terminal(self):
        super()._onchange_use_payment_terminal()
        if self.use_payment_terminal:
            self.payment_method_type = "terminal"
        if self.use_payment_terminal == "teya" and not self.teya_payment_mode:
            self.teya_payment_mode = "production"

    @api.model
    def _cron_regenerate_refresh_token(self):
        payment_methods = self.sudo().search([("use_payment_terminal", "=", "teya")])
        for payment_method in payment_methods:
            if not payment_method.teya_refresh_token:
                _logger.warning(
                    "Skipping Teya token refresh for %s: no refresh token.",
                    payment_method.display_name,
                )
                continue
            if payment_method.teya_payment_mode == "test":
                url = "https://id.teya.xyz/oauth/v2/oauth-token"
            else:
                url = "https://id.teya.com/oauth/v2/oauth-token"
            payload = f"refresh_token={payment_method.teya_refresh_token}&grant_type=refresh_token"
            headers = {
                "Authorization": get_partner_basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            }

            response = requests.request("POST", url, headers=headers, data=payload, timeout=30)
            if response.status_code == 200:
                payment_method.sudo().write(
                    {
                        "teya_auth_token": response.json().get("access_token"),
                        "teya_refresh_token": response.json().get("refresh_token"),
                    }
                )
            else:
                _logger.warning(
                    "Teya token refresh failed for %s (HTTP %s): %s",
                    payment_method.display_name,
                    response.status_code,
                    _teya_http_error_message(response),
                )

    def get_teya_payment_url(self):
        if self.teya_payment_mode == "test":
            return "https://id.teya.xyz/oauth/v2"
        return "https://id.teya.com/oauth/v2"

    def nf_generate_auth_token(self):
        if self._is_write_forbidden({"teya_auth_token", "teya_refresh_token"}):
            raise UserError(
                _(
                    "Please close and validate the following open PoS Sessions before modifying this payment method.\n"
                    "Open sessions: %s",
                    (" ".join(self.open_session_ids.mapped("name")),),
                )
            )

        if self.teya_payment_mode == "test":
            devide_url = "https://id.teya.xyz/oauth/v2/device"
        else:
            devide_url = "https://id.teya.com/oauth/v2/device"

        divice_payload = (
            f"client_id={get_partner_ref_alpha()}&client_secret={get_partner_ref_beta()}"
        )
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            response = requests.request(
                "POST", devide_url, headers=headers, data=divice_payload, timeout=30
            )
        except requests.RequestException as error:
            raise UserError(_("Could not connect to Teya: %s", error)) from error
        if response.status_code != 200:
            raise UserError(
                _("Teya device authorization failed (HTTP %s): %s", response.status_code, _teya_http_error_message(response))
            )

        qr_code_str = response.json().get("qr_code")
        if not qr_code_str:
            raise UserError(_("Teya did not return a QR code. Please try again."))

        if qr_code_str.startswith("data:image"):
            qr_code_str = qr_code_str.split(",")[1]
        missing_padding = len(qr_code_str) % 4
        if missing_padding:
            qr_code_str += "=" * (4 - missing_padding)
        qr_code_bytes = base64.b64decode(qr_code_str)
        qr_code_bin = base64.b64encode(qr_code_bytes)

        return {
            "type": "ir.actions.act_window",
            "name": _("Verify Device"),
            "res_model": "teya.verify.wizard",
            "view_mode": "form",
            "context": {
                "default_qr_code": qr_code_bin,
                "default_verification_uri": response.json().get("verification_url_complete"),
                "default_device_code": response.json().get("device_code"),
                "default_payment_method_id": self.id,
            },
            "target": "new",
        }

    def nf_get_teya_stores(self):
        payment_method = self
        if self._is_write_forbidden({"teya_auth_token", "teya_refresh_token"}):
            raise UserError(
                _(
                    "Please close and validate the following open PoS Sessions before modifying this payment method.\n"
                    "Open sessions: %s",
                    (" ".join(self.open_session_ids.mapped("name")),),
                )
            )

        if not payment_method:
            raise UserError(_("Can not found any integrated pos payment method!"))

        if payment_method.teya_payment_mode == "test":
            url = "https://api.teya.xyz/poslink/v1/stores"
        else:
            url = "https://api.teya.com/poslink/v1/stores"
        payload = {}
        headers = {
            "Accept": "application/json",
            "Authorization": payment_method._teya_bearer_authorization(),
        }
        try:
            response = requests.request("GET", url, headers=headers, data=payload, timeout=30)
        except requests.RequestException as error:
            raise UserError(_("Could not connect to Teya: %s", error)) from error

        if response.status_code == 401:
            if not payment_method.teya_refresh_token:
                raise UserError(
                    _(
                        "Teya access token expired and no refresh token is available. "
                        "Click Generate Token and authorize the device again."
                    )
                )
            payment_method._cron_regenerate_refresh_token()
            headers["Authorization"] = payment_method._teya_bearer_authorization()
            response = requests.request("GET", url, headers=headers, data=payload, timeout=30)

        if response.status_code != 200:
            raise UserError(
                _("Teya could not load stores (HTTP %s): %s", response.status_code, _teya_http_error_message(response))
            )

        if response.status_code == 200:
            stores = response.json().get("stores")
            for store in stores:
                address = store.get("address")
                country_id = self.env["res.country"].search([("code", "=", address.get("country"))], limit=1)

                get_store = self.env["teya.store"].search([("teya_store_id", "=", store.get("id"))])
                if not get_store:
                    get_store = self.env["teya.store"].create(
                        {
                            "teya_store_id": store.get("id"),
                            "name": store.get("name"),
                            "city": address.get("city"),
                            "country_id": country_id.id,
                            "street_1": address.get("street_address_line_1"),
                            "street_2": address.get("street_address_line_2"),
                            "zipcode": address.get("zipcode"),
                            "paymen_method_id": payment_method.id,
                        }
                    )

                if self.teya_payment_mode == "test":
                    terminals_url = f"https://api.teya.xyz/poslink/v1/stores/{get_store.teya_store_id}/terminals"
                else:
                    terminals_url = f"https://api.teya.com/poslink/v1/stores/{get_store.teya_store_id}/terminals"

                terminal_response = requests.request("GET", terminals_url, headers=headers, data=payload)
                if terminal_response.status_code == 200:
                    terminals = terminal_response.json().get("terminals")
                    for terminal in terminals:
                        find_store = self.env["teya.terminal.device"].search([("name", "=", terminal.get("serial_number"))])
                        if not find_store:
                            self.env["teya.terminal.device"].create(
                                {
                                    "name": terminal.get("serial_number"),
                                    "terminal_id": terminal.get("terminal_id"),
                                    "terminal_name": terminal.get("terminal_name"),
                                    "store_id": get_store.id,
                                }
                            )

# ==================== (backend payment RPC only) ==========================
    def proxy_teya_payment_request(self, data, config_id, order_token, operation=False):
        if self.teya_payment_mode == "test":
            url = "https://api.teya.xyz/poslink/v2/payment-requests"
        else:
            url = "https://api.teya.com/poslink/v2/payment-requests"

        config = self.env["pos.config"].browse(config_id)
        terminal_id = config.teya_terminal_id
        store_id = self.teya_store_id
        data.update(
            {
                "store_id": store_id.teya_store_id,
                "terminal_id": terminal_id.terminal_id,
            }
        )

        headers = {
            "Idempotency-Key": order_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": self._teya_bearer_authorization(),
        }
        _logger.info("Teya proxy request headers/data: %s, %s", data, headers)

        response = requests.post(url, json=data, headers=headers)
        _logger.info("Teya proxy response: %s, code %s", response, response.status_code)

        if response.status_code == 401:
            _logger.info("Teya token expired. Attempting token refresh in proxy_teya_payment_request.")
            self._cron_regenerate_refresh_token()
            headers["Authorization"] = self._teya_bearer_authorization()
            response = requests.post(url, json=data, headers=headers)
            _logger.info("Teya proxy response after refresh: %s, code %s", response, response.status_code)

        if response.status_code == 401:
            return {"status_code": response.status_code, "message": _teya_http_error_message(response)}
        if response.status_code == 400:
            return {"status_code": response.status_code, "message": _teya_http_error_message(response)}
        if response.status_code not in (200, 201):
            return {
                "status_code": response.status_code,
                "message": _teya_http_error_message(response),
            }
        try:
            return response.json()
        except (ValueError, requests.exceptions.JSONDecodeError):
            return {
                "status_code": response.status_code,
                "message": _("Invalid response from Teya. Check server logs."),
            }

    def teya_payment_request_status(self, payment_req_id, pos_session_id):
        if not payment_req_id or str(payment_req_id).lower() in ("none", "false", "0"):
            return {"status_code": 400, "message": _("Missing payment request id; start a new payment after fixing the Teya error.")}

        if self.teya_payment_mode == "test":
            url = f"https://api.teya.xyz/poslink/v1/payment-requests/{payment_req_id}"
        else:
            url = f"https://api.teya.com/poslink/v1/payment-requests/{payment_req_id}"

        pos_session = self.env["pos.session"].browse(pos_session_id)
        headers = {
            "Accept": "application/json",
            "Authorization": self._teya_bearer_authorization(),
        }

        _logger.info("Teya payment request status: GET %s", url)
        response = requests.get(url, headers=headers)

        _logger.info("teya_payment_request_status response: %s, %s", response.status_code, response.text)

        if response.status_code == 401:
            _logger.info("Teya token expired. Attempting token refresh in teya_payment_request_status.")
            self._cron_regenerate_refresh_token()
            headers["Authorization"] = self._teya_bearer_authorization()
            response = requests.get(url, headers=headers)

        if response.status_code == 401:
            _logger.info("teya_payment_request_status still 401 after refresh")
            return {"status_code": response.status_code, "message": response.json().get("message")}

        if response.status_code != 200:
            return {"status_code": response.status_code, "message": _teya_http_error_message(response)}

        try:
            body = response.json()
        except (ValueError, requests.exceptions.JSONDecodeError):
            return {
                "status_code": response.status_code,
                "message": _("Invalid response from Teya. Check server logs."),
            }

        payload = {
            "config_id": pos_session.config_id.id,
            "payment_request_id": payment_req_id,
            "response": body,
        }
        status = (body.get("status") or "").upper()
        _logger.info("teya_payment_request_status body: %s", body)
        if status in ("SUCCESSFUL", "CANCELLED", "FAILED"):
            pos_session.config_id._notify("TEYA_LATEST_RESPONSE", payload)
            return body

        return {"status": "pending", "payment_request_id": payment_req_id}