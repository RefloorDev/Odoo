# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
import os
import json

import logging
_logger = logging.getLogger(__name__)


class ServerMonitorLog(models.Model):
    _name = 'otl.server.monitoring.log'
    _description = "Server Monitoring Logs"
    _order = "id desc"

    @api.depends('memory_usage_line', 'memory_usage_line.percentage')
    def _compute_memory_usage(self):
        for record in self:
            memory_usage = 0
            for line in record.memory_usage_line:
                memory_usage = line.percentage
            record.memory_usage = memory_usage

    @api.depends('disk_usage_line', 'disk_usage_line.percentage')
    def _compute_disk_usage(self):
        for record in self:
            disk_usage = 0
            for line in record.disk_usage_line:
                disk_usage = line.percentage
            record.disk_usage = disk_usage

    name = fields.Char('Reference', default='/', copy=False)
    date = fields.Datetime('Date', default=fields.Datetime.now, required=True)
    instance_status = fields.Selection([('running', 'Running'), ('not_running', 'Not Running')], string='Instance Status', default='running', required=True)
    db_connection = fields.Integer('Active DB Connection')
    cpu_usage_percent = fields.Float('CPU Usage')
    memory_usage_line = fields.One2many('otl.server.memory.usage.line', 'monitor_log_id', string='Memory Usage Line')
    disk_usage_line = fields.One2many('otl.server.disk.usage.line', 'monitor_log_id', string='Disk Usage Line')
    memory_usage = fields.Float('Memory Usage', compute='_compute_memory_usage', store=True)
    disk_usage = fields.Float('Disk Usage', compute='_compute_disk_usage', store=True)
    
    @api.model_create_multi
    def create(self, vals_list):
        ir_sequence_obj = self.env['ir.sequence']
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                seq_date = None
                if 'date' in vals:
                    seq_date = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(vals['date']))
                vals['name'] = ir_sequence_obj.next_by_code('server.monitor.log', sequence_date=seq_date) or _('/')
        return super(ServerMonitorLog, self).create(vals_list)

    def read_json_lines(self, file_path):
        result= []
        try:
            with open(file_path, 'r') as file:
                for line in file:
                    try:
                        data = json.loads(line.strip())
                        result.append(data)
                    except json.JSONDecodeError as e:
                        logging.info(f"Error decoding JSON on line: {line.strip()}")
                        logging.info(f"Error: {e}")
        except:
            logging.info(f"Error while accessing File: {file_path}")
        return result

    @api.model
    def cron_get_server_monitoring_logs(self):
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        file_path = os.path.join(base_path, 'scripts/system_metrics.json')
        _logger.info('Start Processing File %s'%file_path)
        if os.path.isfile(file_path):
            data_list = self.read_json_lines(file_path)
            for data in data_list:
                vals = {
                    'date': data.get('timestamp'),
                    'cpu_usage_percent': data.get('cpu_usage_percent'),
                    'db_connection': data.get('db_connection_count'),
                    'instance_status': data.get('odoo_status'),
                    'memory_usage_line': [(0, 0, data.get('memory_usage'))],
                    'disk_usage_line': [(0, 0, data.get('disk_usage'))],
                }
                self.create(vals)
            _logger.info('Completed Processing File %s' % file_path)
            with open(file_path, 'w') as file:
                pass  # This will truncate the file

            _logger.info(f"All content deleted from file: {file_path}")
        else:
            logging.info(f"File Not Found: {file_path}")



class ServerMemoryUsageLine(models.Model):
    _name = 'otl.server.memory.usage.line'
    _description = 'Server Memory Usage Log'

    total = fields.Float('Total')
    used = fields.Float('Used')
    available = fields.Float('Available')
    free = fields.Float('Free')
    percentage = fields.Float('Percentage')
    monitor_log_id = fields.Many2one('otl.server.monitoring.log', string='Monitor Log Ref', required=True,
                                     ondelete='cascade')


class ServerDiskUsageLine(models.Model):
    _name = 'otl.server.disk.usage.line'
    _description = 'Server Memory Usage Log'

    total = fields.Float('Total')
    used = fields.Float('Used')
    free = fields.Float('Free')
    percentage = fields.Float('Percentage')
    monitor_log_id = fields.Many2one('otl.server.monitoring.log', string='Monitor Log Ref', required=True,
                                     ondelete='cascade')




