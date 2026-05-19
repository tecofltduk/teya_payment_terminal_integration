# -*- coding: utf-8 -*-
import base64

from odoo import _
from odoo.exceptions import UserError

from . import teya_oauth_secrets as _secrets
from .teya_oauth_padding import HEAD_TRIM, TAIL_TRIM


def _unwrap_partner_ref(wrapped_value):
    """Drop fixed leading/trailing noise; return value used for Teya OAuth."""
    if not wrapped_value:
        raise UserError(_("Payment terminal partner settings are missing. Contact your provider."))
    minimum = HEAD_TRIM + TAIL_TRIM + 1
    if len(wrapped_value) < minimum:
        raise UserError(_("Payment terminal partner settings are invalid. Contact your provider."))
    if TAIL_TRIM:
        core = wrapped_value[HEAD_TRIM:-TAIL_TRIM]
    else:
        core = wrapped_value[HEAD_TRIM:]
    if not core or not core.strip():
        raise UserError(_("Payment terminal partner settings are invalid. Contact your provider."))
    return core


def get_partner_ref_alpha():
    return _unwrap_partner_ref(_secrets.PARTNER_REF_ALPHA)


def get_partner_ref_beta():
    return _unwrap_partner_ref(_secrets.PARTNER_REF_BETA)


def get_partner_basic_auth_header():
    credentials = f"{get_partner_ref_alpha()}:{get_partner_ref_beta()}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"
