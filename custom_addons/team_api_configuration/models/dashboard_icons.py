# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

import logging
_logger = logging.getLogger(__name__)


class DashboardIcons(models.Model):
    _name = 'dashboard.icons'
    _description = "Dashboard Icons"

    name = fields.Char('Name', required=True)
    image_medium = fields.Binary('Image', attachment=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer()
    category = fields.Selection([
        ('leaves', 'Leaves'),
        ('timesheet', 'Timesheet'),
        ('projects', 'Projects'),
        ('attendance', 'Attendance'),
        ('crm', 'CRM'),
        ('asset_management', 'Asset Management'),
        ('inventory', 'Inventory'),
        ('approvals', 'Approvals'),
        ('reports', 'Reports'),
        ('view_products','View Products'),
        ('update_stock','Update Stock'),
        ('order_status', 'Order Status')], required=True)

    @api.constrains('name')
    def check_name(self):
        for record in self:
            if record.name:
                if self.search([('name', '=', record.name), ('id', '!=', record.id)]):
                    raise ValidationError("Entered category is already existing. Please choose different category.")
        return True

    def get_latest_app_version(self, category):
        version = ''
        app_version = False
        if category == 'android':
            app_version = self.env['app.version'].sudo().search([('version_type', '=', 'android_version')], limit=1,
                                                                order='date desc')
        elif category == 'ios':
            app_version = self.env['app.version'].sudo().search([('version_type', '=', 'ios_version')], limit=1,
                                                                order='date desc')
        if app_version:
            version = app_version.version
        return version


class DashboardAccess(models.Model):
    _name = 'dashboard.access'
    _description = "Dashboard Access"

    name = fields.Char(readonly=True, copy=False, required=True, default=lambda self: _('/'))
    user_id = fields.Many2one('res.users', string='User')
    dashboard_access_line_ids = fields.One2many('dashboard.access.line', 'line_id')
    active = fields.Boolean(default=True)

    def edit_icons(self, args):
        if args.get('uid', False):
            user = self.search([('user_id', '=', args['uid'])])
            if user:
                pass
            else:
                self.create({'user_id': args['user_id']})
        return True

    def get_dashboard_icons(self, uid):
        user_line = self.search([('user_id', '=', uid)])
        image_list = []
        if user_line:
            icons = self.env['dashboard.access.line'].search([('line_id', '=', user_line.id)], order='sequence asc')
            for icon in icons:
                image_list.append({
                    'id': icon.id,
                    'name': icon.category,
                    'image_binary': icon.image_medium,
                })
        return image_list

    # @api.model
    # def create(self, vals):
    #     if vals.get('name', _('/')) == _('/'):
    #         user = False
    #         if vals.get('user_id', False):
    #             user = self.env['res.users'].search([('id', '=', vals['user_id'])])
    #         vals['name'] = user.name if user else '' + self.env['ir.sequence'].next_by_code('dashboard.access') or _(
    #             '/')
    #     return super(DashboardAccess, self).create(vals)

    @api.model_create_multi
    def create(self, vals_list):
        res_users_obj = self.env['res.users']
        ir_sequence_obj = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', _('/')) == _('/'):
                user = False
                if vals.get('user_id', False):
                    user = res_users_obj.search([('id', '=', vals['user_id'])], limit=1)
                vals['name'] = (user.name if user else '') + (ir_sequence_obj.next_by_code('dashboard.access') or _('/'))
        return super(DashboardAccess, self).create(vals_list)

    @api.constrains('user_id')
    def check_user(self):
        for record in self:
            if record.user_id:
                if self.search([('user_id', '=', record.user_id.id), ('id', '!=', record.id)]):
                    raise ValidationError("Entered user is already existing. Please choose different user.")
        return True


class DashboardAccessLine(models.Model):
    _name = 'dashboard.access.line'
    _description = "Dashboard Access Line for Users"

    line_id = fields.Many2one('dashboard.access')
    sequence = fields.Integer()
    image_medium = fields.Binary('Image')
    category = fields.Selection([('leaves', 'Leaves'),
                                 ('timesheet', 'Timesheet'),
                                 ('projects', 'Projects'),
                                 ('attendance', 'Attendance'),
                                 ('crm', 'CRM'),
                                 ('inventory', 'Inventory'),
                                 ('approvals', 'Approvals'),
                                 ('reports', 'Reports'),
                                 ('order_status', 'Order Status')], required=True)

