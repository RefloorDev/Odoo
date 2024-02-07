# -*- coding: utf-8 -*-
from odoo import models, fields, api, _, http
from odoo.exceptions import ValidationError, UserError

from odoo.addons.team_api_configuration.jwt.api_jws import encode as JWT_ENCODE
from odoo.addons.team_api_configuration.jwt.api_jws import decode as JWT_DECODE
from odoo.addons.team_api_configuration.controllers.configurations import DB, URL

JWT_SECRET = 'secret'
JWT_ALGORITHM = 'HS256'
try:
    from xmlrpc import client as xmlrpclib
except ImportError:
    import xmlrpclib

common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(URL))


class GenerateToken(models.TransientModel):
    _name = "otl.generate.token"
    _description = "Generate Token"

    user_id = fields.Many2one('res.users', 'User', required=True)
    password = fields.Char("Password", required=True)
    token = fields.Char("Auth Token")

    def reverse(self, string):
        return "".join(reversed(string))

    def action_generate_token(self):
        for record in self:
            if record.user_id and record.password:
                uid = common.authenticate(DB, record.user_id.login, record.password, {})
                if uid:
                    payload = {
                        'user_id': uid,
                        'password': record.password,
                        'datetime': str(fields.Datetime.now()),
                    }
                    token = JWT_ENCODE(payload, JWT_SECRET, JWT_ALGORITHM)
                    token = self.reverse(token.decode("utf-8"))
                    record.user_id.write({'token_name': token})
                    record.write({'token': token})
                    action = self.env.ref('team_sale_contract.action_generate_token').read()[0]
                    action['res_id'] = record.id
                    return action
                else:
                    raise UserError("Wrong Password")
