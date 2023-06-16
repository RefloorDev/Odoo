# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re
import datetime

from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError

email_validator = re.compile(r"[^@]+@[^@]+\.[^@]+")
_logger = logging.getLogger(__name__)


def dict_keys_startswith(dictionary, string):
    """Returns a dictionary containing the elements of <dict> whose keys start with <string>.
        .. note::
            This function uses dictionary comprehensions (Python >= 2.7)
    """
    return {k: v for k, v in dictionary.items() if k.startswith(string)}


class TeamQuoteQuestion(models.Model):
    _name = 'team.quote.question'
    _description = "Quote Questions"
    _order = "sequence asc"

    sequence = fields.Integer('Sequence', default=10)
    name = fields.Char('Question', required=True)
    code = fields.Char('Code', required=True, size=100)
    active = fields.Boolean('Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    description = fields.Html('Description', help="Use this field to add additional explanations about your question")
    room_ids = fields.Many2many('team.room.room', string="Rooms")
    product_category_ids = fields.Many2many('product.category', string='Product Categories')
    question_type = fields.Selection([
        ('textbox', 'Single Line Text Box'),
        ('numerical_box', 'Numerical Value'),
        ('simple_choice', 'Multiple choice: only one answer'),
        ('multiple_choice', 'Multiple choice: multiple answers allowed'),
    ], string='Question Type')
    default_answer = fields.Text("Default Answer")
    # question_type = fields.Selection([
    #     ('free_text', 'Multiple Lines Text Box'),
    #     ('textbox', 'Single Line Text Box'),
    #     ('numerical_box', 'Numerical Value'),
    #     ('date', 'Date'),
    #     ('datetime', 'Datetime'),
    #     ('simple_choice', 'Multiple choice: only one answer'),
    #     ('multiple_choice', 'Multiple choice: multiple answers allowed'),
    # ], string='Question Type')
    # simple choice / multiple choice / matrix
    labels_ids = fields.One2many(
        'team.quote.label', 'question_id', string='Types of answers', copy=True,
        help='Labels used for proposed choices: simple choice, multiple choice and columns of matrix')
    # Validation
    validation_required = fields.Boolean('Validate entry')
    validation_email = fields.Boolean('Input must be an email')
    validation_length_min = fields.Integer('Minimum Text Length')
    validation_length_max = fields.Integer('Maximum Text Length')
    validation_min_float_value = fields.Float('Minimum value')
    validation_max_float_value = fields.Float('Maximum value')
    validation_min_date = fields.Date('Minimum Date')
    validation_max_date = fields.Date('Maximum Date')
    validation_min_datetime = fields.Datetime('Minimum Datetime')
    validation_max_datetime = fields.Datetime('Maximum Datetime')
    validation_error_msg = fields.Char('Validation Error message', translate=True,
                                       default=lambda self: _("The answer you entered is not valid."))
    # Constraints on number of answers (matrices)
    constr_mandatory = fields.Boolean('Mandatory Answer')
    constr_error_msg = fields.Char('Error message', translate=True,
                                   default=lambda self: _("This question requires an answer."))
    show_in_measurement = fields.Boolean('Show in Measurement', default=False)
    show_in_contract = fields.Boolean('Show in Contract', default=False)
    reflect_cost = fields.Boolean('Reflect in Cost Calculation', default=False)
    calculation_type = fields.Selection([
        ('fixed', 'Fixed Amount'),
        ('unit', 'Unit Price'),
        ('sqft', 'Squre Feet'),
        # ('perc', 'Percentage'),
        # ('code', 'Python Code')
    ], 'Type of Calculation', default='fixed')
    amount = fields.Float('Amount')
    differ_cost_based_on_count = fields.Boolean('Change Cost Based on Count', default=False)
    count_cost_line = fields.One2many('team.quote.count.cost', 'question_id', string='Count Based Costs', copy=False)
    labor_charge_units = fields.Char("Labor Charge Units")
    amount_included = fields.Float('Included Amount', help='It denotes the amount which already included in the quote')
    exclude_from_discount = fields.Boolean('Exclude From Discount', default=False)
    multiply_with_area = fields.Boolean('Multiply with Room Area', default=False)
    set_default_answer = fields.Boolean('Set Default Answer', default=False)
    applicable_rooms = fields.Many2many('team.room.room', 'applicable_question_room_rel', 'question_id', 'room_id', string="Applicable Rooms")
    applicable_current_surface = fields.Char('Applicable Current Surface')
    exclude_from_promotion = fields.Boolean('Exclude From Promotion', default=False)

    _sql_constraints = [
        ('positive_len_min', 'CHECK (validation_length_min >= 0)', 'A length must be positive!'),
        ('positive_len_max', 'CHECK (validation_length_max >= 0)', 'A length must be positive!'),
        ('validation_length', 'CHECK (validation_length_min <= validation_length_max)',
         'Max length cannot be smaller than min length!'),
        ('validation_float', 'CHECK (validation_min_float_value <= validation_max_float_value)',
         'Max value cannot be smaller than min value!'),
        ('validation_date', 'CHECK (validation_min_date <= validation_max_date)',
         'Max date cannot be smaller than min date!'),
        ('validation_datetime', 'CHECK (validation_min_datetime <= validation_max_datetime)',
         'Max datetime cannot be smaller than min datetime!'),
        ('code_company_uniq', 'unique (code,company_id)', 'The code of the question must be unique per company!'),
    ]

    @api.onchange('validation_email')
    def _onchange_validation_email(self):
        if self.validation_email:
            self.validation_required = False

    # Validation methods

    def validate_question(self, post, answer_tag):
        """ Validate question, depending on question type and parameters """
        self.ensure_one()
        try:
            checker = getattr(self, 'validate_' + self.question_type)
        except AttributeError:
            _logger.warning(self.question_type + ": This type of question has no validation method")
            return {}
        else:
            return checker(post, answer_tag)

    def validate_free_text(self, post, answer_tag):
        self.ensure_one()
        errors = {}
        answer = post[answer_tag].strip()
        # Empty answer to mandatory question
        if self.constr_mandatory and not answer:
            errors.update({answer_tag: self.constr_error_msg})
        return errors

    def validate_textbox(self, post, answer_tag):
        self.ensure_one()
        errors = {}
        answer = post[answer_tag].strip()
        # Empty answer to mandatory question
        if self.constr_mandatory and not answer:
            errors.update({answer_tag: self.constr_error_msg})
        # Email format validation
        # Note: this validation is very basic:
        #     all the strings of the form
        #     <something>@<anything>.<extension>
        #     will be accepted
        if answer and self.validation_email:
            if not email_validator.match(answer):
                errors.update({answer_tag: _('This answer must be an email address')})
        # Answer validation (if properly defined)
        # Length of the answer must be in a range
        if answer and self.validation_required:
            if not (self.validation_length_min <= len(answer) <= self.validation_length_max):
                errors.update({answer_tag: self.validation_error_msg})
        return errors

    def validate_numerical_box(self, post, answer_tag):
        self.ensure_one()
        errors = {}
        answer = post[answer_tag].strip()
        # Empty answer to mandatory question
        if self.constr_mandatory and not answer:
            errors.update({answer_tag: self.constr_error_msg})
        # Checks if user input is a number
        if answer:
            try:
                floatanswer = float(answer)
            except ValueError:
                errors.update({answer_tag: _('This is not a number')})
        # Answer validation (if properly defined)
        if answer and self.validation_required:
            # Answer is not in the right range
            with tools.ignore(Exception):
                floatanswer = float(answer)  # check that it is a float has been done hereunder
                if not (self.validation_min_float_value <= floatanswer <= self.validation_max_float_value):
                    errors.update({answer_tag: self.validation_error_msg})
        return errors

    def date_validation(self, date_type, post, answer_tag, min_value, max_value):
        self.ensure_one()
        errors = {}
        if date_type not in ('date', 'datetime'):
            raise ValueError("Unexpected date type value")
        answer = post[answer_tag].strip()
        # Empty answer to mandatory question
        if self.constr_mandatory and not answer:
            errors.update({answer_tag: self.constr_error_msg})
        # Checks if user input is a date
        if answer:
            try:
                if date_type == 'datetime':
                    dateanswer = fields.Datetime.from_string(answer)
                else:
                    dateanswer = fields.Date.from_string(answer)
            except ValueError:
                errors.update({answer_tag: _('This is not a date')})
                return errors
        # Answer validation (if properly defined)
        if answer and self.validation_required:
            # Answer is not in the right range
            try:
                if date_type == 'datetime':
                    date_from_string = fields.Datetime.from_string
                else:
                    date_from_string = fields.Date.from_string
                dateanswer = date_from_string(answer)
                min_date = date_from_string(min_value)
                max_date = date_from_string(max_value)

                if min_date and max_date and not (min_date <= dateanswer <= max_date):
                    # If Minimum and Maximum Date are entered
                    errors.update({answer_tag: self.validation_error_msg})
                elif min_date and not min_date <= dateanswer:
                    # If only Minimum Date is entered and not Define Maximum Date
                    errors.update({answer_tag: self.validation_error_msg})
                elif max_date and not dateanswer <= max_date:
                    # If only Maximum Date is entered and not Define Minimum Date
                    errors.update({answer_tag: self.validation_error_msg})
            except ValueError:  # check that it is a date has been done hereunder
                pass
        return errors

    def validate_date(self, post, answer_tag):
        return self.date_validation('date', post, answer_tag, self.validation_min_date, self.validation_max_date)

    def validate_datetime(self, post, answer_tag):
        return self.date_validation('datetime', post, answer_tag, self.validation_min_datetime,
                                    self.validation_max_datetime)

    def validate_simple_choice(self, post, answer_tag):
        self.ensure_one()
        errors = {}
        # Empty answer to mandatory self
        if self.constr_mandatory and answer_tag not in post:
            errors.update({answer_tag: self.constr_error_msg})
        if self.constr_mandatory and answer_tag in post and not post[answer_tag].strip():
            errors.update({answer_tag: self.constr_error_msg})
        # Answer is a comment and is empty
        if self.constr_mandatory and answer_tag in post and post[answer_tag] == "-1":
            errors.update({answer_tag: self.constr_error_msg})
        return errors

    def validate_multiple_choice(self, post, answer_tag):
        self.ensure_one()
        errors = {}
        if self.constr_mandatory:
            answer_candidates = dict_keys_startswith(post, answer_tag)
            # Preventing answers with blank value
            if all(not answer.strip() for answer in answer_candidates.values()) and answer_candidates:
                errors.update({answer_tag: self.constr_error_msg})
            # There is no answer at all
            if not answer_candidates:
                errors.update({answer_tag: self.constr_error_msg})
        return errors


class TeamQuoteLabel(models.Model):
    """ A suggested answer for a question """
    _name = 'team.quote.label'
    _rec_name = 'value'
    _order = 'sequence,id'
    _description = 'Quote Label'

    question_id = fields.Many2one('team.quote.question', string='Question', ondelete='cascade')
    sequence = fields.Integer('Label Sequence order', default=10)
    value = fields.Char('Suggested value', translate=True, required=True)
    is_correct = fields.Boolean('Is a correct answer')
    answer_score = fields.Float('Score for this choice',
                                help="A positive score indicates a correct choice; a negative or null score indicates a wrong answer")


class TeamQuoteCountCost(models.Model):
    _name = 'team.quote.count.cost'
    _description = 'Count based Costs'
    _order = 'count asc'

    question_id = fields.Many2one('team.quote.question', string='Question', ondelete='cascade')
    count = fields.Integer("Maximum Allowed Count")
    amount = fields.Float("Amount")

    _sql_constraints = [
        ('positive_count', 'CHECK (count > 0)', 'Maximum Allowed Count must be greater than zero!')
    ]
