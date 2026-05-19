from odoo import fields, models


class TeyaStores(models.Model):
    _name = "teya.store"
    _description = "Teya Teminal Stores"

    name = fields.Char(string="Name")
    teya_store_id = fields.Char(string="Store id")
    city = fields.Char(string="City")
    country_id = fields.Many2one("res.country", string="Country")
    street_1 = fields.Char(string="Street 1")
    street_2 = fields.Char(string="Street 2")
    zipcode = fields.Char(string="Zipcode")
    paymen_method_id = fields.Many2one("pos.payment.method", string="Payment method")
