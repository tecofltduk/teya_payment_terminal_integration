# -*- coding: utf-8 -*-
# Module developed for configuring Teya integration
# This module extends Odoo's payment framework
# Odoo is a trademark of Odoo S.A.

{
    "name": " Teya Payment Terminal Odoo Point of sale Integration ",
    "version": "18.0.0.1",
    'category': 'Sales/Point of Sale',
    "depends": ['point_of_sale'],
    "license": "LGPL-3",
    'website': 'https://tecof.odoo.com',
    'author': 'Tecof Ltd.',
    'maintainer': 'Tecof LTD',
    'summary': "Teya Payment Terminal Odoo Point of sale Integration",
    "description": " Teya Payment Terminal Odoo Point of sale Integration, This module adds options to receive payment throught Teya Terminal and sync the transaction details to POS session automatically. ",
    "data": [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/pos_config.xml',
        'views/pos_order.xml',
        'views/pos_payment_methos.xml',
        'views/res_pos_configuration.xml',
        'views/teya_pos_store.xml',
        'views/teya_store_terminals.xml',
        'wizard/auth_wizard.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'teya_payment_terminal_integration/static/src/**/*',
        ],
    },
    'images': [
        'static/description/banner.gif',
    ],
    'qweb': ['static/src/xml/pos.xml'],
    "auto_install": False,
    "installable": True,
    'application' : True,
}
