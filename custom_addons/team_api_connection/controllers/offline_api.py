from odoo import fields,http, _
from odoo.http import content_disposition, dispatch_rpc, request, \
    serialize_exception as _serialize_exception, Response
from odoo.exceptions import AccessError, UserError
import json
from json import loads
from odoo.tools import format_date, str2bool
import requests
from odoo.tools import ustr, consteq, frozendict, pycompat, unique, date_utils
from odoo.http import route
import ast
import base64
import werkzeug
from PIL import Image
from datetime import datetime, timedelta
from odoo.addons.team_api_configuration.jwt.api_jws import encode as JWT_ENCODE
from odoo.addons.team_api_configuration.jwt.api_jws import decode as JWT_DECODE

JWT_SECRET = 'secret'
JWT_ALGORITHM = 'HS256'

try:
    from xmlrpc import client as xmlrpclib
except ImportError:
    import xmlrpclib

try:
    from secrets import token_hex
except ImportError:
    from os import urandom


    def token_hex(nbytes=None):
        return urandom(nbytes).hex()

from odoo.addons.team_api_configuration.controllers.configurations import URL, DB, API_USER_ID, API_USER_PASSWORD
from odoo.addons.team_api_connection.controllers.main import API_Homes


# common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(URL))
# models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))

# At top of file where ServerProxy is first created:
models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL), allow_none=True)
common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(URL), allow_none=True)

import logging

_logger = logging.getLogger(__name__)


class APIHomes(API_Homes):

    def __init__(self, *args):
        super(APIHomes, self).__init__(*args)
        self.create_order_and_update_measurements_api_queue = dict()
        self.generate_contract_document_api_queue = dict()
        self.update_additional_appointment_data_api_queue = dict()
        self.update_arrival_departure_time_api_queue = dict()
        self.update_manual_arrival_date_api_queue = dict()
        self.send_review_link_api_queue = dict()
        self.get_appointment_current_status_api_queue = dict()
        self.get_credit_application_status_api_queue = dict()
        self.initiate_i360_sync_api_queue = dict()
        self.image_sync_api_queue = dict()
        self.appointment_sync_api_queue = dict()
        self.available_installation_date_api_queue = dict()
        self.selected_installation_date_api_queue = dict()

    # def reverse(self, string):
    #     return "".join(reversed(string))
    #
    # def token_extract(self, token):
    #     values = {}
    #     token = (self.reverse(token)).encode("utf-8")
    #     try:
    #         token_decode = JWT_DECODE(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    #         token_decode = token_decode.decode("utf-8")
    #         values = ast.literal_eval(token_decode)
    #     except:
    #         token_decode = ''
    #     return values
    #
    # def get_credentials(self, token):
    #     user_id = False
    #     password = False
    #
    #     values = self.token_extract(token)
    #     if values == {}:
    #         return False, False
    #     user_id = values.get('user_id', False)
    #     password = values.get('password', False)
    #     if user_id:
    #         user_id = int(user_id)
    #     return user_id, password

    @route('/api/logout_from_device', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def logout_from_device(self, **kwargs):
        params = request.params.copy()
        token = params.get('token', False)
        if not token:
            _logger.info("------------Token Missing in main logout_from_device api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main logout_from_device api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main logout_from_device api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'res.users', 'action_logout_from_device', [int(uid)])
            request.env['res.users'].action_log_user_authentication(uid, 'logout', token)
        else:
            result = message
        return json.dumps(result)

    @route('/api/get_master_data', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def get_master_data(self, **kwargs):
        """
            Get Master Data
            @api {POST}/api/get_master_data Get Master Data Contents
            @apiVersion 1.0.0
            @apiName Get Master Data
            @apiGroup Salesman
            @apiDescription Get Master Data Contents

            @apiParam {String} token Token.
            @apiParamExample {form-data} Request-Example:
            token:cQQ4u07DsUKBjCzJdG1DZy7RDnvPeEVnnfidHob_EQw.9JCUQFEdzVGdiojIkJ3b3N3chBnIsUTNxojIkl2XyV2c1Jye.9JiN1IzUIJiOicGbhJCLiQ1VKJiOiAXe0Jye

            @apiSuccessExample {json} Success-Response:
             HTTP/1.1 200 OK
            {
                "result": "Success",
                "message": "Master Data retrieved successfully.",
                "rooms": [
                    {
                        "id": 24,
                        "name": "CLOSET 2",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 25,
                        "name": "STAIRS 3",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Stairs"
                    },
                    {
                        "id": 26,
                        "name": "STAIRS 2",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Stairs"
                    },
                    {
                        "id": 27,
                        "name": "LANDING 3",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 28,
                        "name": "LANDING 2",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 29,
                        "name": "HALLWAY 2",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 30,
                        "name": "NOOK",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 31,
                        "name": "HALLWAY 3",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 19,
                        "name": "LIVING ROOM",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 11,
                        "name": "DEN",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 20,
                        "name": "OFFICE",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 4,
                        "name": "BATHROOM 2",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 18,
                        "name": "LAUNDRY ROOM",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 22,
                        "name": "STUDY",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 1,
                        "name": "BAR",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 8,
                        "name": "BEDROOM 3",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 9,
                        "name": "BEDROOM 4",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 13,
                        "name": "FAMILY ROOM",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 32,
                        "name": "HALLWAY 1",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 14,
                        "name": "FOYER",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 23,
                        "name": "SUNROOM",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 5,
                        "name": "BATHROOM 3",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 33,
                        "name": "CLOSET 1",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 16,
                        "name": "KITCHEN",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 2,
                        "name": "BASEMENT",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 21,
                        "name": "STAIRS",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Stairs"
                    },
                    {
                        "id": 3,
                        "name": "BATHROOM 1",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 7,
                        "name": "BEDROOM 2",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 12,
                        "name": "DINING ROOM",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 34,
                        "name": "LANDING 1",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 6,
                        "name": "BEDROOM 1",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 35,
                        "name": "CLOSET 3",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 36,
                        "name": "CLOSET 4",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    }
                ],
                "questionnaires": [
                    {
                        "id": 1,
                        "name": "Current Surface",
                        "code": "CurrentCoveringType",
                        "company_id": 1,
                        "description": "",
                        "question_type": "simple_choice",
                        "Refelct_in_cost": true,
                        "calculation_type": "sqft",
                        "amount": 0,
                        "amount_included": 0,
                        "sequence": 0,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 1,
                                "sequence": 10,
                                "value": "Carpet",
                                "is_correct": false,
                                "answer_score": ""
                            },
                            {
                                "question_id": 1,
                                "sequence": 10,
                                "value": "Ceramic Tile (backerboard)",
                                "is_correct": false,
                                "answer_score": 5.5
                            },
                            {
                                "question_id": 1,
                                "sequence": 10,
                                "value": "Ceramic Tile (mud bed)",
                                "is_correct": false,
                                "answer_score": 10.0
                            },
                            {
                                "question_id": 1,
                                "sequence": 10,
                                "value": "Concrete / Cement",
                                "is_correct": false,
                                "answer_score": ""
                            },
                            {
                                "question_id": 1,
                                "sequence": 10,
                                "value": "Hardwood",
                                "is_correct": false,
                                "answer_score": 2.0
                            },
                            {
                                "question_id": 1,
                                "sequence": 10,
                                "value": "Laminate",
                                "is_correct": false,
                                "answer_score": ""
                            },
                            {
                                "question_id": 1,
                                "sequence": 10,
                                "value": "Linoleum",
                                "is_correct": false,
                                "answer_score": ""
                            },
                            {
                                "question_id": 1,
                                "sequence": 10,
                                "value": "Sticky Tile",
                                "is_correct": false,
                                "answer_score": ""
                            },
                            {
                                "question_id": 1,
                                "sequence": 10,
                                "value": "Other",
                                "is_correct": false,
                                "answer_score": ""
                            },
                            {
                                "question_id": 1,
                                "sequence": 10,
                                "value": "Sheet Vinyl",
                                "is_correct": false,
                                "answer_score": 1.75
                            }
                        ]
                    },
                    {
                        "id": 2,
                        "name": "Remove Existing Surface",
                        "code": "RemoveCurrentCovering",
                        "company_id": 1,
                        "description": "",
                        "question_type": "simple_choice",
                        "Refelct_in_cost": false,
                        "calculation_type": "unit",
                        "amount": 0,
                        "amount_included": 0,
                        "sequence": 1,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 2,
                                "sequence": 10,
                                "value": "Yes",
                                "is_correct": false,
                                "answer_score": ""
                            },
                            {
                                "question_id": 2,
                                "sequence": 10,
                                "value": "No",
                                "is_correct": false,
                                "answer_score": ""
                            }
                        ]
                    },
                    {
                        "id": 3,
                        "name": "Appliances to be Moved",
                        "code": "Appliances",
                        "company_id": 1,
                        "description": "",
                        "question_type": "numerical_box",
                        "Refelct_in_cost": false,
                        "calculation_type": "unit",
                        "amount": 0,
                        "amount_included": 0,
                        "sequence": 2,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 3,
                                "value": ""
                            }
                        ]
                    },
                    {
                        "id": 18,
                        "name": "Stair Count",
                        "code": "StairCount",
                        "company_id": 1,
                        "description": "",
                        "question_type": "numerical_box",
                        "Refelct_in_cost": true,
                        "calculation_type": "unit",
                        "amount": 210.0,
                        "amount_included": 0,
                        "sequence": 2,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": []
                    },
                    {
                        "id": 14,
                        "name": "Stair Width",
                        "code": "StairWidth",
                        "company_id": 1,
                        "description": "",
                        "question_type": "numerical_box",
                        "Refelct_in_cost": false,
                        "calculation_type": "unit",
                        "amount": 0,
                        "amount_included": 0,
                        "sequence": 3,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": []
                    },
                    {
                        "id": 4,
                        "name": "Standard Furniture to be Moved",
                        "code": "FurnitureNormal",
                        "company_id": 1,
                        "description": "",
                        "question_type": "simple_choice",
                        "Refelct_in_cost": false,
                        "calculation_type": "fixed",
                        "amount": 0,
                        "amount_included": 0,
                        "sequence": 3,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 4,
                                "value": ""
                            },
                            {
                                "question_id": 4,
                                "sequence": 10,
                                "value": "Yes",
                                "is_correct": false,
                                "answer_score": ""
                            },
                            {
                                "question_id": 4,
                                "sequence": 10,
                                "value": "No",
                                "is_correct": false,
                                "answer_score": ""
                            }
                        ]
                    },
                    {
                        "id": 19,
                        "name": "Cover Risers",
                        "code": "StairCoverRisers",
                        "company_id": 1,
                        "description": "",
                        "question_type": "simple_choice",
                        "Refelct_in_cost": false,
                        "calculation_type": "unit",
                        "amount": 0,
                        "amount_included": 0,
                        "sequence": 4,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 19,
                                "sequence": 10,
                                "value": "Yes",
                                "is_correct": false,
                                "answer_score": ""
                            },
                            {
                                "question_id": 19,
                                "sequence": 10,
                                "value": "No",
                                "is_correct": false,
                                "answer_score": ""
                            }
                        ]
                    },
                    {
                        "id": 5,
                        "name": "Heavy Furniture to be Moved",
                        "code": "FurnitureHeavy",
                        "company_id": 1,
                        "description": "",
                        "question_type": "numerical_box",
                        "Refelct_in_cost": true,
                        "calculation_type": "fixed",
                        "amount": 120.0,
                        "amount_included": 0,
                        "sequence": 4,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 5,
                                "value": ""
                            }
                        ]
                    },
                    {
                        "id": 6,
                        "name": "Piano or Pool Table",
                        "code": "MovePianoPoolTable",
                        "company_id": 1,
                        "description": "",
                        "question_type": "simple_choice",
                        "Refelct_in_cost": true,
                        "calculation_type": "fixed",
                        "amount": 0,
                        "amount_included": 0,
                        "sequence": 5,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 6,
                                "value": ""
                            },
                            {
                                "question_id": 6,
                                "sequence": 10,
                                "value": "Piano",
                                "is_correct": false,
                                "answer_score": 250.0
                            },
                            {
                                "question_id": 6,
                                "sequence": 10,
                                "value": "Pool Table",
                                "is_correct": false,
                                "answer_score": 330.0
                            }
                        ]
                    },
                    {
                        "id": 16,
                        "name": "Pedestal Sink R/R",
                        "code": "PedestalSink",
                        "company_id": 1,
                        "description": "",
                        "question_type": "simple_choice",
                        "Refelct_in_cost": true,
                        "calculation_type": "unit",
                        "amount": 100.0,
                        "amount_included": 0,
                        "sequence": 6,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 16,
                                "value": ""
                            },
                            {
                                "question_id": 16,
                                "sequence": 10,
                                "value": "Yes",
                                "is_correct": false,
                                "answer_score": ""
                            },
                            {
                                "question_id": 16,
                                "sequence": 10,
                                "value": "No",
                                "is_correct": false,
                                "answer_score": ""
                            }
                        ]
                    },
                    {
                        "id": 8,
                        "name": "Fireplace Scribe/Seal ft",
                        "code": "FireplaceScribeSealFt",
                        "company_id": 1,
                        "description": "",
                        "question_type": "numerical_box",
                        "Refelct_in_cost": true,
                        "calculation_type": "sqft",
                        "amount": 5.0,
                        "amount_included": 0,
                        "sequence": 7,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 8,
                                "value": ""
                            }
                        ]
                    },
                    {
                        "id": 20,
                        "name": "Undercut Fireplace",
                        "code": "FireplaceUndercut",
                        "company_id": 1,
                        "description": "",
                        "question_type": "numerical_box",
                        "Refelct_in_cost": true,
                        "calculation_type": "unit",
                        "amount": 10.0,
                        "amount_included": 0,
                        "sequence": 8,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 20,
                                "value": ""
                            }
                        ]
                    },
                    {
                        "id": 10,
                        "name": "Toilet R/R",
                        "code": "Toilet",
                        "company_id": 1,
                        "description": "",
                        "question_type": "simple_choice",
                        "Refelct_in_cost": true,
                        "calculation_type": "unit",
                        "amount": 85.0,
                        "amount_included": 0,
                        "sequence": 9,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 10,
                                "value": ""
                            },
                            {
                                "question_id": 10,
                                "sequence": 10,
                                "value": "Yes",
                                "is_correct": false,
                                "answer_score": ""
                            },
                            {
                                "question_id": 10,
                                "sequence": 10,
                                "value": "No",
                                "is_correct": false,
                                "answer_score": ""
                            }
                        ]
                    },
                    {
                        "id": 11,
                        "name": "1/4 Plywood Sheets Required",
                        "code": "QuarterInchPlywood",
                        "company_id": 1,
                        "description": "",
                        "question_type": "numerical_box",
                        "Refelct_in_cost": true,
                        "calculation_type": "unit",
                        "amount": 95.0,
                        "amount_included": 0,
                        "sequence": 10,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 11,
                                "value": ""
                            }
                        ]
                    },
                    {
                        "id": 12,
                        "name": "3/4 Plywood Sheets Required",
                        "code": "ThreeQuarterInchPlywood",
                        "company_id": 1,
                        "description": "",
                        "question_type": "numerical_box",
                        "Refelct_in_cost": true,
                        "calculation_type": "unit",
                        "amount": 95.0,
                        "amount_included": 0,
                        "sequence": 11,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 12,
                                "value": ""
                            }
                        ]
                    },
                    {
                        "id": 13,
                        "name": "Sqft of Leveling Required",
                        "code": "LevelingSolutionSqft",
                        "company_id": 1,
                        "description": "",
                        "question_type": "numerical_box",
                        "Refelct_in_cost": true,
                        "calculation_type": "sqft",
                        "amount": 2.0,
                        "amount_included": 0,
                        "sequence": 12,
                        "default_answer": "",
                        "exclude_from_discount": false,
                        "quote_label": [
                            {
                                "question_id": 13,
                                "value": ""
                            }
                        ]
                    }
                ],
                "flooring_colors": [
                    {
                        "material_id": 25110,
                        "name": "Stairs - Econoline",
                        "color": "Artisan Plank Country Natural",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/CountryNatural.png"
                    },
                    {
                        "material_id": 25111,
                        "name": "Stairs - Econoline",
                        "color": "Artisan Plank Finnish Pine",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/FinnishPine.jpg"
                    },
                    {
                        "material_id": 25079,
                        "name": "Stairs - Econoline",
                        "color": "Artisan Plank Frontier",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Frontier.png"
                    },
                    {
                        "material_id": 25062,
                        "name": "Stairs - Econoline",
                        "color": "Artisan Plank Highland Grey",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/HighlandGrey.png"
                    },
                    {
                        "material_id": 25063,
                        "name": "Stairs - Econoline",
                        "color": "Artisan Plank Platinum Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/PlatinumOak.jpg"
                    },
                    {
                        "material_id": 25014,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Belmont Hickory",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Belmont_Hickory.jpg"
                    },
                    {
                        "material_id": 25015,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Biscayne Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Biscayne_Oak.jpg"
                    },
                    {
                        "material_id": 25016,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Chandler Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Chandler_Oak.jpg"
                    },
                    {
                        "material_id": 25017,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Chesapeake Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Chesapeake_Oak.jpg"
                    },
                    {
                        "material_id": 25018,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Copano Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Copano_Oak.jpg"
                    },
                    {
                        "material_id": 25019,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Duxbury Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Duxbury_Oak.jpg"
                    },
                    {
                        "material_id": 25024,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Enhanced Aldergrove Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Aldergrove_Oak.jpg"
                    },
                    {
                        "material_id": 25025,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Enhanced Elster Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Elster_Oak.jpg"
                    },
                    {
                        "material_id": 25026,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Enhanced Nicola Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Nicola_Oak.jpg"
                    },
                    {
                        "material_id": 25027,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Enhanced Shoreline Maple",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Shoreline_Maple.jpg"
                    },
                    {
                        "material_id": 25020,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Galveston Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Galveston_Oak.jpg"
                    },
                    {
                        "material_id": 25028,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Hd Cheshire Elm",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Cheshire_Elm.jpg"
                    },
                    {
                        "material_id": 25021,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Hobbs Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Hobbs_Oak.jpg"
                    },
                    {
                        "material_id": 25022,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Monterey Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Monterey_Oak.jpg"
                    },
                    {
                        "material_id": 25023,
                        "name": "Stairs - Econoline",
                        "color": "Coretec Pro Plus Quincy Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Quincy_Oak.jpg"
                    },
                    {
                        "material_id": 24948,
                        "name": "Vinyl Flooring - Smart Choice",
                        "color": "Delacy",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Delacy.png"
                    },
                    {
                        "material_id": 25108,
                        "name": "Stairs - Econoline",
                        "color": "Encore Cordova Cherry",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore_Cordova_Cherry.png"
                    },
                    {
                        "material_id": 25109,
                        "name": "Stairs - Econoline",
                        "color": "Encore Tavern Hickory",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore_Tavern_Hickory.png"
                    },
                    {
                        "material_id": 25114,
                        "name": "Stairs - Econoline",
                        "color": "Encore Teak Harbor",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore_Teak_Harbor.png"
                    },
                    {
                        "material_id": 24942,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting Aged Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_Aged_Oak.jpg"
                    },
                    {
                        "material_id": 24934,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting Barnwood",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_Barnwood.jpg"
                    },
                    {
                        "material_id": 24941,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting Bold Wood",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_Bold_Wood.jpg"
                    },
                    {
                        "material_id": 24933,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting Brushed Hickory",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_Brushed_Hickory.jpg"
                    },
                    {
                        "material_id": 24936,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting Canyon Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_Canyon_Oak.jpg"
                    },
                    {
                        "material_id": 24939,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting Distinct Wood",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_Distinct_Wood.jpg"
                    },
                    {
                        "material_id": 24935,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting English Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_English_Oak.jpg"
                    },
                    {
                        "material_id": 24945,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting Heritage Wood",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_Heritage_Wood.jpg"
                    },
                    {
                        "material_id": 24940,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting Laurel Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_Laurel_Oak.jpg"
                    },
                    {
                        "material_id": 24938,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting Monticello (Multi-width)",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_Monticello.jpg"
                    },
                    {
                        "material_id": 24937,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting Reclaimed",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_Reclaimed.jpg"
                    },
                    {
                        "material_id": 24944,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting Umber",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_Umber.jpg"
                    },
                    {
                        "material_id": 24943,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting Vintage Oak (Multi-width)",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_XL_Vintage_Oak.jpg"
                    },
                    {
                        "material_id": 24932,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting Weathered",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_Weathered.jpg"
                    },
                    {
                        "material_id": 24929,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting XL Appalachian Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_XL_Appalachian_Oak.jpg"
                    },
                    {
                        "material_id": 24930,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting XL Driftwood Grey Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_XL_Driftwood_Grey Oak.jpg"
                    },
                    {
                        "material_id": 24926,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting XL Greystone Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_XL_Greystone_Oak.jpg"
                    },
                    {
                        "material_id": 25029,
                        "name": "Stairs - Premium",
                        "color": "Everlasting XL Kentucky Bourbon Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_XL_Kentucky_Bourbon_Oak.jpg"
                    },
                    {
                        "material_id": 24931,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting XL New England Maple",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_XL_New_England_Maple.jpg"
                    },
                    {
                        "material_id": 24927,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting XL Smokehouse Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Everlasting_XL_Smokehouse_Oak.jpg"
                    },
                    {
                        "material_id": 24928,
                        "name": "Stairs - Econoline",
                        "color": "Everlasting XL Whiskey Barrel Oak",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/WhiskeyBarrelOak600_600.jpg"
                    },
                    {
                        "material_id": 25051,
                        "name": "Stairs - Econoline",
                        "color": "Heatherstone",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Heatherstone.jpg"
                    },
                    {
                        "material_id": 24919,
                        "name": "Stairs - Econoline",
                        "color": "Pure Tile Newcastle Dove",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Pure_Tile_Newcastle_Dove.jpg"
                    },
                    {
                        "material_id": 24923,
                        "name": "Stairs - Econoline",
                        "color": "Pure Tile Newcastle Shadow",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Pure_Tile_Newcastle_Shadow.jpg"
                    },
                    {
                        "material_id": 24925,
                        "name": "Stairs - Econoline",
                        "color": "Pure Tile Newcastle Shell",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Pure_Tile_Newcastle_Shell.jpg"
                    },
                    {
                        "material_id": 24924,
                        "name": "Stairs - Econoline",
                        "color": "Pure Tile Newcastle Smoke",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Pure_Tile_Newcastle_Smoke.jpg"
                    },
                    {
                        "material_id": 24921,
                        "name": "Stairs - Econoline",
                        "color": "Pure Tile Zinc Stone",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Pure_Tile_Zinc_Stone.jpg"
                    },
                    {
                        "material_id": 24922,
                        "name": "Stairs - Econoline",
                        "color": "Pure Tile Zinc Umber",
                        "material_image_url": "https://refloormichigan.com/FlooringThumbs/Pure_Tile_Zinc_Umber.jpg"
                    }
                ],
                "molding_types": [
                    {
                        "molding_id": 5,
                        "name": "NO MOLDING"
                    },
                    {
                        "molding_id": 2,
                        "name": "Vinyl White"
                    },
                    {
                        "molding_id": 3,
                        "name": "Unfinished"
                    }
                ],
                "discount_coupons": [
                    {
                        "Code": "BIGOFF",
                        "Amount": "1000",
                        "Type": "Dollars"
                    },
                    {
                        "Code": "SAVE500",
                        "Amount": "500",
                        "Type": "Dollars"
                    },
                    {
                        "Code": "MAGIC5",
                        "Amount": "5",
                        "Type": "Percent"
                    }
                ],
                "product_plans": [
                    {
                        "id": 79,
                        "plan_title": "Vinyl Flooring - Economy",
                        "plan_subtitle": "Pressboard",
                        "description": "Recommendation - If you are flipping your house",
                        "material_cost": 10.56,
                        "warranty": "",
                        "sequence": 1,
                        "company_id": 0,
                        "cost_per_sqft": 13.56,
                        "monthly_promo": 0,
                        "warranty_info": "1 year warranty",
                        "eligible_for_discounts": "false",
                        "unit_of_measure": "each",
                        "grade": "Econoline",
                        "stair_cost": 132.3
                    },
                    {
                        "id": 311,
                        "plan_title": "Vinyl Flooring - Standard",
                        "plan_subtitle": "Vinyl Plank",
                        "description": "Recommendation - if you are moving in the next 5 years",
                        "material_cost": 14.61,
                        "warranty": "",
                        "sequence": 2,
                        "company_id": 0,
                        "cost_per_sqft": 17.61,
                        "monthly_promo": 0,
                        "warranty_info": "4 year warranty",
                        "eligible_for_discounts": "false",
                        "unit_of_measure": "each",
                        "grade": "Standard",
                        "stair_cost": 189.0
                    },
                    {
                        "id": 312,
                        "plan_title": "Vinyl Flooring - Smart Choice",
                        "plan_subtitle": "",
                        "description": "Recommendation - If you are planning to stay in your home for 5 years or more",
                        "material_cost": 16.24,
                        "warranty": "",
                        "sequence": 3,
                        "company_id": 0,
                        "cost_per_sqft": 19.24,
                        "monthly_promo": 0,
                        "warranty_info": "Lifetime Guarantee",
                        "eligible_for_discounts": "true",
                        "unit_of_measure": "each",
                        "grade": "Smart Choice",
                        "stair_cost": 210.0
                    },
                    {
                        "id": 313,
                        "plan_title": "Vinyl Flooring - Premium",
                        "plan_subtitle": "Hardwood",
                        "description": "Recommendation - If you are planning to use high end",
                        "material_cost": 19.49,
                        "warranty": "",
                        "sequence": 4,
                        "company_id": 0,
                        "cost_per_sqft": 22.49,
                        "monthly_promo": 0,
                        "warranty_info": "10 Year Warranty",
                        "eligible_for_discounts": "false",
                        "unit_of_measure": "each",
                        "grade": "Premium",
                        "stair_cost": 252.0
                    }
                ]
            }

            @apiErrorExample {json} Error-Response:
            HTTP/1.1 200 OK
            {
                "result": "AuthFailed",
                "message": "You have been logged into another device using the same account. Please login again.",
                "token": 1
            }
            {
                "result": "Failed",
                "message": "Something went wrong while fetching master data.",
                "token": 1
            }

            @apiError (Error Code) {Number} 500 Internal Server Error.

            @apiSampleRequest off
        """
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        app_version = params.get('app_version', '')
        if not token:
            _logger.info("------------Token Missing in main get_master_data api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main get_master_data api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main get_master_data api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'res.users', 'get_master_data_contents', [{'app_version': app_version}])
            stair_width_data = models.execute_kw(DB, int(uid), password, 'res.users', 'get_stair_width_id', [{}])
            get_stair_cover_risers_data = models.execute_kw(DB, int(uid), password, 'res.users', 'get_stair_cover_risers', [{}])
            questionnaires = result.get('questionnaires', [])
            stair_width_id = stair_width_data.get('stair_width_id')
            stair_cover_risers_id = get_stair_cover_risers_data.get('stair_cover_risers')
            if questionnaires:
                for questionnaire in questionnaires:
                    if stair_width_id and questionnaire.get("id") == stair_width_id:
                        questionnaire["id"] = 9
                    elif stair_cover_risers_id and questionnaire.get("id") == stair_cover_risers_id:
                        questionnaire["id"] = 8
                        for quote_label in questionnaire.get("quote_label", []):
                            if quote_label.get("question_id") == stair_cover_risers_id:
                                quote_label["question_id"] = 8
            result['questionnaires'] = questionnaires
        else:
            result = message
        return json.dumps(result)

    @route('/api/get_appointments', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def get_appointments(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        if not token:
            _logger.info("------------Token Missing in main get_appointments api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main get_appointments api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main get_appointments api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        # enable_api_queue_system = eval(str(request.env['ir.config_parameter'].sudo().get_param('enable_api_queue_system')))
        enable_api_queue_system = str2bool(request.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_api_queue_system'))
        if status:
            if enable_api_queue_system:
                _logger.info('appointment_sync_api_queue Data - Starting--:%s - User ID: %s' % (
                    self.appointment_sync_api_queue, uid))
                time = datetime.now()
                if uid in self.appointment_sync_api_queue:
                    queue_time = self.appointment_sync_api_queue.get(uid, {})
                    time_difference = (time - queue_time).total_seconds()
                    if int(time_difference) < 20:
                        _logger.info('appointment_sync_api_queue Data - Duplicate--:%s - User ID ID: %s' % (
                            self.appointment_sync_api_queue, uid))
                        result = {'override_json_result': 1, 'result': 'Failed',
                                  'message': 'Execution is already in progress'}
                        return json.dumps(result)
                self.appointment_sync_api_queue.update({
                    uid: time
                })
                _logger.info('appointment_sync_api_queue Data - Added--:%s' % (
                    self.appointment_sync_api_queue))
            appointment_data = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                                 'action_get_appointment_data', [int(uid)])

            if appointment_data.get('result', '') == 'Failed':
                result = appointment_data
            else:
                result = {
                    'result': 'Success',
                    'appointments': appointment_data.get('data', []),
                    'message': '',
                }
        else:
            result = message
        result.update({'override_json_result': 1})
        if enable_api_queue_system and uid:
            self.appointment_sync_api_queue.pop(uid, '')
            _logger.info('appointment_sync_api_queue Data - Ending--:%s' % (
                self.appointment_sync_api_queue))
        return json.dumps(result)

    @route('/api/update_customer_and_room_information', type='json', auth="none", methods=['POST'], csrf=False)
    def update_customer_and_room_information(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', False)
        data = params.get('data', False)
        _logger.info("------------update_customer_and_room_information params: %s------------------" % (params))
        if not token:
            _logger.info("------------Token Missing in main update_customer_and_room_information api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main update_customer_and_room_information api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main update_customer_and_room_information api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            appointment_data = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                                 'action_update_customer_and_room_information', [data])

            result = appointment_data
        else:
            result = message
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/update_customer_and_room_information', data, uid, result)
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/update_contract_information', type='json', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def update_contract_information(self, **kwargs):
        # models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL), allow_none=True)
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', False)
        data = params.get('data', False)
        _logger.info("------------update_contract_information params: %s------------------" % (params))
        if not token:
            _logger.info("------------Token Missing in main update_contract_information api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main update_contract_information api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main update_contract_information api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            payment_data_result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                                    'action_update_contract_information', [data])

            result = payment_data_result
        else:
            result = message
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/update_contract_information', data, uid,
                                                              result)
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/upload_images', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def upload_images(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        appointment_id = params.get('appointment_id', 0) and int(params.get('appointment_id', 0)) or 0
        room_id = params.get('room_id', 0) and int(params.get('room_id', 0)) or 0
        room_name = params.get('room_name', '')
        image_type = params.get('image_type', '')
        image_name = params.get('image_name', '')
        data_completed = params.get('data_completed', 0)
        network_strength = params.get('network_strength', '')
        file = params.get('file', False)
        _logger.info("------------add_screenshots params: %s------------------" % (params))
        data = []
        result = {}
        file_data = {}
        image_id = 0
        image_already_existing = True
        if not token:
            _logger.info("------------Token Missing in add_screenshots------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in add_screenshots-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in add_screenshots-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        # enable_api_queue_system = eval(str(request.env['ir.config_parameter'].sudo().get_param('enable_api_queue_system')))
        enable_api_queue_system = str2bool(request.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_api_queue_system'))
        if status:
            if enable_api_queue_system:
                _logger.info('image_sync_api_queue Data - Starting--:%s - Appointment ID: %s, Image: %s' % (
                    self.image_sync_api_queue, appointment_id, image_name))
                time = datetime.now()
                if appointment_id not in self.image_sync_api_queue:
                    self.image_sync_api_queue.update({
                        appointment_id: {}
                    })
                image_dict = self.image_sync_api_queue.get(appointment_id, {})
                if image_name in image_dict:
                    queue_time = image_dict.get(image_name, {})
                    time_difference = (time - queue_time).total_seconds()
                    if int(time_difference) < 20:
                        _logger.info('image_sync_api_queue Data - Duplicate--:%s - Appointment ID: %s, Image: %s' % (
                            self.image_sync_api_queue, appointment_id, image_name))
                        result = {'override_json_result': 1, 'result': 'Failed',
                                  'message': 'Execution is already in progress'}
                        request.env['otl.api.sync.log'].sudo().create_api_log('/api/upload_images', {'appointment_id': appointment_id}, uid, result, network_strength)
                        return json.dumps(result)
                self.image_sync_api_queue[appointment_id].update({
                    image_name: time
                })
                _logger.info('image_sync_api_queue Data - Added--:%s' % (self.image_sync_api_queue))
            if not file:
                return json.dumps({'result': 'Failed', 'message': 'Empty attachment in values.'})

            if type(file) == werkzeug.datastructures.FileStorage:
                image_binary = (file.read())
                file_data.update({
                    'uid': int(uid),
                    'image': base64.b64encode(image_binary).decode('utf-8'),
                    'file_name': image_name or file.filename,
                    'appointment_id': appointment_id,
                    'image_type': image_type,
                })
                data = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'ir.attachment', 'action_upload_images',
                                         [file_data])
            if data:
                image_id = data[0].get('attachment_id', False)
                image_already_existing = data[0].get('image_already_existing', False)
                if image_already_existing:
                    result = {
                        'message': 'File is already existing',
                        'result': 'Success',
                        'image_name': image_name
                    }
                else:
                    if image_id:
                        image_vals = {
                            'appointment_id': appointment_id,
                            'attachment_id': image_id,
                            'image_type': image_type,
                            'image_name': image_name,
                            'room_id': room_id,
                            'room_name': room_name,
                            'data_completed': data_completed,
                        }
                        result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment', 'action_link_uploaded_image',
                                                   [image_vals])
        else:
            result = message
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/upload_images', {'appointment_id': appointment_id}, uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        if enable_api_queue_system and appointment_id and self.image_sync_api_queue.get(appointment_id, False):
            self.image_sync_api_queue[appointment_id].pop(image_name, {})
            if not self.image_sync_api_queue[appointment_id]:
                self.image_sync_api_queue.pop(appointment_id, '')
            _logger.info('image_sync_api_queue Data - Ending--:%s' % (self.image_sync_api_queue))
        return json.dumps(result)

    @route('/api/generate_contract_document', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def generate_contract_document(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        contract_plumbing_option_1 = params.get('contract_plumbing_option_1', 0) and int(params.get('contract_plumbing_option_1', 0)) or 0
        contract_plumbing_option_2 = params.get('contract_plumbing_option_2', 0) and int(params.get('contract_plumbing_option_2', 0)) or 0
        send_physical_document = params.get('send_physical_document', 0) and int(params.get('send_physical_document', 0)) or 0
        flexible_installation = params.get('flexible_installation', 0) and int(params.get('flexible_installation', 0)) or 0
        recision_date = params.get('recision_date', False)
        additional_comments = params.get('additional_comments', '')
        network_strength = params.get('network_strength', '')
        # if (contract_plumbing_option_1 and contract_plumbing_option_2) or \
        #         (not contract_plumbing_option_1 and not contract_plumbing_option_2):
        #     return json.dumps({
        #         'override_json_result': 1,
        #         'result': 'Failed',
        #         'message': 'Plumbing option should select either one option'
        #     })
        appointment_id = params.get('appointment_id', 0) and str(params.get('appointment_id', 0)) or '0'

        _logger.info("------------generate_contract_document params: %s------------------" % (params))
        result = {}
        if not token:
            _logger.info("------------Token Missing in generate_contract_document------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in generate_contract_document-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in generate_contract_document-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        # enable_api_queue_system = eval(str(request.env['ir.config_parameter'].sudo().get_param('enable_api_queue_system')))
        enable_api_queue_system = str2bool(request.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_api_queue_system'))
        data = {}
        if status:
            data = {
                'appointment_id': int(appointment_id),
                'contract_plumbing_option_1': contract_plumbing_option_1,
                'contract_plumbing_option_2': contract_plumbing_option_2,
                'send_physical_document': send_physical_document,
                'flexible_installation': flexible_installation,
                'additional_comments': additional_comments,
                'recision_date': recision_date
            }
            if enable_api_queue_system:
                _logger.info('generate_contract_document_api_queue Data - Starting--:%s - Appointment ID: %s' % (
                        self.generate_contract_document_api_queue, appointment_id))
                time = datetime.now()
                if appointment_id in self.generate_contract_document_api_queue:
                    queue_time = self.generate_contract_document_api_queue.get(appointment_id, {})
                    time_difference = (time - queue_time).total_seconds()
                    if int(time_difference) < 20:
                        _logger.info('generate_contract_document_api_queue Data - Duplicate--:%s - Appointment ID: %s' % (
                            self.generate_contract_document_api_queue, appointment_id))
                        result = {'override_json_result': 1, 'result': 'Failed',
                                  'message': 'Execution is already in progress'}
                        request.env['otl.api.sync.log'].sudo().create_api_log(
                            '/api/generate_contract_document', data, uid,
                            result, network_strength)
                        return json.dumps(result)
                self.generate_contract_document_api_queue.update({
                    appointment_id: time
                })
                _logger.info('generate_contract_document_api_queue Data - Added--:%s' % (
                    self.generate_contract_document_api_queue))

            result = models.execute_kw(DB, int(uid), password, 'sale.order', 'action_generate_contract_document',
                                       [data])
        else:
            result = message
        if data:
            request.env['otl.api.sync.log'].sudo().create_api_log('/api/generate_contract_document', data, uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        if enable_api_queue_system:
            self.generate_contract_document_api_queue.pop(appointment_id, '')
            _logger.info('generate_contract_document_api_queue Data - Ending--:%s' % (
                self.generate_contract_document_api_queue))
        return json.dumps(result)

    @route('/api/initiate_sync_to_i360', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def initiate_sync_to_i360(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        appointment_id = params.get('appointment_id', 0) and int(params.get('appointment_id', 0)) or 0
        sync_delay = params.get('sync_delay', 1) and int(params.get('sync_delay', 1)) or 1
        network_strength = params.get('network_strength', '')
        result = {}
        if not token:
            _logger.info("------------Token Missing in initiate_sync_to_i360------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in initiate_sync_to_i360-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in initiate_sync_to_i360-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        data = {}
        if status:
            data = {
                'appointment_id': appointment_id,
                'sync_delay': sync_delay,
            }
            result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                       'action_initiate_sync_to_i360',
                                       [data])
        else:
            result = message
            
        if data:
            request.env['otl.api.sync.log'].sudo().create_api_log('/api/initiate_sync_to_i360', data, uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/initiate_sync_to_i360_json', type='json', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def initiate_sync_to_i360_json(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', '')
        data = params.get('data', [])
        appointment_id = False
        network_strength = params.get('network_strength', '')
        result = {}
        if not token:
            _logger.info("------------Token Missing in initiate_sync_to_i360_json------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in initiate_sync_to_i360_json-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in initiate_sync_to_i360_json-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        # enable_api_queue_system = eval(str(request.env['ir.config_parameter'].sudo().get_param('enable_api_queue_system')))
        enable_api_queue_system = str2bool(request.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_api_queue_system'))
        if status:
            if enable_api_queue_system:
                if data.get('appointment_id', 0):
                    _logger.info('initiate_i360_sync_api_queue Data - Starting--:%s - Appointment ID: %s' % (
                        self.initiate_i360_sync_api_queue, data.get('appointment_id', 0)))
                    appointment_id = data.get('appointment_id', 0) and str(data.get('appointment_id', 0)) or '0'
                    time = datetime.now()
                    if appointment_id in self.initiate_i360_sync_api_queue:
                        queue_time = self.initiate_i360_sync_api_queue.get(appointment_id, {})
                        time_difference = (time - queue_time).total_seconds()
                        if int(time_difference) < 20:
                            _logger.info('initiate_i360_sync_api_queue Data - Duplicate--:%s - Appointment ID: %s' % (
                                self.initiate_i360_sync_api_queue, data.get('appointment_id', 0)))
                            result = {'override_json_result': 1, 'result': 'Failed',
                                      'message': 'Execution is already in progress'}
                            request.env['otl.api.sync.log'].sudo().create_api_log(
                                '/api/initiate_sync_to_i360_json', data, uid,
                                result, network_strength)
                            return json.dumps(result)
                    self.initiate_i360_sync_api_queue.update({
                        appointment_id: time
                    })
                    _logger.info('initiate_i360_sync_api_queue Data - Added--:%s' % (
                        self.initiate_i360_sync_api_queue))
                else:
                    _logger.info(
                        "------------Appointment ID missing in create_order_and_update_measurements_encoded api-------------------")
                    return json.dumps(
                        {'override_json_result': 1, 'result': 'Failed', 'message': 'Appointment ID is missing'})
            result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                       'action_initiate_sync_to_i360',
                                       [data])
        else:
            result = message
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/initiate_sync_to_i360_json', data, uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        if enable_api_queue_system and appointment_id:
            self.initiate_i360_sync_api_queue.pop(appointment_id, '')
            _logger.info('initiate_i360_sync_api_queue Data - Ending--:%s' % (
                self.initiate_i360_sync_api_queue))
        return json.dumps(result)

    @route('/api/update_sync_log', type='json', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def update_sync_log(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', '')
        data = params.get('data', [])
        if not token:
            _logger.info("------------Token Missing in update_sync_log------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in update_sync_log-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in update_sync_log-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                       'action_update_sync_log',
                                       [data])
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/create_order_and_update_measurements', type='json', auth="none", methods=['POST'], csrf=False)
    def create_order_and_update_measurements(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', False)
        data = params.get('data', False)
        _logger.info("------------create_order_and_update_measurements params: %s------------------" % (params))
        if not token:
            _logger.info("------------Token Missing in main update_contract_information api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main create_order_and_update_measurements api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main create_order_and_update_measurements api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            payment_data_result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                                    'action_create_order_and_update_measurements', [data])

            result = payment_data_result
        else:
            result = message
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/create_order_and_update_measurements', data, uid,
                                                              result)
        result.update({'override_json_result': 1})
        return json.dumps(result)

    def action_extract_jwt_token(self, auth_token , jwt_token, decode_options):
        """
        Function to decode the data passed in the API
        :param auth_token:
        :param jwt_token:
        :param decode_options:
        :return:
        """
        values = {}
        try:
            token_decode = JWT_DECODE(jwt_token, auth_token, algorithms=[JWT_ALGORITHM], options=decode_options)
            token_decode = token_decode.decode("utf-8")
            values = ast.literal_eval(token_decode)
        except:
            token_decode = ''
        return values

    @route('/api/create_order_and_update_measurements_encoded', type='json', auth="none", methods=['POST'], csrf=False)
    def create_order_and_update_measurements_encoded(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', False)
        data = params.get('data', False)
        network_strength = params.get('network_strength', '')
        appointment_id = False
        _logger.info("------------create_order_and_update_measurements_encoded params - 1st: %s------------------" % (params))
        while 'data' in data:
            data = data.get('data', {})
        _logger.info("------------create_order_and_update_measurements_encoded params- 2nd: %s------------------" % (params))
        decode_options = ast.literal_eval(str(params.get('decode_options', {'verify_signature': True})))
        if not token:
            _logger.info("------------Token Missing in main create_order_and_update_measurements_encoded api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main create_order_and_update_measurements_encoded api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main create_order_and_update_measurements_encoded api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            stair_width_data = models.execute_kw(DB, int(uid), password, 'res.users', 'get_stair_width_id', [{}])
            get_stair_cover_risers_data = models.execute_kw(DB, int(uid), password, 'res.users', 'get_stair_cover_risers', [{}])
            # Handle application issue with static room id 9 
            # Fix question_id 9 to 42 in answer list if present
            if data and "answer" in data and isinstance(data["answer"], list) and (
                (stair_width_data and stair_width_data.get('stair_width_id', False)) or 
                (get_stair_cover_risers_data and get_stair_cover_risers_data.get('stair_cover_risers', False))):
                update_answer = []
                for ans in data["answer"]:
                    updated_question_id = False
                    if isinstance(ans, dict) and ans.get("question_id") == 9:
                        updated_question_id = stair_width_data.get('stair_width_id', False)
                    elif isinstance(ans, dict) and ans.get("question_id") == 8:
                        updated_question_id = get_stair_cover_risers_data.get('stair_cover_risers', False)
                    if updated_question_id:
                        ans["question_id"] = updated_question_id
                    update_answer.append(ans)
                data["answer"] = update_answer
        decoded_data = data
        # enable_api_queue_system = eval(str(request.env['ir.config_parameter'].sudo().get_param('enable_api_queue_system')))
        enable_api_queue_system = str2bool(request.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_api_queue_system'))
        if status:
            if enable_api_queue_system:
                if data.get('appointment_id', 0):
                    _logger.info('create_order_and_update_measurements_api_queue Data - Starting--:%s - Appointment ID: %s' % (
                        self.create_order_and_update_measurements_api_queue, data.get('appointment_id', 0)))
                    appointment_id = data.get('appointment_id', 0) and str(data.get('appointment_id', 0)) or '0'
                    time = datetime.now()
                    if appointment_id in self.create_order_and_update_measurements_api_queue:
                        queue_time = self.create_order_and_update_measurements_api_queue.get(appointment_id, {})
                        time_difference = (time - queue_time).total_seconds()
                        if int(time_difference) < 20:
                            _logger.info(
                                'create_order_and_update_measurements_api_queue Data - Duplicate--:%s - Appointment ID: %s' % (
                                    self.create_order_and_update_measurements_api_queue, data.get('appointment_id', 0)))
                            result = {'override_json_result': 1, 'result': 'Failed',
                                      'message': 'Execution is already in progress'}
                            request.env['otl.api.sync.log'].sudo().create_api_log(
                                '/api/create_order_and_update_measurements_encoded', data, uid,
                                result, network_strength)
                            return json.dumps(result)
                    self.create_order_and_update_measurements_api_queue.update({
                        appointment_id: time
                    })
                    _logger.info('create_order_and_update_measurements_api_queue Data - Added--:%s' % (
                        self.create_order_and_update_measurements_api_queue))
                else:
                    _logger.info(
                        "------------Appointment ID missing in create_order_and_update_measurements_encoded api-------------------")
                    return json.dumps(
                        {'override_json_result': 1, 'result': 'Failed', 'message': 'Appointment ID is missing'})
            payment_method_secret = data.get('payment_method_secret', '')
            credit_application_secret = data.get('application_info_secret', '')
            try:
                if payment_method_secret:
                    payment_method_dict = self.action_extract_jwt_token(token, payment_method_secret, decode_options)
                    if payment_method_dict:
                        decoded_data.update({
                            'paymentmethod': payment_method_dict
                        })
            except:
                result = {'override_json_result': 1, 'result': 'Failed', 'message': 'Something went wrong while decoding the payment token'}
                request.env['otl.api.sync.log'].sudo().create_api_log(
                    '/api/create_order_and_update_measurements_encoded', data, uid,
                    result, network_strength)
                if enable_api_queue_system:
                    self.create_order_and_update_measurements_api_queue.pop(appointment_id, '')
                return json.dumps(result)
            try:
                if credit_application_secret:
                    credit_application_dict = self.action_extract_jwt_token(token, credit_application_secret, decode_options)
                    if credit_application_dict:
                        decoded_data.update({
                            'applicationInfo': credit_application_dict
                        })
            except:
                result = {'override_json_result': 1, 'result': 'Failed', 'message': 'Something went wrong while decoding the credit application token'}
                request.env['otl.api.sync.log'].sudo().create_api_log(
                    '/api/create_order_and_update_measurements_encoded', data, uid,
                    result, network_strength)
                if enable_api_queue_system:
                    self.create_order_and_update_measurements_api_queue.pop(appointment_id, '')
                return json.dumps(result)
            if decoded_data:
                def remove_none_values(data):
                    """Recursively remove None values from dictionaries and lists."""
                    if isinstance(data, dict):
                        return {k: remove_none_values(v) for k, v in data.items() if v is not None}
                    elif isinstance(data, list):
                        return [remove_none_values(v) for v in data if v is not None]
                    else:
                        return data
                decoded_data = remove_none_values(decoded_data)
                payment_data_result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                                     'action_create_order_and_update_measurements', [decoded_data])
            else:
                return json.dumps({'override_json_result': 1, 'result': 'Failed',
                                   'message': 'Empty values in decoded data'})

            result = payment_data_result
        else:
            result = message
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/create_order_and_update_measurements_encoded', data, uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        if enable_api_queue_system:
            if appointment_id:
                self.create_order_and_update_measurements_api_queue.pop(appointment_id, '')
            _logger.info('create_order_and_update_measurements_api_queue Data - Ending--:%s'%(self.create_order_and_update_measurements_api_queue))
        return json.dumps(result)

    @route('/api/create_order_and_update_measurements_encoded_v2', type='json', auth="none", methods=['POST'], csrf=False)
    def create_order_and_update_measurements_encoded_v2(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', False)
        data = params.get('data', False)
        native_data = params.get('native_data', False)
        network_strength = params.get('network_strength', '')
        decode_options = ast.literal_eval(str(params.get('decode_options', {'verify_signature': True})))
        decoded_data = {}
        _logger.info("------------create_order_and_update_measurements_encoded_v2 params: %s------------------" % (params))
        if not token:
            _logger.info("------------Token Missing in main create_order_and_update_measurements_encoded_v2 api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main create_order_and_update_measurements_encoded_v2 api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main create_order_and_update_measurements_encoded_v2 api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            if data:
                try:
                    decoded_data = self.action_extract_jwt_token(token, data, decode_options)
                except:
                    return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Something went wrong while decoding the data token'})
            else:
                # decoded_data = json.loads(native_data)
                decoded_data = native_data
            if decoded_data:
                payment_data_result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                                     'action_create_order_and_update_measurements', [decoded_data])
            else:
                return json.dumps({'override_json_result': 1, 'result': 'Failed',
                                   'message': 'Empty values in decoded data'})

            result = payment_data_result
        else:
            result = message
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/create_order_and_update_measurements_encoded_v2', decoded_data, uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/fetch_database_raw_data', type='json', auth="none", methods=['POST'], csrf=False)
    def action_fetch_database_raw_data(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', False)
        data = params.get('data', False)
        appointment_id = int(params.get('appointment_id', 0))
        network_strength = params.get('network_strength', '')
        _logger.info(
            "------------fetch_database_raw_data params: %s------------------" % (params))
        if not token:
            _logger.info("------------Token Missing in main fetch_database_raw_data api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main fetch_database_raw_data api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main fetch_database_raw_data api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            if data and appointment_id:
                result = request.env['otl.api.sync.log'].sudo().store_database_raw_data('/api/fetch_database_raw_data', data, uid, appointment_id, network_strength)
            else:
                result = {'result': 'Failed', 'message': 'Data or Appointment ID is missing'}
        else:
            result = message
        result.update({'override_json_result': 1})
        _logger.info("fetch_database_raw_data Response: %s"%(result))
        return json.dumps(result)

    @route('/api/check_auto_logout', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def check_auto_logout(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        _logger.info(
            "------------check_auto_logout params: %s------------------" % (params))
        if not token:
            _logger.info("------------Token Missing in main check_auto_logout api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main check_auto_logout api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main check_auto_logout api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'res.users', 'action_check_auto_logout', [])
        else:
            result = message
        result.update({'override_json_result': 1})
        _logger.info("check_auto_logout Response: %s"%(result))
        return json.dumps(result)

    @route('/api/get_available_installation_date', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def action_get_available_installation_date(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        appointment_id = params.get('appointment_id', '')
        network_strength = params.get('network_strength', '')
        _logger.info(
            "------------action_get_available_installation_date params: %s------------------" % (params))
        if not token:
            _logger.info("------------Token Missing in main action_get_available_installation_date api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        if not appointment_id:
            _logger.info("------------Appointment ID Missing in main action_get_available_installation_date api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty Appointment ID.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main action_get_available_installation_date api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main action_get_available_installation_date api-------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        # enable_api_queue_system = eval(str(request.env['ir.config_parameter'].sudo().get_param('enable_api_queue_system')))
        enable_api_queue_system = str2bool(request.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_api_queue_system'))
        if status:
            if enable_api_queue_system:
                _logger.info('available_installation_date_api_queue Data - Starting--:%s - Appointment ID: %s' % (
                    self.available_installation_date_api_queue, appointment_id))
                time = datetime.now()
                if appointment_id in self.available_installation_date_api_queue:
                    queue_time = self.available_installation_date_api_queue.get(appointment_id, {})
                    time_difference = (time - queue_time).total_seconds()
                    if int(time_difference) < 20:
                        _logger.info(
                            'available_installation_date_api_queue Data - Duplicate--:%s - Appointment ID: %s' % (
                                self.available_installation_date_api_queue, appointment_id))
                        result = {'override_json_result': 1, 'result': 'Failed',
                                  'message': 'Execution is already in progress'}
                        request.env['otl.api.sync.log'].sudo().create_api_log(
                            '/api/get_available_installation_date', params, uid,
                            result, network_strength)
                        return json.dumps(result)
                self.available_installation_date_api_queue.update({
                    appointment_id: time
                })
                _logger.info('available_installation_date_api_queue Data - Added--:%s' % (
                    self.available_installation_date_api_queue))
            result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment', 'action_get_available_installation_date', [{'appointment_id': appointment_id}])
        else:
            result = message
        _logger.info("---------action_get_available_installation_date Response: %s"%(result))
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/get_available_installation_date', params,
                                                              uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        if enable_api_queue_system:
            self.available_installation_date_api_queue.pop(appointment_id, '')
            _logger.info('------available_installation_date_api_queue Data - Ending--:%s' % (
                self.available_installation_date_api_queue))
        return json.dumps(result)

    @route('/api/submit_selected_installation_date', type='http', auth="none", methods=['POST'], csrf=False,
           allow_none=True, )
    def action_submit_selected_installation_date(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        sale_order_id = params.get('sale_order_id', '')
        installation_id = params.get('installation_id', '')
        network_strength = params.get('network_strength', '')
        _logger.info(
            "------------submit_selected_installation_date params: %s------------------" % (params))
        if not token:
            _logger.info("------------Token Missing in main submit_selected_installation_date api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        if not sale_order_id:
            _logger.info(
                "------------Sale Order ID Missing in main submit_selected_installation_date api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty Sale Order ID.'})
        if not installation_id:
            _logger.info(
                "------------Selected Installation Date ID Missing in main submit_selected_installation_date api------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Empty Selected Installation Date ID.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main submit_selected_installation_date api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info(
                "------------password missing in main submit_selected_installation_date api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        # enable_api_queue_system = eval(str(request.env['ir.config_parameter'].sudo().get_param('enable_api_queue_system')))
        enable_api_queue_system = str2bool(request.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_api_queue_system'))
        if status:
            if enable_api_queue_system:
                _logger.info('selected_installation_date_api_queue Data - Starting--:%s - Appointment ID: %s' % (
                    self.selected_installation_date_api_queue, sale_order_id))
                time = datetime.now()
                if sale_order_id in self.selected_installation_date_api_queue:
                    queue_time = self.selected_installation_date_api_queue.get(sale_order_id, {})
                    time_difference = (time - queue_time).total_seconds()
                    if int(time_difference) < 20:
                        _logger.info(
                            'selected_installation_date_api_queue Data - Duplicate--:%s - Appointment ID: %s' % (
                                self.selected_installation_date_api_queue, sale_order_id))
                        result = {'override_json_result': 1, 'result': 'Failed',
                                  'message': 'Execution is already in progress'}
                        request.env['otl.api.sync.log'].sudo().create_api_log(
                            '/api/get_available_installation_date', params, uid,
                            result, network_strength)
                        return json.dumps(result)
                self.selected_installation_date_api_queue.update({
                    sale_order_id: time
                })
                _logger.info('selected_installation_date_api_queue Data - Added--:%s' % (
                    self.selected_installation_date_api_queue))
            result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                       'action_submit_selected_installation_date',
                                       [{'sale_order_id': sale_order_id, 'installation_id': installation_id}])
        else:
            result = message
        _logger.info("---------submit_selected_installation_date Response: %s" % (result))
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/submit_selected_installation_date', params,
                                                              uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        if enable_api_queue_system:
            self.selected_installation_date_api_queue.pop(sale_order_id, '')
            _logger.info('------selected_installation_date_api_queue Data - Ending--:%s' % (
                self.selected_installation_date_api_queue))
        return json.dumps(result)

    @route('/api/<version>/create_versatile_credit_application', type='json', auth="none", methods=['POST'], csrf=False,
           allow_none=True, )
    def action_create_versatile_credit_application(self, version='v1', **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL), allow_none=True)
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = ''
        access_token = request.httprequest.headers.get('Authorization')
        if not access_token:
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Access Token is missing'})
        if access_token.startswith('Bearer '):
            token = access_token[7:]
        data = params
        _logger.info(
            "------------create_versatile_credit_application params: %s------------------" % (params))
        if not token:
            _logger.info("------------Token Missing in main create_versatile_credit_application api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token is not existing'})
        if not data:
            _logger.info("------------Data Missing in main create_versatile_credit_application api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Data is not existing'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main create_versatile_credit_application api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info(
                "------------password missing in main create_versatile_credit_application api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            if version == 'v1':
                result = models.execute_kw(DB, int(uid), password, 'otl.versatile.credit.application',
                                           'action_create_versatile_credit_application',
                                           [data])
            else:
                result= {'override_json_result': 1, 'result': 'Failed', 'message': 'Invalid Version'}
        else:
            result = message
        _logger.info("---------create_versatile_credit_application Response: %s" % (result))
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/<version>/update_additional_appointment_data', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def action_update_additional_appointment_data(self, version='v1', **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        flexible_installation = params.get('flexible_installation', 0) and int(params.get('flexible_installation', 0)) or 0
        send_physical_document = params.get('send_physical_document', 0) and int(
            params.get('send_physical_document', 0)) or 0
        additional_comments = params.get('additional_comments', '')
        appointment_id = params.get('appointment_id', 0) and str(params.get('appointment_id', 0)) or '0'
        recision_date = params.get('recision_date', False)
        network_strength = params.get('network_strength', '')

        _logger.info("------------update_additional_appointment_data params: %s------------------" % (params))
        result = {}
        if not token:
            _logger.info("------------Token Missing in update_additional_appointment_data------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in update_additional_appointment_data-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in update_additional_appointment_data-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        # enable_api_queue_system = eval(str(request.env['ir.config_parameter'].sudo().get_param('enable_api_queue_system')))
        enable_api_queue_system = str2bool(request.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_api_queue_system'))
        if status:
            if version == 'v1':
                data = {
                    'appointment_id': int(appointment_id),
                    'send_physical_document': send_physical_document,
                    'flexible_installation': flexible_installation,
                    'additional_comments': additional_comments,
                    'recision_date': recision_date
                }
                if enable_api_queue_system:
                    _logger.info('update_additional_appointment_data_api_queue Data - Starting--:%s - Appointment ID: %s' % (
                            self.update_additional_appointment_data_api_queue, appointment_id))
                    time = datetime.now()
                    if appointment_id in self.update_additional_appointment_data_api_queue:
                        queue_time = self.update_additional_appointment_data_api_queue.get(appointment_id, {})
                        time_difference = (time - queue_time).total_seconds()
                        if int(time_difference) < 20:
                            _logger.info('update_additional_appointment_data_api_queue Data - Duplicate--:%s - Appointment ID: %s' % (
                                self.update_additional_appointment_data_api_queue, appointment_id))
                            result = {'override_json_result': 1, 'result': 'Failed',
                                      'message': 'Execution is already in progress'}
                            request.env['otl.api.sync.log'].sudo().create_api_log(
                                '/api/%s/update_additional_appointment_data'%(version), data, uid,
                                result, network_strength)
                            return json.dumps(result)
                    self.update_additional_appointment_data_api_queue.update({
                        appointment_id: time
                    })
                    _logger.info('update_additional_appointment_data_api_queue Data - Added--:%s' % (
                        self.update_additional_appointment_data_api_queue))

                result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment', 'action_update_additional_appointment_data',
                                           [data])
            else:
                result= {'override_json_result': 1, 'result': 'Failed', 'message': 'Invalid Version'}
        else:
            result = message
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/%s/update_additional_appointment_data'%(version), params, uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        if enable_api_queue_system:
            self.update_additional_appointment_data_api_queue.pop(appointment_id, '')
            _logger.info('update_additional_appointment_data_api_queue Data - Ending--:%s' % (
                self.update_additional_appointment_data_api_queue))
        return json.dumps(result)

    @route('/api/<version>/get_credit_application_status', type='json', auth="none", methods=['POST'], csrf=False,
           allow_none=True, )
    def action_get_credit_application_status(self, version='v1', **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL), allow_none=True)
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = ''
        access_token = request.httprequest.headers.get('Authorization')
        if not access_token:
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Access Token is missing'})
        if access_token.startswith('Bearer '):
            token = access_token[7:]
        data = params
        appointment_id = params.get('appointment_id', 0) and str(params.get('appointment_id', 0)) or '0'
        network_strength = params.get('network_strength', '')
        _logger.info(
            "------------get_credit_application_status params: %s------------------" % (params))
        if not token:
            _logger.info("------------Token Missing in get_credit_application_status api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token is not existing'})
        if not data:
            _logger.info("------------Data Missing in get_credit_application_status api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Data is not existing'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in get_credit_application_status api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info(
                "------------password missing in get_credit_application_status api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        # enable_api_queue_system = eval(str(request.env['ir.config_parameter'].sudo().get_param('enable_api_queue_system')))
        enable_api_queue_system = str2bool(request.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_api_queue_system'))
        if status:
            if version == 'v1':
                if enable_api_queue_system:
                    _logger.info('get_credit_application_status_api_queue Data - Starting--:%s - Appointment ID: %s' % (
                            self.get_credit_application_status_api_queue, appointment_id))
                    time = datetime.now()
                    if appointment_id in self.get_credit_application_status_api_queue:
                        queue_time = self.get_credit_application_status_api_queue.get(appointment_id, {})
                        time_difference = (time - queue_time).total_seconds()
                        if int(time_difference) < 20:
                            _logger.info('get_credit_application_status_api_queue Data - Duplicate--:%s - Appointment ID: %s' % (
                                self.get_credit_application_status_api_queue, appointment_id))
                            result = {'override_json_result': 1, 'result': 'Failed',
                                      'message': 'Execution is already in progress'}
                            request.env['otl.api.sync.log'].sudo().create_api_log(
                                '/api/%s/update_additional_appointment_data'%(version), data, uid,
                                result, network_strength)
                            return json.dumps(result)
                    self.get_credit_application_status_api_queue.update({
                        appointment_id: time
                    })
                    _logger.info('get_credit_application_status_api_queue Data - Added--:%s' % (
                        self.get_credit_application_status_api_queue))
                result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                           'action_get_credit_application_status',
                                           [data])
            else:
                result = {'override_json_result': 1, 'result': 'Failed', 'message': 'Invalid Version'}
        else:
            result = message
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/%s/get_credit_application_status' % (version),
                                                              params, uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        if enable_api_queue_system:
            self.get_credit_application_status_api_queue.pop(appointment_id, '')
            _logger.info('get_credit_application_status_api_queue Data - Ending--:%s' % (
                self.get_credit_application_status_api_queue))
        return json.dumps(result)

    @route('/api/<version>/update_arrival_departure_time', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def action_update_arrival_departure_time(self, version='v1', **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        appointment_id = params.get('appointment_id', 0) and str(params.get('appointment_id', 0)) or '0'
        arrival_date = params.get('arrival_date', False)
        departure_date = params.get('departure_date', False)
        timezone = params.get('timezone', False)
        network_strength = params.get('network_strength', '')

        _logger.info("------------update_arrival_departure_time params: %s------------------" % (params))
        result = {}
        if not token:
            _logger.info("------------Token Missing in update_arrival_departure_time------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in update_arrival_departure_time-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in update_arrival_departure_time-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        # enable_api_queue_system = eval(str(request.env['ir.config_parameter'].sudo().get_param('enable_api_queue_system')))
        enable_api_queue_system = str2bool(request.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_api_queue_system'))
        if status:
            if version == 'v1':
                data = {
                    'appointment_id': int(appointment_id),
                    'arrival_date': arrival_date,
                    'departure_date': departure_date,
                    'timezone': timezone
                }
                if enable_api_queue_system:
                    _logger.info('update_arrival_departure_time_api_queue Data - Starting--:%s - Appointment ID: %s' % (
                            self.update_arrival_departure_time_api_queue, appointment_id))
                    time = datetime.now()
                    if appointment_id in self.update_arrival_departure_time_api_queue:
                        queue_time = self.update_arrival_departure_time_api_queue.get(appointment_id, {})
                        time_difference = (time - queue_time).total_seconds()
                        if int(time_difference) < 20:
                            _logger.info('update_arrival_departure_time_api_queue Data - Duplicate--:%s - Appointment ID: %s' % (
                                self.update_arrival_departure_time_api_queue, appointment_id))
                            result = {'override_json_result': 1, 'result': 'Failed',
                                      'message': 'Execution is already in progress'}
                            request.env['otl.api.sync.log'].sudo().create_api_log(
                                '/api/%s/update_arrival_departure_time'%(version), data, uid,
                                result, network_strength)
                            return json.dumps(result)
                    self.update_arrival_departure_time_api_queue.update({
                        appointment_id: time
                    })
                    _logger.info('update_arrival_departure_time_api_queue Data - Added--:%s' % (
                        self.update_arrival_departure_time_api_queue))

                result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment', 'action_update_arrival_departure_time',
                                           [data])
            else:
                result= {'override_json_result': 1, 'result': 'Failed', 'message': 'Invalid Version'}
        else:
            result = message
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/%s/update_arrival_departure_time'%(version), params, uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        if enable_api_queue_system:
            self.update_arrival_departure_time_api_queue.pop(appointment_id, '')
            _logger.info('update_arrival_departure_time_api_queue Data - Ending--:%s' % (
                self.update_arrival_departure_time_api_queue))
        return json.dumps(result)

    @route('/api/<version>/get_appointment_sync_status', type='http', auth="none", methods=['GET'], csrf=False,
           allow_none=True, )
    def get_appointment_sync_status(self, version='v1', **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL), allow_none=True)
        token = ''
        access_token = request.httprequest.headers.get('Authorization')
        if not access_token:
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Access Token is missing'})
        if access_token.startswith('Bearer '):
            token = access_token[7:]
        if not token:
            _logger.info("------------Token Missing in get_appointment_sync_status api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Token is not existing'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in get_appointment_sync_status api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info(
                "------------password missing in get_appointment_sync_status api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            if version == 'v1':
                result = models.execute_kw(DB, int(uid), password, 'res.users', 'action_get_appointment_sync_status', [int(uid)])
                _logger.info('-----get_appointment_sync_status: Result: %s'%(result))
            else:
                result = {'override_json_result': 1, 'result': 'Failed', 'message': 'Invalid Version'}
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/<version>/upload_compressed_files', type='http', auth="none", methods=['POST'], csrf=False,
           allow_none=True, )
    def upload_compressed_files_api(self,version='v1', **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = ''
        access_token = request.httprequest.headers.get('Authorization')
        if not access_token:
            _logger.error("upload_compressed_files - Empty access_token")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Access Token is missing'})
        if access_token.startswith('Bearer '):
            token = access_token[7:]
        file_data = {}
        appointment_id = params.get('appointment_id', 0) and int(params.get('appointment_id', 0)) or 0
        file = params.get('file', False)
        if not token:
            _logger.error("upload_compressed_files - Empty Token")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.error("upload_compressed_files - Empty uid")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.error("upload_compressed_files - Empty password")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if not file:
            _logger.error("upload_compressed_files - Empty file")
            return json.dumps({'result': 'Failed', 'message': 'Empty attachment in values.'})
        if version == 'v1':

            if type(file) == werkzeug.datastructures.FileStorage:
                image_binary = (file.read())
                file_data.update({
                    'image': base64.b64encode(image_binary).decode('utf-8'),
                    'file_name': file.filename,
                    'appointment_id': appointment_id
                })
                data = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'ir.attachment', 'upload_compressed_files',
                                         [file_data])

                if data:
                    _logger.info(f"upload_compressed_files - Compressed attachment uploaded.")
                    return json.dumps({'result': 'Success', 'message': 'Compressed attachment uploaded.', 'values': data})
                else:
                    _logger.error(f"upload_compressed_files - Failed while uploading compressed Attachment.")
                    return json.dumps({'result': 'Failed', 'message': 'Failed while uploading compressed Attachment.'})
            else:
                _logger.error(f"upload_compressed_files - File type must be werkzeug.datastructures.FileStorage type.")
                return json.dumps(
                    {'result': 'Failed', 'message': 'File type must be werkzeug.datastructures.FileStorage type.'})
        else :
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Invalid Version'})

    @route('/api/<version>/update_manual_arrival_date', type='http', auth="none", methods=['POST'], csrf=False,
           allow_none=True, )
    def action_update_manual_arrival_date(self, version='v1', **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        appointment_id = params.get('appointment_id', 0) and str(params.get('appointment_id', 0)) or '0'
        manual_arrival_date = params.get('manual_arrival_date', False)
        timezone = params.get('timezone', False)
        network_strength = params.get('network_strength', '')

        _logger.info("------------update_manual_arrival_date params: %s------------------" % params)
        result = {}
        if not token:
            _logger.info("------------Token Missing in update_manual_arrival_date------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in update_manual_arrival_date-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in update_manual_arrival_date-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        # enable_api_queue_system = eval(
        #     str(request.env['ir.config_parameter'].sudo().get_param('enable_api_queue_system')))
        enable_api_queue_system = str2bool(request.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_api_queue_system'))
        if status:
            if version == 'v1':
                data = {
                    'appointment_id': int(appointment_id),
                    'manual_arrival_date': manual_arrival_date,
                    'timezone': timezone
                }
                if enable_api_queue_system:
                    _logger.info('update_manual_arrival_date_api_queue Data - Starting--:%s - Appointment ID: %s' % (
                        self.update_manual_arrival_date_api_queue, appointment_id))
                    time = datetime.now()
                    if appointment_id in self.update_manual_arrival_date_api_queue:
                        queue_time = self.update_manual_arrival_date_api_queue.get(appointment_id, {})
                        time_difference = (time - queue_time).total_seconds()
                        if int(time_difference) < 20:
                            _logger.info(
                                'update_manual_arrival_date_api_queue Data - Duplicate--:%s - Appointment ID: %s' % (
                                    self.update_manual_arrival_date_api_queue, appointment_id))
                            result = {'override_json_result': 1, 'result': 'Failed',
                                      'message': 'Execution is already in progress'}
                            request.env['otl.api.sync.log'].sudo().create_api_log(
                                '/api/%s/update_manual_arrival_date' % (version), data, uid,
                                result, network_strength)
                            return json.dumps(result)
                    self.update_manual_arrival_date_api_queue.update({
                        appointment_id: time
                    })
                    _logger.info('update_manual_arrival_date_api_queue Data - Added--:%s' % (
                        self.update_manual_arrival_date_api_queue))

                result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                           'action_update_manual_arrival_date',
                                           [data])
            else:
                result = {'override_json_result': 1, 'result': 'Failed', 'message': 'Invalid Version'}
        else:
            result = message
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/%s/update_manual_arrival_date' % (version),
                                                              params, uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        if enable_api_queue_system:
            self.update_manual_arrival_date_api_queue.pop(appointment_id, '')
            _logger.info('update_manual_arrival_date_api_queue Data - Ending--:%s' % (
                self.update_manual_arrival_date_api_queue))
        return json.dumps(result)

    @route('/api/<version>/send_review_link', type='http', auth="none", methods=['POST'], csrf=False,
           allow_none=True, )
    def action_send_review_link(self, version='v1', **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = ''
        access_token = request.httprequest.headers.get('Authorization')
        if not access_token:
            _logger.error("send_review_link - Empty access_token")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Access Token is missing'})
        if access_token.startswith('Bearer '):
            token = access_token[7:]
        appointment_id = params.get('appointment_id', 0) and str(params.get('appointment_id', 0)) or '0'
        phone = params.get('phone', False)
        network_strength = params.get('network_strength', '')

        _logger.info("------------send_review_link params: %s------------------" % params)
        result = {}
        if not token:
            _logger.info("------------Token Missing in send_review_link------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in send_review_link-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in send_review_link-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        # enable_api_queue_system = eval(
        #     str(request.env['ir.config_parameter'].sudo().get_param('enable_api_queue_system')))
        enable_api_queue_system = str2bool(request.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_api_queue_system'))
        if status:
            if version == 'v1':
                data = {
                    'appointment_id': int(appointment_id),
                    'phone': phone,
                }
                if enable_api_queue_system:
                    _logger.info('send_review_link_api_queue Data - Starting--:%s - Appointment ID: %s' % (
                        self.send_review_link_api_queue, appointment_id))
                    time = datetime.now()
                    if appointment_id in self.send_review_link_api_queue:
                        queue_time = self.send_review_link_api_queue.get(appointment_id, {})
                        time_difference = (time - queue_time).total_seconds()
                        if int(time_difference) < 20:
                            _logger.info(
                                'send_review_link_api_queue Data - Duplicate--:%s - Appointment ID: %s' % (
                                    self.send_review_link_api_queue, appointment_id))
                            result = {'override_json_result': 1, 'result': 'Failed',
                                      'message': 'Execution is already in progress'}
                            request.env['otl.api.sync.log'].sudo().create_api_log(
                                '/api/%s/send_review_link' % (version), data, uid,
                                result, network_strength)
                            return json.dumps(result)
                    self.send_review_link_api_queue.update({
                        appointment_id: time
                    })
                    _logger.info('send_review_link_api_queue Data - Added--:%s' % (
                        self.send_review_link_api_queue))

                result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                           'action_send_review_link',
                                           [data])
            else:
                result = {'override_json_result': 1, 'result': 'Failed', 'message': 'Invalid Version'}
        else:
            result = message
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/%s/send_review_link' % (version),
                                                              params, uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        if enable_api_queue_system:
            self.send_review_link_api_queue.pop(appointment_id, '')
            _logger.info('send_review_link_api_queue Data - Ending--:%s' % (
                self.send_review_link_api_queue))
        return json.dumps(result)

    @route('/api/<version>/get_appointment_current_status', type='http', auth="none", methods=['POST'], csrf=False,
           allow_none=True, )
    def action_get_appointment_current_status(self, version='v1', **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = ''
        access_token = request.httprequest.headers.get('Authorization')
        if not access_token:
            _logger.error("get_appointment_current_status - Empty access_token")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Access Token is missing'})
        if access_token.startswith('Bearer '):
            token = access_token[7:]
        appointment_id = params.get('appointment_id', 0) and str(params.get('appointment_id', 0)) or '0'
        network_strength = params.get('network_strength', '')

        _logger.info("------------get_appointment_current_status params: %s------------------" % params)
        result = {}
        if not token:
            _logger.info("------------Token Missing in get_appointment_current_status------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in get_appointment_current_status-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in get_appointment_current_status-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        # enable_api_queue_system = eval(
        #     str(request.env['ir.config_parameter'].sudo().get_param('enable_api_queue_system')))
        enable_api_queue_system = str2bool(request.env['ir.config_parameter'].sudo().get_param('team_sale_contract.enable_api_queue_system'))
        if status:
            if version == 'v1':
                data = {
                    'appointment_id': int(appointment_id),
                    'user_id': int(uid)
                }
                if enable_api_queue_system:
                    _logger.info('get_appointment_current_status_api_queue Data - Starting--:%s - Appointment ID: %s' % (
                        self.get_appointment_current_status_api_queue, appointment_id))
                    time = datetime.now()
                    if appointment_id in self.get_appointment_current_status_api_queue:
                        queue_time = self.get_appointment_current_status_api_queue.get(appointment_id, {})
                        time_difference = (time - queue_time).total_seconds()
                        if int(time_difference) < 20:
                            _logger.info(
                                'get_appointment_current_status_api_queue Data - Duplicate--:%s - Appointment ID: %s' % (
                                    self.get_appointment_current_status_api_queue, appointment_id))
                            result = {'override_json_result': 1, 'result': 'Failed',
                                      'message': 'Execution is already in progress'}
                            request.env['otl.api.sync.log'].sudo().create_api_log(
                                '/api/%s/get_appointment_current_status' % (version), data, uid,
                                result, network_strength)
                            return json.dumps(result)
                    self.get_appointment_current_status_api_queue.update({
                        appointment_id: time
                    })
                    _logger.info('get_appointment_current_status_api_queue Data - Added--:%s' % (
                        self.get_appointment_current_status_api_queue))

                result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                           'action_get_appointment_current_status',
                                           [data])
            else:
                result = {'override_json_result': 1, 'result': 'Failed', 'message': 'Invalid Version'}
        else:
            result = message
        request.env['otl.api.sync.log'].sudo().create_api_log('/api/%s/get_appointment_current_status' % (version),
                                                              params, uid,
                                                              result, network_strength)
        result.update({'override_json_result': 1})
        if enable_api_queue_system:
            self.get_appointment_current_status_api_queue.pop(appointment_id, '')
            _logger.info('get_appointment_current_status_api_queue Data - Ending--:%s' % (
                self.get_appointment_current_status_api_queue))
        return json.dumps(result)
