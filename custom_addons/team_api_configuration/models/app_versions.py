# -*- coding: utf-8 -*-
from odoo import models, fields, api


class AppVersion(models.Model):
	_name = 'app.version'
	_description = "App Versions"

	name = fields.Char('Name')
	version_type = fields.Selection([('android_version','Android Version'),('ios_version','IoS Version')], string="Type")
	date = fields.Date('Date')
	version = fields.Char('App Version')
	active = fields.Boolean('Active', default=True)
