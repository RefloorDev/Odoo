
from dateutil.relativedelta import relativedelta
from datetime import date, datetime, time
import io
import pytz
import base64

from odoo import api, fields, models, _
from odoo.tools.misc import xlsxwriter
from odoo.exceptions import ValidationError, UserError


class DayWiseSyncReport(models.TransientModel):
    _name = "otl.day.wise.sync.status.report"
    _description = "Sync Status Report"

    date = fields.Date('Date', required=True, default=fields.Date.context_today)
    report_data = fields.Binary('File Name')
    name = fields.Char('Name', size=252)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    def action_generate_day_wise_report(self):
        self.action_generate_report()
        form_id = self.env.ref('team_sale_contract.day_wise_report_form').id
        return {
            'type': 'ir.actions.act_window',
            'name': "Day Wise Sync Status Report",
            'res_model': 'otl.day.wise.sync.status.report',
            'res_id': self.ids[0],
            'view_type': 'form',
            'view_mode': 'tree,form',
            'view_id': False,
            'views': [(form_id, 'form')],
            'target': 'new'
        }

    def convert_date_utc_2_local(self, str_date, tz):
        if str_date:
            timez = 'UTC'
            if tz:
                timez = tz
            local_tz = pytz.timezone(timez)
            date_with_tz = pytz.utc.localize(str_date).astimezone(local_tz).strftime('%d %b %Y %I:%M %p')
        return date_with_tz

    def get_sync_completed_time(self, appointment):
        completed_time = ''
        sync_status = 'Pending'
        sync_error = ''
        network_strength = ''
        sync_log = appointment.api_sync_log_line.filtered(lambda x: x.name == '/api/initiate_sync_to_i360_json')
        if sync_log:
            if sync_log.filtered(lambda x: x.state == 'success'):
                completed_time = sync_log[0].created_date
                sync_status = 'Completed'
                network_strength = sync_log[0].network_strength or ''
            else:
                if sync_log:
                    sync_error = sync_log[0].response
                    network_strength = sync_log[0].network_strength or ''
        else:
            if appointment.appointment_result == 'Sold':
                sync_log = appointment.api_sync_log_line.filtered(
                    lambda x: x.name == '/api/generate_contract_document')
                if sync_log.filtered(lambda x: x.state == 'success'):
                    sync_error = 'Initiate Sync API not triggered'
                    network_strength = sync_log[0].network_strength or ''
                else:
                    if sync_log:
                        sync_error = sync_log[0].response
                        network_strength = sync_log[0].network_strength or ''
                    else:
                        sync_log = appointment.api_sync_log_line.filtered(
                            lambda x: x.name == '/api/upload_images')
                        if sync_log.filtered(lambda x: x.state == 'success'):
                            sync_error = 'Generate Contract API not triggered'
                            network_strength = sync_log[0].network_strength or ''
                        else:
                            if sync_log:
                                sync_error = sync_log[0].response
                                network_strength = sync_log[0].network_strength or ''
                            else:
                                sync_log = appointment.api_sync_log_line.filtered(
                                    lambda x: x.name == '/api/create_order_and_update_measurements_encoded')
                                if sync_log.filtered(lambda x: x.state == 'success'):
                                    sync_error = 'Upload Image API not triggered'
                                    network_strength = sync_log[0].network_strength or ''
                                else:
                                    if sync_log:
                                        sync_error = sync_log[0].response
                                        network_strength = sync_log[0].network_strength or ''
                                    else:
                                        sync_error = 'Create Order & Update Room API not triggered'
            else:
                sync_log = appointment.api_sync_log_line.filtered(
                    lambda x: x.name == '/api/upload_images')
                if sync_log.filtered(lambda x: x.state == 'success'):
                    sync_error = 'Generate Contract API not triggered'
                    network_strength = sync_log[0].network_strength or ''
                else:
                    if sync_log:
                        sync_error = sync_log[0].response
                        network_strength = sync_log[0].network_strength or ''
                    else:
                        sync_log = appointment.api_sync_log_line.filtered(
                            lambda x: x.name == '/api/create_order_and_update_measurements_encoded')
                        if sync_log.filtered(lambda x: x.state == 'success'):
                            sync_error = 'Upload Image API not triggered'
                        else:
                            if sync_log:
                                sync_error = sync_log[0].response
                            else:
                                sync_error = 'Create Order & Update Room API not triggered'
        return {
            "sync_completed_time": completed_time,
            "sync_status": sync_status,
            "sync_error": sync_error,
            "network_strength": network_strength,
        }

    def get_user_device_details(self, appointment):
        user = appointment.user_id
        device_details = ''
        user_login_log = self.env['otl.user.authentication.log'].search([('date', '<=', appointment.appointment_date), ('user_id', '=', user.id)], limit=1)
        if user_login_log and user_login_log.device_name:
            device_details = '%s, %s'%(user_login_log.device_name, user_login_log.device_os)
        elif user.device_name:
            device_details = '%s, %s'%(user.device_name, user.device_os)
        return device_details

    def get_i360_sync_status(self, appointment):
            sync_status = 'Pending'
            sync_error = ''
            order = appointment.sale_order_ids and appointment.sale_order_ids[0] or False
            if order:
                if order.is_data_upload_completed:
                    sync_status = 'Completed'
                else:
                    sync_logs = appointment.sync_log_line.filtered(lambda x: x.state == 'failed')
                    api_name_list = []
                    for line in sync_logs:
                        if line.name not in api_name_list:
                            api_name_list.append(line.name)
                            sync_error += '%s - %s\n'%(line.name, line.response)
                    if not sync_error:
                        sync_error = "No i360 Failed Sync Logs"
            else:
                sync_error = "Order is not Created in Odoo"
            return {
                "sync_status": sync_status,
                "sync_error": sync_error
            }

    def create_appointment_sheet(self, workbook, date_from, date_to, tz, header_fmt, bold_font, normal_font_left):
        worksheet = workbook.add_worksheet('Appointments')
        normal_font_left_bg_gr = workbook.add_format(
            {'bold': False, 'border': True, 'align': 'left', 'text_wrap': True, 'bg_color': '#00ff19'})
        normal_font_left_bg_rd = workbook.add_format(
            {'bold': False, 'border': True, 'align': 'left', 'text_wrap': True, 'bg_color': '#fc3737'})
        bold_font_left = workbook.add_format({'bold': True, 'border': True, 'align': 'left', 'text_wrap': True, 'bg_color': '#DDFBE6'})
        bold_font_right = workbook.add_format({'bold': True, 'border': True, 'align': 'right', 'text_wrap': True, 'bg_color': '#DDFBE6'})
        currency_format = workbook.add_format({'bold': False, 'border': True, 'align': 'right', 'text_wrap': True, 'num_format': '$#,##0.00'})

        row = 0
        col = 0
        sheet_1_heading = 'Sync Status of Appointments Done on %s' % self.date.strftime('%m/%d/%Y')
        worksheet.merge_range(row, 0, row, 16, sheet_1_heading, header_fmt)
        worksheet.set_row(row, 30)
        row += 1

        col = 0
        worksheet.set_column(0, 0, 15)
        worksheet.set_column(0, 1, 25)
        worksheet.set_column(0, 2, 20)
        worksheet.set_column(0, 3, 15)
        worksheet.set_column(0, 4, 20)
        worksheet.set_column(0, 5, 15)
        worksheet.set_column(0, 6, 20)
        worksheet.set_column(0, 7, 20)
        worksheet.set_column(0, 8, 20)
        worksheet.set_column(0, 9, 20)
        worksheet.set_column(0, 10, 20)
        worksheet.set_column(0, 11, 15)
        worksheet.set_column(0, 12, 25)
        worksheet.set_column(0, 13, 15)
        worksheet.set_column(0, 14, 20)
        worksheet.set_column(0, 15, 25)
        worksheet.set_column(0, 16, 20)
        worksheet.set_column(0, 17, 25)
        worksheet.set_column(0, 18, 20)
        worksheet.set_column(0, 19, 20)

        worksheet.write(row, col, 'Appointment', bold_font)
        col += 1
        worksheet.write(row, col, 'i360 ID', bold_font)
        col += 1
        worksheet.write(row, col, 'Customer', bold_font)
        col += 1
        worksheet.write(row, col, 'Salesperson', bold_font)
        col += 1
        worksheet.write(row, col, 'Appointment Date', bold_font)
        col += 1
        worksheet.write(row, col, 'Result Status', bold_font)
        col += 1
        worksheet.write(row, col, 'Market Segment', bold_font)
        col += 1
        worksheet.write(row, col, 'Down Payment Method', bold_font)
        col += 1
        worksheet.write(row, col, 'Down Payment Amount', bold_font)
        col += 1
        worksheet.write(row, col, 'Completed Time', bold_font)
        col += 1
        worksheet.write(row, col, 'Sync Started Time', bold_font)
        col += 1
        worksheet.write(row, col, 'Sync Completed Time', bold_font)
        col += 1
        worksheet.write(row, col, 'App Version', bold_font)
        col += 1
        worksheet.write(row, col, 'Device Details', bold_font)
        col += 1
        worksheet.write(row, col, 'Network Strength', bold_font)
        col += 1
        worksheet.write(row, col, 'Odoo Sync Status', bold_font)
        col += 1
        worksheet.write(row, col, 'Failure Reason', bold_font)
        col += 1
        worksheet.write(row, col, 'i360 Sync Status', bold_font)
        col += 1
        worksheet.write(row, col, 'Failure Reason', bold_font)
        col += 1
        worksheet.write(row, col, 'Final Status', bold_font)

        col = 0
        row += 1

        appointments = self.env['team.customer.appointment'].search(
            [('appointment_date', '>=', date_from),
             ('appointment_date', '<=', date_to)])

        total_appointments = len(appointments)
        total_completed_appointments = 0
        total_pending_appointments = 0
        total_pending_odoo_appointments = 0
        total_pending_i360_appointments = 0
        for appointment in appointments:
            sale_order = appointment.sale_order_ids and appointment.sale_order_ids[0] or False
            worksheet.write(row, col, appointment.name, normal_font_left)
            col += 1
            worksheet.write(row, col, appointment.improveit_appointment_id or '', normal_font_left)
            col += 1
            worksheet.write(row, col, appointment.customer_name, normal_font_left)
            col += 1
            worksheet.write(row, col, appointment.user_id.name, normal_font_left)
            col += 1
            worksheet.write(row, col, self.convert_date_utc_2_local(appointment.appointment_date, tz),
                            normal_font_left)
            col += 1
            worksheet.write(row, col, appointment.appointment_result or '', normal_font_left)
            col += 1
            worksheet.write(row, col, appointment.market_segment or '', normal_font_left)
            col += 1
            down_payment_amount = 0
            down_payment_method = ''
            if appointment.appointment_result == 'Sold' and sale_order:
                down_payment_amount = sale_order.down_payment_amount
                if sale_order.payment_method and down_payment_amount:
                    down_payment_method = dict(sale_order._fields['payment_method'].selection).get(sale_order.payment_method)
            worksheet.write(row, col, down_payment_method, normal_font_left)
            col += 1
            worksheet.write(row, col, down_payment_amount, currency_format)
            col += 1
            completed_date = ''
            if appointment.completed_date:
                completed_date = self.convert_date_utc_2_local(appointment.completed_date, tz)
            worksheet.write(row, col, completed_date, normal_font_left)
            col += 1
            sync_initiated_date = ''
            if appointment.sync_initiated_date:
                sync_initiated_date = self.convert_date_utc_2_local(appointment.sync_initiated_date, tz)
            worksheet.write(row, col, sync_initiated_date, normal_font_left)
            col += 1
            result = self.get_sync_completed_time(appointment)
            sync_completed_time = result.get('sync_completed_time', '')
            if sync_completed_time:
                sync_completed_time = self.convert_date_utc_2_local(appointment.sync_initiated_date, tz)
            worksheet.write(row, col, sync_completed_time, normal_font_left)
            col += 1
            worksheet.write(row, col, appointment.app_version_id and appointment.app_version_id.name or '',
                            normal_font_left)
            col += 1
            device_details = self.get_user_device_details(appointment)
            worksheet.write(row, col, device_details, normal_font_left)
            col += 1
            worksheet.write(row, col, result.get('network_strength', ''), normal_font_left)
            col += 1
            if result.get('sync_status', '') == 'Completed':
                worksheet.write(row, col, result.get('sync_status', ''), normal_font_left_bg_gr)
            else:
                worksheet.write(row, col, result.get('sync_status', ''), normal_font_left_bg_rd)
                total_pending_odoo_appointments += 1
            col += 1
            worksheet.write(row, col, result.get('sync_error', ''), normal_font_left)
            col += 1
            i360_sync_result = self.get_i360_sync_status(appointment)
            if i360_sync_result.get('sync_status', '') == 'Completed':
                worksheet.write(row, col, i360_sync_result.get('sync_status', ''), normal_font_left_bg_gr)
            else:
                worksheet.write(row, col, i360_sync_result.get('sync_status', ''), normal_font_left_bg_rd)
                total_pending_i360_appointments += 1
            col += 1
            worksheet.write(row, col, i360_sync_result.get('sync_error', ''), normal_font_left)
            col += 1
            final_status = 'Pending'
            if result.get('sync_status', '') == 'Completed' and i360_sync_result.get('sync_status',
                                                                                     '') == 'Completed':
                final_status = 'Completed'
            if final_status == 'Completed':
                worksheet.write(row, col, final_status, normal_font_left_bg_gr)
                total_completed_appointments +=1
            else:
                worksheet.write(row, col, final_status, normal_font_left_bg_rd)
                total_pending_appointments += 1

            row += 1
            col = 0

        row += 2
        worksheet.merge_range(row, col, row, col + 2, 'Total No. of Appointments', bold_font_left)
        worksheet.write(row, col + 3, total_appointments, bold_font_right)
        row += 1

        worksheet.merge_range(row, col, row, col + 2, 'Total No. of Completed Appointments', bold_font_left)
        worksheet.write(row, col + 3, total_completed_appointments, bold_font_right)
        row += 1

        worksheet.merge_range(row, col, row, col + 2, 'Total No. of Pending Appointments', bold_font_left)
        worksheet.write(row, col + 3, total_pending_appointments, bold_font_right)
        row += 1

        worksheet.merge_range(row, col, row, col + 2, 'Total No. of Pending Appointments to Sync to Odoo', bold_font_left)
        worksheet.write(row, col + 3, total_pending_odoo_appointments, bold_font_right)
        row += 1

        worksheet.merge_range(row, col, row, col + 2, 'Total No. of Pending Appointments to Sync to i360', bold_font_left)
        worksheet.write(row, col + 3, total_pending_i360_appointments, bold_font_right)
        row += 1

        return True

    def create_server_statistics_sheet(self, workbook, date_from, date_to, tz, header_fmt, bold_font, normal_font_left, normal_font_right, normal_font_right_2d):
        worksheet = workbook.add_worksheet('Server Log')
        normal_font_right_2d_bg_gr = workbook.add_format(
            {'bold': False, 'border': True, 'align': 'right', 'text_wrap': True, 'num_format': '0.00', 'bg_color': '#00ff19'})
        normal_font_right_2d_bg_red = workbook.add_format(
            {'bold': False, 'border': True, 'align': 'right', 'text_wrap': True, 'num_format': '0.00', 'bg_color': '#fc3737'})
        normal_font_left_bg_red = workbook.add_format(
            {'bold': False, 'border': True, 'align': 'left', 'text_wrap': True, 'bg_color': '#fc3737'})


        row = 0
        col = 0
        sheet_1_heading = 'Server Statistics Log on %s' % self.date.strftime('%m/%d/%Y')
        worksheet.merge_range(row, 0, row, 5, sheet_1_heading, header_fmt)
        worksheet.set_row(row, 30)
        row += 1

        col = 0
        worksheet.set_column(0, 0, 20)
        worksheet.set_column(0, 1, 15)
        worksheet.set_column(0, 2, 15)
        worksheet.set_column(0, 3, 15)
        worksheet.set_column(0, 4, 15)
        worksheet.set_column(0, 5, 15)

        worksheet.write(row, col, 'Time', bold_font)
        col += 1
        worksheet.write(row, col, 'Odoo Status', bold_font)
        col += 1
        worksheet.write(row, col, 'No. of Active DB Connection', bold_font)
        col += 1
        worksheet.write(row, col, 'Memory Usage(%)', bold_font)
        col += 1
        worksheet.write(row, col, 'CPU Usage(%)', bold_font)
        col += 1
        worksheet.write(row, col, 'Storage Used(%)', bold_font)

        col = 0
        row += 1

        self.env['otl.server.monitoring.log'].sudo().cron_get_server_monitoring_logs()
        server_logs = self.env['otl.server.monitoring.log'].search([('date', '>=', date_from), ('date', '<=', date_to)])

        for log in server_logs:
            worksheet.write(row, col, self.convert_date_utc_2_local(log.date, tz),
                            normal_font_left)
            col += 1
            odoo_status = 'Running'
            if log.instance_status == 'not_running':
                odoo_status = 'Not Running'
                worksheet.write(row, col, odoo_status, normal_font_left_bg_red)
            else:
                worksheet.write(row, col, odoo_status, normal_font_left)
            col += 1
            worksheet.write(row, col, log.db_connection, normal_font_right)
            col += 1
            worksheet.write(row, col, log.memory_usage, normal_font_right_2d)
            col += 1
            worksheet.write(row, col, log.cpu_usage_percent, normal_font_right_2d)
            col += 1
            worksheet.write(row, col, log.disk_usage, normal_font_right_2d)

            row += 1
            col = 0
        if row > 2:
            worksheet.conditional_format(2, 2, row-1, 2, {'type': 'cell',
                                                   'criteria': '<',
                                                   'value': 100,
                                                   'format': normal_font_right_2d_bg_gr})

            worksheet.conditional_format(2, 2, row-1, 2, {'type': 'cell',
                                                   'criteria': '>=',
                                                   'value': 100,
                                                   'format': normal_font_right_2d_bg_red})
            worksheet.conditional_format(2, 3, row-1, 5, {'type': 'cell',
                                                   'criteria': '<',
                                                   'value': 80,
                                                   'format': normal_font_right_2d_bg_gr})

            worksheet.conditional_format(2, 3, row-1, 5, {'type': 'cell',
                                                   'criteria': '>=',
                                                   'value': 80,
                                                   'format': normal_font_right_2d_bg_red})
        return True



    def action_generate_report(self):
        for record in self:
            file_data = io.BytesIO()
            workbook = xlsxwriter.Workbook(file_data)
            header_fmt = workbook.add_format(
                {'bold': True, 'border': True, 'font_size': 14, 'align': 'center', 'text_wrap': True})
            bold_font = workbook.add_format({'bold': True, 'border': True, 'align': 'center', 'text_wrap': True})
            normal_font_left = workbook.add_format(
                {'bold': False, 'border': True, 'align': 'left', 'text_wrap': True})
            normal_font_right = workbook.add_format(
                {'bold': False, 'border': True, 'align': 'right', 'text_wrap': True})
            normal_font_right_2d = workbook.add_format(
                {'bold': False, 'border': True, 'align': 'right', 'text_wrap': True, 'num_format': '0.00'})

            tz = self.env.user.tz or 'US/Eastern'
            user_tz = pytz.timezone(tz)
            if record.date:
                date_from = datetime.combine(record.date, time.min)
                date_to = datetime.combine(record.date, time.max)
                server_frmt_from = fields.Datetime.from_string(date_from)
                user_utc_from_datetime = user_tz.localize(server_frmt_from).astimezone(pytz.UTC)
                server_frmt_to = fields.Datetime.from_string(date_to)
                user_utc_to_datetime = user_tz.localize(server_frmt_to).astimezone(pytz.UTC)

                record.create_appointment_sheet(workbook, user_utc_from_datetime, user_utc_to_datetime, tz, header_fmt, bold_font, normal_font_left)
                record.create_server_statistics_sheet(workbook, user_utc_from_datetime, user_utc_to_datetime, tz, header_fmt, bold_font, normal_font_left, normal_font_right, normal_font_right_2d)

            workbook.close()
            file_data.seek(0)
            data = file_data.read()
            file_data.close()
            out = base64.encodebytes(data)
            self.write({'report_data': out, 'name': 'DailyReport_%s.xlsx'%(record.date.strftime('%d%b%Y'))})
            return True

    def get_daily_status_excel_file(self):
        attachment_ids = []
        for record in self:
            if record.report_data:
                attachment = self.env['ir.attachment'].create({
                    'name': record.name,
                    'datas': record.report_data,
                    'type': 'binary',
                })
                if attachment:
                    attachment_ids = [(4, attachment.id)]
        return attachment_ids

    @api.model
    def cron_send_daily_sync_status_report(self):
        daily_report = self.create({'date': fields.Date.context_today(self) + relativedelta(days=-1)})
        if daily_report:
            daily_report.action_generate_report()
            try:
                # Get the template id corresponding to the email template
                template_id = self.env.ref('team_sale_contract.email_template_daily_sync_report')
            except ValueError:
                template_id = False
            if template_id:
                template_id.attachment_ids = daily_report.get_daily_status_excel_file()
                template_id.send_mail(daily_report.id, force_send=True, raise_exception=False)
                template_id.attachment_ids = [(6,0, [])]
        return True


