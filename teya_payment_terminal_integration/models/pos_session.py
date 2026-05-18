# -*- coding: utf-8 -*-
# Copyright (C) 2021-Today: Part of NextFlowIT.
# @author:  Part of NextFlowIT.

from odoo import models

class PosSessios(models.Model):
    _inherit = 'pos.session'

    # Token refresh is handled per payment method on 401 or by scheduled cron only.
    # Do not refresh all Teya methods on every session open/close.
