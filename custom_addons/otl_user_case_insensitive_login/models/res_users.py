# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def _get_login_domain(self, login):
        domain = [('login', '=ilike', login)]
        # website = self.env['website'].get_current_website()
        # if website:
        #     domain + website.website_domain()
        return domain

    def reset_password(self, login):
        """ retrieve the user corresponding to login (login or email),
            and reset their password
        """
        users = self.search([('login', '=ilike', login)])
        if not users:
            users = self.search([('email', '=ilike', login)])
        if len(users) != 1:
            raise Exception(_('Reset password: invalid username or email'))
        return users.action_reset_password()
