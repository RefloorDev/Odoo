# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class APISyncLock(models.Model):
    _name = 'otl.api.lock'
    _description = 'API processing lock (claim row)'

    appointment_id = fields.Many2one('team.customer.appointment', 'Appointment', required=True, ondelete='cascade')
    name = fields.Char('API', required=True)
    api_create_date = fields.Char('API Create Date', required=True)
    create_date = fields.Datetime('Create Date', default=fields.Datetime.now)

    _sql_constraints = [
        ('otl_api_lock_uniq', 'unique(appointment_id, name)', 'Lock already exists for this appointment + API + create_date')
    ]

    @api.model
    def cron_cleanup_stale_locks(self, ttl_minutes=15):
        """Cron job to remove stale otl.api.lock rows older than ttl_minutes.

        The scheduled action can call this method (without args) to delete locks
        older than 15 minutes by default.
        """
        try:
            threshold = datetime.utcnow() - timedelta(minutes=int(ttl_minutes))
            threshold_str = fields.Datetime.to_string(threshold)
            stale = self.sudo().search([('create_date', '<', threshold_str)])
            if stale:
                _logger.info('Cleaning up %s stale otl.api.lock records older than %s minutes', len(stale), ttl_minutes)
                stale.unlink()
            return True
        except Exception as e:
            _logger.exception('Error cleaning up stale otl.api.lock records: %s', e)
            return False

