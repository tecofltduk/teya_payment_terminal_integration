from odoo import fields, models


class TerminalDevice(models.Model):
    _name = "teya.terminal.device"
    _description = "Teya Terminal Device"

    name = fields.Char(string="Serianl Number")
    store_id = fields.Many2one("teya.store", string="Store id")
    terminal_id = fields.Char(string="Terminal ID", required=True)
    terminal_name = fields.Char(string="Terminal Name")
