# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ChangeImproveitAppointmentWizard(models.TransientModel):
    _name = 'otl.change.improveit.appointment.wizard'
    _description = 'Change Improveit Appointment ID'

    appointment_id = fields.Many2one('team.customer.appointment', string='Appointment', required=True)
    new_improveit_id = fields.Char(string='New Improveit Appointment ID', required=True)
    initiate_resync = fields.Boolean(string='Initiate Resync', default=False)

    def action_apply(self):
        self.ensure_one()
        appointment = self.appointment_id
        if not appointment or not appointment.exists():
            raise UserError(_('Selected appointment does not exist.'))
        new_id = (self.new_improveit_id or '').strip()
        if not new_id:
            raise UserError(_('New Improveit Appointment ID is required.'))

        # If another appointment already has this improveit id, rename it
        existing = self.env['team.customer.appointment'].search([('improveit_appointment_id', '=', new_id)], limit=1)
        if existing and existing.id != appointment.id:
            # rename existing to avoid duplicate - use a suffix to keep trace
            old_val = existing.improveit_appointment_id or ''
            suffix = '_renamed_to%s' % (appointment.id)
            existing.write({'improveit_appointment_id': (existing.improveit_appointment_id or '') + suffix})
            try:
                existing.message_post(body=_('Improveit Appointment ID %s was renamed to %s by %s') % (old_val, (old_val + suffix), self.env.user.name))
            except Exception:
                pass

        # write new id to current appointment and post message
        old_current = appointment.improveit_appointment_id or ''
        appointment.write({'improveit_appointment_id': new_id})
        try:
            appointment.message_post(body=_('Improveit Appointment ID changed from %s to %s by %s') % (old_current, new_id, self.env.user.name))
            if self.initiate_resync:
                order = appointment.sale_order_ids and appointment.sale_order_ids[0] or False
                appointment.write({'start_sync_to_i360': False, 'prospect_info_updated': False, 'status_updated_to_i360': False})
                if order:
                    if order.quote_id or order.excluded_quote_id or order.contract_document_uploaded or order.other_files_uploaded or order.is_data_upload_completed:
                        order.write({'quote_id': '', 'excluded_quote_id': '', 'contract_document_uploaded': False,
                                     'other_files_uploaded': False, 'update_destination_selection_synced': False,
                                     'is_data_upload_completed': False, 'discount_history_sync_i360_ref': '',
                                     'additional_comment_synced': False})
                        room_measurements = order.room_measurement_line.filtered(
                            lambda x: not x.exclude_from_calculation and x.improveit_id)
                        if room_measurements:
                            room_measurements.write({'improveit_id': ''})
                    if appointment.related_attachment_ids:
                        synced_attachments = appointment.related_attachment_ids.filtered(lambda att: att.improveit_id)
                        if synced_attachments:
                            synced_attachments.write({'improveit_id': ''})
                    card_transaction_log_line = appointment.card_transaction_log_line.filtered(lambda x: x.synced)
                    if card_transaction_log_line:
                        card_transaction_log_line.write({'synced': False})

                    if order.contract_doc_attachment_id and order.contract_doc_attachment_id.improveit_id:
                        order.contract_doc_attachment_id.write({'improveit_id': ''})
                    credit_application = self.env['team.credit.application'].search([
                        ('order_id', '=', order.id)
                    ], limit=1, order='id desc')
                    if credit_application:
                        if credit_application.improveit_id:
                            credit_application.write({'improveit_id': ''})
                        if not credit_application.attachment_id:
                            credit_application.generate_link(order)
                        attachment = credit_application.attachment_id
                        if attachment.improveit_id:
                            attachment.write({'improveit_id': ''})
                    ext_credit_application = self.env['otl.versatile.credit.application'].search(
                        [('appointment_id', '=', int(appointment.id)), ('status', '=ilike', 'approved')], limit=1)
                    if ext_credit_application and ext_credit_application.improveit_id:
                        ext_credit_application.write({'improveit_id': ''})
                # initiate resync
                appointment.action_initiate_sync_to_i360({'appointment_id': appointment.id, 'sync_delay': 1})
        except Exception:
            pass

        return {'type': 'ir.actions.act_window_close'}
