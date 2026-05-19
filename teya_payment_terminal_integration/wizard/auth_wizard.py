import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..models.teya_credential_provider import get_partner_ref_alpha, get_partner_ref_beta


class TeyaDiviceVerifyWizard(models.TransientModel):
    _name = "teya.verify.wizard"
    _description = "Teya Verify Wizard"

    qr_code = fields.Binary(string="QR Code", readonly=True)
    verification_uri = fields.Char(string="Verification Uri")
    device_code = fields.Char(string="Device Code")
    payment_method_id = fields.Many2one("pos.payment.method", string="Payment Method")

    def nf_varify_devide(self):
        url = self.payment_method_id.get_teya_payment_url()
        auth_device_url = url + "/oauth-token"
        device_code = self.device_code
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        auth_payload = (
            "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code"
            f"&device_code={device_code}"
            f"&client_id={get_partner_ref_alpha()}"
            f"&client_secret={get_partner_ref_beta()}"
        )

        try:
            response = requests.request("POST", auth_device_url, headers=headers, data=auth_payload, timeout=30)
        except requests.RequestException as error:
            raise UserError(_("Could not connect to Teya: %s", error)) from error

        if response.status_code != 200:
            from ..models.pos_payment_methos import _teya_http_error_message
            raise UserError(
                _("Teya device verification failed (HTTP %s): %s", response.status_code, _teya_http_error_message(response))
            )

        self.payment_method_id.write(
            {
                "teya_auth_token": response.json().get("access_token"),
                "teya_refresh_token": response.json().get("refresh_token"),
            }
        )

        return {"type": "ir.actions.act_window_close"}
