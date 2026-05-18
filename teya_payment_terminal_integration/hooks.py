# -*- coding: utf-8 -*-

def post_init_hook(env):
    """Assign company on legacy Teya stores synced before company_id existed."""
    stores = env['teya.store'].sudo().search([
        ('company_id', '=', False),
        ('paymen_method_id', '!=', False),
    ])
    for store in stores:
        company = store.paymen_method_id.company_id
        if company:
            store.company_id = company
