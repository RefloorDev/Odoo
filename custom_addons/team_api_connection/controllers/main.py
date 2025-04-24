from odoo import fields,http, _
from odoo.http import content_disposition, dispatch_rpc, request, \
    serialize_exception as _serialize_exception, Response
from odoo.exceptions import AccessError, UserError
import json
from json import loads
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

common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(URL))
models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))

import logging

_logger = logging.getLogger(__name__)


class JsonRPCDispatcherInherit(http.JsonRPCDispatcher):
    def _response(self, result=None, error=None):
        response = {'jsonrpc': '2.01', 'id': self.request_id}
        if error is not None:
            response['error'] = error 
        if result is not None:
            response['result'] = result
            # Try to parse and format result if it's a string
            if isinstance(result, str):
                result_dict = ast.literal_eval(result)
                try:
                    result_dict = ast.literal_eval(result)
                    if 'override_json_result' in result_dict and result_dict.get('override_json_result', 0):
                        mime = 'application/json'
                        # body = json.dumps(result_dict, default=lambda obj: obj.isoformat() if hasattr(obj, 'isoformat') else str(obj))
                        # body = json.dumps(result_dict, default=date_utils.json_default)
                        return self.request.make_json_response(result_dict, status=error and error.pop('http_status', 200) or 200, headers=[('Content-Type', mime), ('Content-Length', len(result_dict))])
                        # return self.request.make_json_response(body, status=error and error.pop('http_status', 200) or 200, headers=[('Content-Type', mime), ('Content-Length', len(body))])
                except Exception as e:
                    _logger.error("Failed to parse result string: %s. Error: %s. Result was: %s", str(e), type(e).__name__, result)
            
        response['session_id'] = request.session.sid if request and request.session else None
        mime = 'application/json'
        # body = json.dumps(response, default=lambda obj: obj.isoformat() if hasattr(obj, 'isoformat') else str(obj))
        # return self.request.make_json_response(body, status=error and error.pop('http_status', 200) or 200, headers=[('Content-Type', mime), ('Content-Length', len(body))])
        return self.request.make_json_response(response, status=error and error.pop('http_status', 200) or 200, headers=[('Content-Type', mime), ('Content-Length', len(response))])

class JsonRequest_API(http.Controller):

    def _json_response(self, result=None, error=None):

        response = {
            'jsonrpc': '2.0',
            'id': self.jsonrequest.get('id')
        }
        if error is not None:
            response['error'] = error
        if result is not None:
            response['result'] = result

            if (isinstance(result, str)):
                try:
                    result_dict = ast.literal_eval(result)
                    if 'override_json_result' in result_dict and result_dict.get('override_json_result', 0):
                        mime = 'application/json'
                        body = json.dumps(result_dict, default=date_utils.json_default)
                        return Response(
                            body, status=error and error.pop('http_status', 200) or 200,
                            headers=[('Content-Type', mime), ('Content-Length', len(body))]
                        )
                except:
                    pass

        response['session_id'] = self.session.sid

        mime = 'application/json'
        body = json.dumps(response, default=date_utils.json_default)

        return Response(
            body, status=error and error.pop('http_status', 200) or 200,
            headers=[('Content-Type', mime), ('Content-Length', len(body))]
        )


http.Controller._json_response = JsonRequest_API._json_response


class API_Homes(http.Controller):

    def reverse(self, string):
        return "".join(reversed(string))

    def token_extract(self, token):
        values = {}
        token = (self.reverse(token)).encode("utf-8")
        try:
            token_decode = JWT_DECODE(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            token_decode = token_decode.decode("utf-8")
            values = ast.literal_eval(token_decode)
        except:
            token_decode = ''
        return values

    def get_credentials(self, token):
        user_id = False
        password = False

        values = self.token_extract(token)
        if values == {}:
            return False, False
        user_id = values.get('user_id', False)
        password = values.get('password', False)
        if user_id:
            user_id = int(user_id)
        return user_id, password

    def authenticate_user(self, username, password, user_values={}, restrict_multi_login=0):
        _logger.info(f"Authentication - authenticate_user -odoo - user : {username}")
        uid = False
        token = ''
        result = {}
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        if username and password and DB:
            _logger.info(f"Authentication - authenticate_user -odoo - before db connection - user : {username}")
            uid = common.authenticate(DB, username, password, {})
            _logger.info(f"Authentication - authenticate_user -odoo - after db connection - user : {username}")
            registered_id = user_values.get('device_reg_id', '')
            if uid:
                # user = request.env['res.users'].browse(uid)
                user = request.env['res.users'].sudo().browse(uid)
                                
                if restrict_multi_login and user.token_name and user.device_reg_id and user.device_reg_id != registered_id:
                    _logger.error(f"Authentication - authenticate_user -odoo - user : {username} ; already logged-in another device")
                    result.update({
                        'result': 'TokenExist',
                        'message': 'You have already logged-in another device. Please logout from that device or contact refloor support.',
                    })
                    return result
                _logger.info(f"Authentication - authenticate_user -odoo - user : {username} ; success")
                # token = token_hex(32)
                token = ''
                payload = {
                    'user_id': uid,
                    'password': password,
                    'datetime':str(fields.Datetime.now()),
                }
                token = JWT_ENCODE(payload, JWT_SECRET, JWT_ALGORITHM)
                token = self.reverse(token.decode("utf-8"))
                _logger.info(f"Authentication - authenticate_user -odoo - user : {username} ; Token generated")
                models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'res.users', 'write',
                                  [[uid], {'token_name': token}])
                _logger.info(f"Authentication - authenticate_user -odoo - user : {username} ; Retrieving user details")
                user_details = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'res.users', 'get_user_details',
                                              [int(uid)])
                user_details.update({
                    'user_id': uid,
                    'token': token,
                })
                request.env['res.users'].action_log_user_authentication(uid, 'login', token, user_values)
                result.update({
                    'result': 'Success',
                    'values': [user_details],
                    'message': '',
                })
                if user_values:
                    user_values.update({'login': username})
                    _logger.info(f"Authentication - authenticate_user -odoo - user : {username} ; updating device id")
                    data = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'res.users', 'update_device_id',
                                             [user_values])
                    return result
            else:
                _logger.error(f"Authentication - authenticate_user -odoo - user : {username} ; Invalid credentials")
                return {
                    'result': 'Failed',
                    'message': 'Invalid Credentials'
                }
        else:
            _logger.error(f"Authentication - authenticate_user -odoo - user : {username} ; No Value for Login/Password/DB")
            return {
                'result': 'Failed',
                'message': 'No Value for Login/Password/DB'
            }

    # @route('/api/authenticate', type='http', auth="none", methods=['POST'], csrf=False)
    # def authenticate_user_credentials(self, **kwargs):
    #     _logger.info("===============server_proxy=========" + str(models))
    #     values = request.params.copy()
    #     username = values.get('login', False)
    #     password = values.get('password', False)
    #     registered_id = values.get('device_reg_id', False)
    #     if not username:
    #         _logger.info("------------Empty username-------------------")
    #         return json.dumps({'result': 'Failed', 'message': 'Empty login'})
    #     if not password:
    #         _logger.info("------------Empty password-------------------")
    #         return json.dumps({'result': 'Failed', 'message': 'Empty password'})
    #     if not registered_id:
    #         _logger.info("------------Empty Device Registered id-------------------")
    #         return json.dumps({'result': 'Failed', 'message': 'Empty registered_id'})
    #     result = self.authenticate_user(username, password, registered_id)
    #     _logger.info("------------Authentication result-------------------" + str(result))
    #     return json.dumps(result)

    def action_verify_token(self, uid, token):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        result_duplicate = {'result': 'AuthFailed',
                            'message': 'You have been logged into another device using the same account. Please login again.', 'token': 1}
        result_auth_failed = {'result': 'AuthFailed',
                            'message': 'Session expired. Please login again.', 'token': 1}
        result_inactive = {'result': 'AuthFailed', 'message': 'Account disabled. Please contact admin.', 'token': 1}
        if uid and token:
            _logger.info('Token...........:' + str(token))
            _logger.info('User Id...........:' + str(uid))
            values = {}
            try:
                values.update({'id': str(uid), 'token': token})
                _logger.info("------------Calling fuction verify api token---------------")
            except:
                values = {}
            if values != {}:
                user_result = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'res.users', 'verify_api_token',
                                            [values])
                _logger.info("User Id(after function).......:" + str(user_result))
                token_status = user_result.get('token_status', 'different')
                if user_result.get('user_exists', False) and token_status == 'empty':
                    return False, result_auth_failed
                elif user_result.get('user_exists', False) and token_status == 'same':
                    _logger.info("------------Token Verified---------------")
                    return True, True
        user = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'res.users', 'is_active_user', [int(uid)])

        if user:
            return False, result_inactive
        else:
            return False, result_duplicate

    @route('/api/forgot_password', type='http', auth="none", methods=['POST'], csrf=False)
    def forget_password_api(self, **kwargs):
        """
         Forgot Password
         @api {POST}/api/forgot_password Reset Salesman login credentials
         @apiVersion 1.0.0
         @apiName Forgot Password
         @apiGroup Salesman
         @apiDescription Salesman login credentials

         @apiParam {String} login Username.
         @apiParamExample {form-data} Request-Example:
            login:vrenaud@refloor.com
         @apiSuccessExample {json} Success-Response:
             HTTP/1.1 200 OK
             {
                "result": "Success",
                "message": "Please check your mailbox for password reset instructions"
            }

         @apiErrorExample {json} Error-Response:
             HTTP/1.1 200 OK
            {
                "result": "Failed",
                "message": "This Email ID is not registered in the system"
            }

         @apiError (Error Code) {Number} 500 Internal Server Error.

        @apiSampleRequest off
        """
        params = request.params.copy()
        login = params.get('login', False)
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        if not login:
            _logger.info("----------------------Failed:Empty login-------------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty login'})
        values = ({'login': login})
        _logger.info(f"Forgot Password - request for - {login}")
        data = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'res.users', 'forget_password_api',
                                 [values])
        return json.dumps(data)

    @route('/api/authenticate', type='http', auth="none", methods=['POST'], csrf=False)
    def authenticate_salesperson_user_credentials(self, **kwargs):
        """
         Authenticate
         @api {POST}/api/authenticate Salesman login Authentication
         @apiVersion 1.0.0
         @apiName Authenticate
         @apiGroup Salesman
         @apiDescription Salesman login Authentication

         @apiParam {String} login Username.
         @apiParam {String} password Password.
         @apiParam {String} device_reg_id Device Registration Token.
         @apiParamExample {form-data} Request-Example:
            login:vrenaud@refloor.com
            password:testAPP1
            device_reg_id:1234

         @apiSuccessExample {json} Success-Response:
             HTTP/1.1 200 OK
             {
                "result": "Success",
                "values": [
                    {
                        "user_id": 155,
                        "user_name": "Vince Renaud",
                        "token": "cQQ4u07DsUKBjCzJdG1DZy7RDnvPeEVnnfidHob_EQw.9JCUQFEdzVGdiojIkJ3b3N3chBnIsUTNxojIkl2XyV2c1Jye.9JiN1IzUIJiOicGbhJCLiQ1VKJiOiAXe0Jye"
                    }
                ],
                "message": ""
            }

         @apiErrorExample {json} Error-Response:
             HTTP/1.1 200 OK
            {
                "result": "Failed",
                "message": "Invalid Credentials"
            }

         @apiError (Error Code) {Number} 500 Internal Server Error.

        @apiSampleRequest off
        """
        _logger.info("Authentication - Login request received")
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        #_logger.info("===============server_proxy=========" + str(models))
        values = request.params.copy()
        username = values.get('login', False)
        password = values.get('password', False)
        registered_id = values.get('device_reg_id', False)
        device_name = values.get('device_name', '')
        device_os = values.get('device_os', '')
        app_version = values.get('app_version', '')
        _logger.info(f"Authentication - {username,device_name,device_os,app_version,registered_id} ")
        restrict_multi_login = int(values.get('restrict_multi_login', 0))
        if not username:
            _logger.error("Authentication - Empty username")
            return json.dumps({'result': 'Failed', 'message': 'Empty login'})
        if not password:
            _logger.error(f"Authentication - Empty password  for user: {username}")
            return json.dumps({'result': 'Failed', 'message': 'Empty password'})
        if not registered_id:
            _logger.error(f"Authentication - Empty registered_id for user : {username}")
            return json.dumps({'result': 'Failed', 'message': 'Empty registered_id'})
        _logger.info(f"Authentication - Before i360 connection for user: {username}")
        data = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'res.users', 'authenticate_salesperson_user',
                                     [{'username': username, 'password': password}])
        _logger.info(f"Authentication - After i360 connection for user: {username}")
        if data.get('result', '') == 'Success':
            user_vals = {
                'device_reg_id': registered_id,
                'device_name': device_name,
                'device_os': device_os,
                'app_version': app_version,
            }
            _logger.info(f"Authentication - Before odoo db connection for user: {username}")
            message = self.authenticate_user(username, password, user_vals, restrict_multi_login)
            _logger.info(f"Authentication - After odoo db connection for user: {username}")
            return json.dumps(message)
        else:
            _logger.error(f"Authentication - i360 authentication failure for user : {username} ; data: {data}")
            #result = data
            return json.dumps({'result': 'Failed', 'message': 'User Authentication Failed'})

    # Create Attachment
    @route('/api/CreateAttachment', type='http', auth="none", methods=['POST'], csrf=False)
    def create_attachment_api(self, **kwargs):
        """
         CreateAttachment
         @api {POST}/api/CreateAttachment Upload Files
         @apiVersion 1.0.0
         @apiName CreateAttachment
         @apiGroup Salesman
         @apiDescription To upload the images/documents to the system

         @apiParam {String} token Token.
         @apiParam {File} attachment Files to be uploaded.
         @apiParamExample {form-data} Request-Example:
            token:cQQ4u07DsUKBjCzJdG1DZy7RDnvPeEVnnfidHob_EQw.9JCUQFEdzVGdiojIkJ3b3N3chBnIsUTNxojIkl2XyV2c1Jye.9JiN1IzUIJiOicGbhJCLiQ1VKJiOiAXe0Jye
            attachment: Image.jpg

         @apiSuccessExample {json} Success-Response:
             HTTP/1.1 200 OK
             {
                "result": "Success",
                "values": [
                    {
                        "user_id": 155,
                        "user_name": "Vince Renaud",
                        "token": "cQQ4u07DsUKBjCzJdG1DZy7RDnvPeEVnnfidHob_EQw.9JCUQFEdzVGdiojIkJ3b3N3chBnIsUTNxojIkl2XyV2c1Jye.9JiN1IzUIJiOicGbhJCLiQ1VKJiOiAXe0Jye"
                    }
                ],
                "message": ""
            }

         @apiErrorExample {json} Error-Response:
             HTTP/1.1 200 OK
            {
                "result": "Failed",
                "message": "Invalid Credentials"
            }

         @apiError (Error Code) {Number} 500 Internal Server Error.

        @apiSampleRequest off
        """
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        params = dict(params)
        token = params.get('token', False)
        file = params.get('attachment', False)
        if not token:
            _logger.info("------------Token Missing in CreateAttachment api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)

        file_data = {}

        status, message = self.action_verify_token(uid, token)
        if status:
            if not file:
                return json.dumps({'result': 'Failed', 'message': 'Empty attachment in values.'})

            if type(file) == werkzeug.datastructures.FileStorage:
                image_binary = (file.read())
                file_data.update(
                    {'uid': int(uid), 'image': base64.b64encode(image_binary).decode('utf-8'), 'file_name': file.filename})
                data = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'ir.attachment', 'create_attachment',
                                         [file_data])
                if data:
                    result = {
                        'result': 'Success',
                        'values': data,
                        'message': '',
                    }
                else:
                    result = {'result': 'Failed', 'message': 'Can not create image URL'}
            else:
                result = {'result': 'Failed', 'message': 'File type must be werkzeug.datastructures.FileStorage type'}

        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        return json.dumps(result)

    @route('/api/SalesScheduleList', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def get_SalesScheduleList_api(self, **kwargs):
        """
            SalesScheduleList
            @api {POST}/api/SalesScheduleList List Appointment Details of the current day
            @apiVersion 1.0.0
            @apiName SalesScheduleList
            @apiGroup Salesman
            @apiDescription List Appointment Details of the current day for the logined user

            @apiParam {String} token Token.
            @apiParamExample {form-data} Request-Example:
            token:cQQ4u07DsUKBjCzJdG1DZy7RDnvPeEVnnfidHob_EQw.9JCUQFEdzVGdiojIkJ3b3N3chBnIsUTNxojIkl2XyV2c1Jye.9JiN1IzUIJiOicGbhJCLiQ1VKJiOiAXe0Jye

            @apiSuccessExample {json} Success-Response:
             HTTP/1.1 200 OK
             {
                "result": "Success",
                "room_data": [
                    {
                        "id": 1,
                        "name": "BAR",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "room_category": "Vinyl Flooring"
                    }
                ],
                "appointment_details": [
                    {
                        "id": 400,
                        "name": "CAP/2021/00400",
                        "customer_name": "COMPAU, RON",
                        "applicant_first_name": "Ron",
                        "applicant_middle_name": "",
                        "applicant_last_name": "Compau",
                        "co_applicant_first_name": "dfdfdfd",
                        "co_applicant_middle_name": "",
                        "co_applicant_last_name": "dggdf",
                        "co_applicant_phone": "",
                        "co_applicant_email": "ss@gmail.com",
                        "co_applicant_address": "CoAddress",
                        "co_applicant_city": "COCity",
                        "co_applicant_state_id": "",
                        "co_applicant_state_code": "",
                        "co_applicant_state_name": "",
                        "co_applicant_zip": "CoZip",
                        "co_applicant_secondary_phone": "(313) 673-9878",
                        "is_room_measurement_exist": true,
                        "customer_id": 337,
                        "co_applicant": "dggdf, dfdfdfd",
                        "appointment_date": "2021-04-15 08:00:00",
                        "street": "39134 Baroque Blvd",
                        "street2": "",
                        "city": "Clinton Township",
                        "state_id": 43,
                        "state_code": "MI",
                        "state": "Michigan",
                        "country_id": 0,
                        "country": "",
                        "zip": "48038",
                        "country_code": "",
                        "phone": "(586) 634-0867",
                        "mobile": false,
                        "email": "roncompau13@yahooo.com",
                        "sales_person": "mhigley@refloor.com",
                        "salesperson_id": 183,
                        "partner_latitude": 0,
                        "partner_longitude": 0
                    },
                    {
                        "id": 399,
                        "name": "CAP/2021/00399",
                        "customer_name": "BASILISCO, SANGEETA",
                        "applicant_first_name": "Sangeeta",
                        "applicant_middle_name": "",
                        "applicant_last_name": "Basilisco",
                        "co_applicant_first_name": "Jose",
                        "co_applicant_middle_name": "",
                        "co_applicant_last_name": "Rs",
                        "co_applicant_phone": "",
                        "co_applicant_email": "ddd@gmail.com",
                        "co_applicant_address": "Stephenson Highway",
                        "co_applicant_city": "Troy",
                        "co_applicant_state_id": 43,
                        "co_applicant_state_code": "MI",
                        "co_applicant_state_name": "Michigan",
                        "co_applicant_zip": "48083",
                        "co_applicant_secondary_phone": "(243) 423-4234",
                        "is_room_measurement_exist": true,
                        "customer_id": 336,
                        "co_applicant": "Rs, Jose",
                        "appointment_date": "2021-04-15 09:00:00",
                        "street": "49651 Golden Lake Dr",
                        "street2": "",
                        "city": "Shelby Twp",
                        "state_id": 43,
                        "state_code": "MI",
                        "state": "Michigan",
                        "country_id": 0,
                        "country": "",
                        "zip": "48315",
                        "country_code": "",
                        "phone": "(586) 530-1810",
                        "mobile": false,
                        "email": "claudegbasil0501@gmail.com",
                        "sales_person": "mhigley@refloor.com",
                        "salesperson_id": 183,
                        "partner_latitude": 0,
                        "partner_longitude": 0
                    }
                ],
                "message": ""
            }

            @apiErrorExample {json} Error-Response:
            HTTP/1.1 200 OK
            {
                "result": "AuthFailed",
                "message": "You have been logged into another device using the same account. Please login again.",
                "token": 1
            }

            @apiError (Error Code) {Number} 500 Internal Server Error.

            @apiSampleRequest off
        """
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        if not token:
            _logger.info("------------Token Missing in main SalesScheduleList api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main SalesScheduleList api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main SalesScheduleList api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            room_data = models.execute_kw(DB, int(uid), password, 'team.room.room', 'get_rooms', [])
            appointment_data = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                                 'get_appointment_data', [int(uid)])

            result = {
                'result': 'Success',
                'room_data': room_data,
                'appointment_details': appointment_data,
                'message': '',
            }
        else:
            result = message
        return json.dumps(result)

    @route('/api/RoomsScheduleList', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def get_RoomsScheduleList_api(self, **kwargs):
        """
            RoomsScheduleList
            @api {POST}/api/RoomsScheduleList List Rooms Available
            @apiVersion 1.0.0
            @apiName RoomsScheduleList
            @apiGroup Salesman
            @apiDescription List Rooms available along with status i.e, whether it is already measured or not

            @apiParam {String} token Token.
            @apiParam {Int} appointment_id Appointment Reference
            @apiParamExample {form-data} Request-Example:
            token:cQQ4u07DsUKBjCzJdG1DZy7RDnvPeEVnnfidHob_EQw.9JCUQFEdzVGdiojIkJ3b3N3chBnIsUTNxojIkl2XyV2c1Jye.9JiN1IzUIJiOicGbhJCLiQ1VKJiOiAXe0Jye
            appointment_id:399

            @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "result": "Success",
                "values": [
                    {
                        "id": 1,
                        "name": "BAR",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "measurement_exist": "True",
                        "is_custom_room": "False",
                        "custom_room_measurement_id": "False",
                        "custom_room_parent": "False",
                        "room_category": "Vinyl Flooring"
                    },
                    {
                        "id": 2,
                        "name": "BASEMENT",
                        "note": "",
                        "company_id": 1,
                        "image": "",
                        "measurement_exist": "False",
                        "is_custom_room": "False",
                        "custom_room_measurement_id": "False",
                        "custom_room_parent": "False",
                        "room_category": "Vinyl Flooring"
                    }
                ],
                "message": ""
            }
            @apiErrorExample {json} Error-Response:
            HTTP/1.1 200 OK
            {
                "result": "AuthFailed",
                "message": "You have been logged into another device using the same account. Please login again.",
                "token": 1
            }

            @apiError (Error Code) {Number} 500 Internal Server Error.

            @apiSampleRequest off
        """
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        appointment_id = params.get('appointment_id', 0)
        if not token:
            _logger.info("------------Token Missing in main RoomScheduleList api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        if not appointment_id:
            _logger.info("------------Appointment_id Missing in main RoomScheduleList api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty appointment_id.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main RoomScheduleList api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main RoomScheduleList api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            room_data = models.execute_kw(DB, int(uid), password, 'team.room.room', 'get_room_list',[{'appointment_id':appointment_id}])
            result = {
                'result': 'Success',
                'values': room_data,
                'message': '',
            }
        else:
            result = message
        return json.dumps(result)

    @route('/api/add_custom_rooms', type='http', auth="none", methods=['POST'], csrf=False,allow_none=True, )
    def add_custom_rooms(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        appointment_id = int(params.get('appointment_id', 0))
        room_name = params.get('room_name', '')
        if not token:
            _logger.info("------------Token Missing in add_custom_rooms api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in add_custom_rooms api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in add_custom_rooms api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.room.room',
                                       'add_custom_rooms',
                                       [{'appointment_id': appointment_id,
                                         'room_name': room_name}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/PaymentPlanList', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def get_PaymentplanList_api(self, **kwargs):
        """
            RoomsScheduleList
            @api {POST}/api/RoomsScheduleList List Rooms Available
            @apiVersion 1.0.0
            @apiName RoomsScheduleList
            @apiGroup Salesman
            @apiDescription List Rooms available along with status i.e, whether it is already measured or not

            @apiParam {String} token Token.
            @apiParam {Int} appointment_id Appointment Reference
            @apiParamExample {form-data} Request-Example:
            token:cQQ4u07DsUKBjCzJdG1DZy7RDnvPeEVnnfidHob_EQw.9JCUQFEdzVGdiojIkJ3b3N3chBnIsUTNxojIkl2XyV2c1Jye.9JiN1IzUIJiOicGbhJCLiQ1VKJiOiAXe0Jye
            appointment_id:399

            @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "result": "Success",
                "values": [
                    {
                        "payment_plans": [
                            {
                                "id": 6,
                                "plan_title": "Economy Package",
                                "plan_subtitle": "Pressboard",
                                "description": "Recommendation - If you are flipping your house",
                                "material_cost": 9.91,
                                "warranty": "",
                                "sequence": 1,
                                "company_id": 0,
                                "cost_per_sqft": 12.91,
                                "monthly_promo": 0,
                                "additional_cost": 120,
                                "warranty_info": "1 year warranty",
                                "eligible_for_discounts": "false",
                                "unit_of_measure": "each",
                                "grade": "Econoline",
                                "stair_cost": 132.3
                            },
                            {
                                "id": 7,
                                "plan_title": "Standard Package",
                                "plan_subtitle": "Vinyl Plank",
                                "description": "Recommendation - if you are moving in the next 5 years",
                                "material_cost": 14.16,
                                "warranty": "",
                                "sequence": 2,
                                "company_id": 0,
                                "cost_per_sqft": 17.16,
                                "monthly_promo": 0,
                                "additional_cost": 120,
                                "warranty_info": "4 year warranty",
                                "eligible_for_discounts": "false",
                                "unit_of_measure": "each",
                                "grade": "Standard",
                                "stair_cost": 189
                            },
                            {
                                "id": 8,
                                "plan_title": "Smart Choice Package",
                                "plan_subtitle": "",
                                "description": "Recommendation - If you are planning to stay in your home for 5 years or more",
                                "material_cost": 15.73,
                                "warranty": "",
                                "sequence": 3,
                                "company_id": 0,
                                "cost_per_sqft": 18.73,
                                "monthly_promo": 0,
                                "additional_cost": 120,
                                "warranty_info": "Lifetime Guarantee",
                                "eligible_for_discounts": "true",
                                "unit_of_measure": "each",
                                "grade": "Smart Choice",
                                "stair_cost": 0
                            },
                            {
                                "id": 9,
                                "plan_title": "Premium Package",
                                "plan_subtitle": "Hardwood",
                                "description": "Recommendation - If you are planning to use high end",
                                "material_cost": 18.88,
                                "warranty": "",
                                "sequence": 4,
                                "company_id": 0,
                                "cost_per_sqft": 21.88,
                                "monthly_promo": 0,
                                "additional_cost": 120,
                                "warranty_info": "10 Year Warranty",
                                "eligible_for_discounts": "false",
                                "unit_of_measure": "each",
                                "grade": "Premium",
                                "stair_cost": 252
                            }
                        ],
                        "payment_options": [
                            {
                                "id": 1,
                                "Name": "Cash",
                                "Description__c": "Pay Now",
                                "Down_Payment__c": "0.5",
                                "Final_Payment__c": "0.5",
                                "Payment_Factor__c": "false",
                                "Balance_Due__c": "false",
                                "Payment_Info__c": "50% Down / 50% Completion",
                                "sequence": 1
                            },
                            {
                                "id": 5,
                                "Name": "1 Year<br />No Payments<br />No Interest",
                                "Description__c": "In 1 Year",
                                "Down_Payment__c": "false",
                                "Final_Payment__c": "false",
                                "Payment_Factor__c": "false",
                                "Balance_Due__c": "365.0",
                                "Payment_Info__c": "Single Payment",
                                "sequence": 2
                            },
                            {
                                "id": 6,
                                "Name": "Zero Interest Program",
                                "Description__c": "25 Equal Payments",
                                "Down_Payment__c": "false",
                                "Final_Payment__c": "false",
                                "Payment_Factor__c": "0.04",
                                "Balance_Due__c": "false",
                                "Payment_Info__c": "Monthly",
                                "sequence": 3
                            },
                            {
                                "id": 7,
                                "Name": "Low Monthly Payment",
                                "Description__c": "No Down Payment<br />$0 Due at Completion<br />No Pre-Payment Penalty",
                                "Down_Payment__c": "false",
                                "Final_Payment__c": "false",
                                "Payment_Factor__c": "0.0132",
                                "Balance_Due__c": "false",
                                "Payment_Info__c": "Monthly",
                                "sequence": 4
                            }
                        ],
                        "monthly_promo": [
                            {
                                "Code": "BIGOFF",
                                "Amount": "1000.0",
                                "Type": "Dollars"
                            },
                            {
                                "Code": "SAVE500",
                                "Amount": "500.0",
                                "Type": "Dollars"
                            },
                            {
                                "Code": "MAGIC5",
                                "Amount": "5.0",
                                "Type": "Percent"
                            }
                        ],
                        "admin_fee": 0,
                        "min_sale_price": 1500.0
                    }
                ],
                "message": ""
            }
            @apiErrorExample {json} Error-Response:
            HTTP/1.1 200 OK
            {
                "result": "AuthFailed",
                "message": "You have been logged into another device using the same account. Please login again.",
                "token": 1
            }

            @apiError (Error Code) {Number} 500 Internal Server Error.

            @apiSampleRequest off
        """
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        appointment_id = params.get('appointment_id', 0)
        if not appointment_id:
            _logger.info("------------Appointment ID  Missing in main PaymentMethodList api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID'})
        if not token:
            _logger.info("------------Token Missing in main SalesScheduleList api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main SalesScheduleList api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main SalesScheduleList api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            payment_plan_data = models.execute_kw(DB, int(uid), password, 'product.template',
                                                  'get_payment_plan', [{'appointment_id':appointment_id}])
            result = {
                'result': 'Success',
                'values': payment_plan_data,
                'message': '',
            }
        else:
            result = message
        return json.dumps(result)

    @route('/api/PaymentMethodList', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def get_PaymentMethodList_api(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        appointment_id = params.get('appointment_id', 0)
        if not appointment_id:
            _logger.info("------------Appointment ID  Missing in main PaymentMethodList api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID'})
        if not token:
            _logger.info("------------Token Missing in main PaymentMethodList api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main PaymentMethodList api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main PaymentMethodList api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            payment_method_data = models.execute_kw(DB, int(uid), password, 'product.template', 'get_payment_method',
                                                    [{'appointment_id': appointment_id}])
            if payment_method_data:
                result = {
                    'result': 'Success',
                    'values': payment_method_data,
                    'message': '',
                }
            else:
                result = {
                    'result': 'Failed',
                    'values': '',
                    'message': 'Data Not Found',
                }

        else:
            result = message
        return json.dumps(result)

    @route('/api/select_material_from_plan', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def Select_material(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        appointment_id = params.get('appointment_id', 0)
        material_id = params.get('material_id', 0)
        if not appointment_id:
            _logger.info("------------Appointment ID  Missing in main select_material_from_plan api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID'})
        if not material_id:
            _logger.info("------------material_id ID  Missing in main select_material_from_plan api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty material_id '})
        if not token:
            _logger.info("------------Token Missing in main select_material_from_plan api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main select_material_from_plan api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main select_material_from_plan api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'product.product', 'select_material_from_plan',
                                       [{'appointment_id': appointment_id, 'material_id': material_id}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/check_appointment_room_status', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def Checkroomstatus(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        appointment_id = params.get('appointment_id', False)
        room_id = params.get('room_id', False)
        if not appointment_id:
            _logger.info("------------Appointment ID  Missing in main check_appointment_room_status api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID'})
        if not room_id:
            _logger.info("------------room_id ID  Missing in main  check_appointment_room_status api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty room_id '})
        if not token:
            _logger.info("------------Token Missing in main check_appointment_room_status api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main  check_appointment_room_status api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main check_appointment_room_status api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line', 'Checkroomstatus',
                                       [{'appointment_id': appointment_id,'room_id':room_id}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/user_appointments', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def get_rooms_api(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        if not token:
            _logger.info("------------Token Missing in main dashboard api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main dashboard api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main dashboard api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            appointment_data = models.execute_kw(DB, int(uid), password, 'team.customer.appointment', 'get_appointment_data', [int(uid)])
            result = {
                'result': 'Success',
                'appointment_data': appointment_data,
                'message': '',
            }
        else:
            result = message
        return json.dumps(result)

    @route('/api/add_transitions', type='json', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def transition_add(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', '')
        data = params.get('data', {})
        result = {}
        if not token:
            _logger.info("------------Token Missing in add_transitions api------------------")
            return json.dumps({'override_json_result':1, 'result': 'Failed', 'message': 'Empty token.'})
        if not data:
            _logger.info("------------data Missing in add_transitions api------------------")
            return json.dumps({'override_json_result':1, 'result': 'Failed', 'message': 'Empty data.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in add_transitions api-------------------")
            return json.dumps({'override_json_result':1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in add_transitions api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.contract.transition.line', 'create_transitions',
                                       [data])
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    # create room material
    @route('/api/update_material', type='json', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def update_material(self, **kwargs):
        """
            update_material
            @api {POST}/api/update_material Update Material/Tile Color
            @apiVersion 1.0.0
            @apiName update_material
            @apiGroup Salesman
            @apiDescription Update Material/Tile Color in the measured room

            @apiParam {String} token Token.
            @apiParam {json} data json values
            @apiParamExample {json} Request-Example:
            {
                "token":"cQQ4u07DsUKBjCzJdG1DZy7RDnvPeEVnnfidHob_EQw.9JCUQFEdzVGdiojIkJ3b3N3chBnIsUTNxojIkl2XyV2c1Jye.9JiN1IzUIJiOicGbhJCLiQ1VKJiOiAXe0Jye",
                "data":
                {
                    "measurement_id": 256,
                    "material_id":100,
                    "comments": "cooments about the material"
                }
            }

            @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "result": "Success",
                "message": "Material Updated"
            }
            @apiErrorExample {json} Error-Response:
            HTTP/1.1 200 OK
            {
                "result": "AuthFailed",
                "message": "You have been logged into another device using the same account. Please login again.",
                "token": 1
            }

            @apiError (Error Code) {Number} 500 Internal Server Error.

            @apiSampleRequest off
        """
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', '')
        data = params.get('data', {})
        result = {}
        if not token:
            _logger.info("------------Token Missing in update_material api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        if not data:
            _logger.info("------------data Missing in update_material api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty data.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in update_material api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in update_material api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line','update_material_details',[data])
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/update_material_room', type='json', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def update_material_room(self, **kwargs):
        """
            update_material_room
            @api {POST}/api/update_material_room Update Material/Tile Color
            @apiVersion 1.0.0
            @apiName update_material_room
            @apiGroup Salesman
            @apiDescription Update Material/Tile Color in the measured room & return details of measured room

            @apiParam {String} token Token.
            @apiParam {json} data json values
            @apiParamExample {json} Request-Example:
            {
                "token":"cQQ4u07DsUKBjCzJdG1DZy7RDnvPeEVnnfidHob_EQw.9JCUQFEdzVGdiojIkJ3b3N3chBnIsUTNxojIkl2XyV2c1Jye.9JiN1IzUIJiOicGbhJCLiQ1VKJiOiAXe0Jye",
                "data":
                {
                    "measurement_id": 256,
                    "material_id":100,
                    "comments": "cooments about the material"
                }
            }

            @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
            "result": "Success",
            "values": [
                {
                    "contract_measurement_id": 212,
                    "name": "Bathroom 3-71.0",
                    "material_id": 100,
                    "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Windsong%20Oak.png",
                    "color": "Windsong Oak",
                    "material_name": "Premium Package",
                    "room_image_url": "http://server.oneteamus.com:2446/web/image/2745?access_token=bc5fdc05-e0f8-4ed9-8e46-1052112264c5",
                    "room_image_id": 2745,
                    "material_colors": [
                        {
                            "material_id": 378,
                            "name": "Premium Package",
                            "color": "Alabaster",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Vienna%20Alabaster.jpg"
                        },
                        {
                            "material_id": 103,
                            "name": "",
                            "color": "Antique Pine",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/AntiquePine.jpg"
                        },
                        {
                            "material_id": 333,
                            "name": "Premium Package",
                            "color": "Beverly Hills",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Coastal%20Beverly%20Hills.jpg"
                        },
                        {
                            "material_id": 342,
                            "name": "Premium Package",
                            "color": "Broadway",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Evolve%20Broadway.png"
                        },
                        {
                            "material_id": 104,
                            "name": "",
                            "color": "Burnished Hickory",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Burnished%20Hickory.jpg"
                        },
                        {
                            "material_id": 367,
                            "name": "Premium Package",
                            "color": "Carbon",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Meridian%20Carbon.jpg"
                        },
                        {
                            "material_id": 106,
                            "name": "",
                            "color": "Cordova Cherry",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Cordova%20Cherry.png"
                        },
                        {
                            "material_id": 354,
                            "name": "Premium Package",
                            "color": "Corinthian Coast",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Athena%20Corinthian%20Coast.jpg"
                        },
                        {
                            "material_id": 107,
                            "name": "",
                            "color": "Country Natural",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/CountryNatural.png"
                        },
                        {
                            "material_id": 355,
                            "name": "Premium Package",
                            "color": "Cyprus",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Athena%20Cyprus.jpg"
                        },
                        {
                            "material_id": 108,
                            "name": "",
                            "color": "Delacy",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Delacy.png"
                        },
                        {
                            "material_id": 353,
                            "name": "Premium Package",
                            "color": "Farmhouse White",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Achim%20Farmhouse%20White.jpg"
                        },
                        {
                            "material_id": 109,
                            "name": "",
                            "color": "Finnish Pine",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/FinnishPine.jpg"
                        },
                        {
                            "material_id": 110,
                            "name": "",
                            "color": "Forest Grove",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/ForestGrove.png"
                        },
                        {
                            "material_id": 368,
                            "name": "Premium Package",
                            "color": "Fossil",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Meridian%20Fossil.jpg"
                        },
                        {
                            "material_id": 111,
                            "name": "",
                            "color": "Frontier",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Frontier.png"
                        },
                        {
                            "material_id": 360,
                            "name": "Premium Package",
                            "color": "Harbor Beige",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Cascade%20Harbor%20Beige.jpg"
                        },
                        {
                            "material_id": 112,
                            "name": "",
                            "color": "Hermitage",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Hermitage.png"
                        },
                        {
                            "material_id": 334,
                            "name": "Premium Package",
                            "color": "Highland Grey",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/HighlandGrey.png"
                        },
                        {
                            "material_id": 344,
                            "name": "Premium Package",
                            "color": "Jurassic",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Evolve%20Jurassic.png"
                        },
                        {
                            "material_id": 115,
                            "name": "",
                            "color": "Long View Pine",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Long%20View%20Pine.png"
                        },
                        {
                            "material_id": 116,
                            "name": "",
                            "color": "Longden",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Longden.png"
                        },
                        {
                            "material_id": 345,
                            "name": "Premium Package",
                            "color": "Malibu",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Coastal%20Malibu.jpg"
                        },
                        {
                            "material_id": 336,
                            "name": "Premium Package",
                            "color": "Melrose Ave",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Coastal%20Melrose%20Ave.jpg"
                        },
                        {
                            "material_id": 373,
                            "name": "Premium Package",
                            "color": "Mineral",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Vienna%20Mineral.jpg"
                        },
                        {
                            "material_id": 118,
                            "name": "",
                            "color": "Old English",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/OldEnglish.jpg"
                        },
                        {
                            "material_id": 343,
                            "name": "Premium Package",
                            "color": "Paradise Bay",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Deco%20Paradise%20Bay.jpg"
                        },
                        {
                            "material_id": 364,
                            "name": "Premium Package",
                            "color": "Patina",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Graffiti%20Patina.jpg"
                        },
                        {
                            "material_id": 361,
                            "name": "Premium Package",
                            "color": "Pebble",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Century%20Pebble.jpg"
                        },
                        {
                            "material_id": 119,
                            "name": "",
                            "color": "Platinum Oak",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/PlatinumOak.jpg"
                        },
                        {
                            "material_id": 375,
                            "name": "Premium Package",
                            "color": "Porcelain",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Meridian%20Porcelain.jpg"
                        },
                        {
                            "material_id": 374,
                            "name": "Premium Package",
                            "color": "Quartz",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Vienna%20Quartz.jpg"
                        },
                        {
                            "material_id": 120,
                            "name": "",
                            "color": "Rain Barrel",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/RainBarrel.jpg"
                        },
                        {
                            "material_id": 346,
                            "name": "Premium Package",
                            "color": "Rodeo Dr",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Coastal%20Rodeo%20Drive.jpg"
                        },
                        {
                            "material_id": 347,
                            "name": "Premium Package",
                            "color": "Sandlot",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Evolve%20Sandlot.png"
                        },
                        {
                            "material_id": 359,
                            "name": "Premium Package",
                            "color": "Sea Mist",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Cascade%20Sea%20Mist.jpg"
                        },
                        {
                            "material_id": 356,
                            "name": "Premium Package",
                            "color": "Seagull",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Cape%20May%20Seagull.jpg"
                        },
                        {
                            "material_id": 372,
                            "name": "Premium Package",
                            "color": "Sediment",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Pasedena%20Sediment.jpg"
                        },
                        {
                            "material_id": 2,
                            "name": "Additional Cost",
                            "color": "Select Color",
                            "material_image_url": "http://server.oneteamus.com:2446/web/image/625?access_token=98353e24-b62f-42d8-b9d4-3d4f08e3625c"
                        },
                        {
                            "material_id": 357,
                            "name": "Premium Package",
                            "color": "Shell",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Cape%20May%20Shell.jpg"
                        },
                        {
                            "material_id": 365,
                            "name": "Premium Package",
                            "color": "Skyline",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Graffiti%20Skyline.jpg"
                        },
                        {
                            "material_id": 369,
                            "name": "Premium Package",
                            "color": "Steel",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Meridian%20Steel.jpg"
                        },
                        {
                            "material_id": 371,
                            "name": "Premium Package",
                            "color": "Stone",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Pasedena%20Stone.jpg"
                        },
                        {
                            "material_id": 348,
                            "name": "Premium Package",
                            "color": "Sundance",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Evolve%20Sundance.png"
                        },
                        {
                            "material_id": 349,
                            "name": "Premium Package",
                            "color": "Sunset Blvd",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Coastal%20Sunset%20Blvd.jpg"
                        },
                        {
                            "material_id": 122,
                            "name": "",
                            "color": "Tavern Hickory",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Tavern%20Hickory.png"
                        },
                        {
                            "material_id": 123,
                            "name": "",
                            "color": "Teak Harbor",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Teak%20Harbor.png"
                        },
                        {
                            "material_id": 350,
                            "name": "Premium Package",
                            "color": "Tivoli",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Evolve%20Tivoli.png"
                        },
                        {
                            "material_id": 358,
                            "name": "Premium Package",
                            "color": "White Cap",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Cape%20May%20White%20Cap.jpg"
                        },
                        {
                            "material_id": 124,
                            "name": "",
                            "color": "Windsong Oak",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Windsong%20Oak.png"
                        },
                        {
                            "material_id": 125,
                            "name": "",
                            "color": "Woodland",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Woodland.jpg"
                        }
                    ],
                    "molding_type": [
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
                    "moulding": "Vinyl White",
                    "moulding_id": 2,
                    "striked": "False",
                    "room_id": 5,
                    "room_name": "Bathroom 3",
                    "appointment_id": 171,
                    "room_area": 71,
                    "adjusted_area": 71,
                    "drawing_attachment": [
                        {
                            "id": 2743,
                            "name": "messurementImage.jpeg",
                            "url": "http://server.oneteamus.com:2446/web/image/2743?access_token=d7647d10-81c1-4240-94a3-aaf69a3f851c"
                        }
                    ],
                    "custom_room": "False",
                    "stair_count": 0
                },
                {
                    "total_area": 71,
                    "total_stair_count": 0
                }
            ],
            "message": "Success",
            "override_json_result": 1
            }
            @apiErrorExample {json} Error-Response:
            HTTP/1.1 200 OK
            {
                "result": "AuthFailed",
                "message": "You have been logged into another device using the same account. Please login again.",
                "token": 1
            }

            @apiError (Error Code) {Number} 500 Internal Server Error.

            @apiSampleRequest off
        """
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', '')
        data = params.get('data', {})
        result = {}
        if not token:
            _logger.info("------------Token Missing in update_material api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        if not data:
            _logger.info("------------data Missing in update_material api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty data.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in update_material api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in update_material api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line',
                                       'update_material_details_room', [data])
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    #update moulding
    @route('/api/update_moulding', type='json', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def update_moulding(self, **kwargs):
        """
            update_moulding
            @api {POST}/api/update_moulding Update Molding of the Room
            @apiVersion 1.0.0
            @apiName update_moulding
            @apiGroup Salesman
            @apiDescription Update type of molding in the measured room & return details of measured room

            @apiParam {String} token Token.
            @apiParam {json} data json values
            @apiParamExample {json} Request-Example:
            {
                "token":"cQQ4u07DsUKBjCzJdG1DZy7RDnvPeEVnnfidHob_EQw.9JCUQFEdzVGdiojIkJ3b3N3chBnIsUTNxojIkl2XyV2c1Jye.9JiN1IzUIJiOicGbhJCLiQ1VKJiOiAXe0Jye",
                "data":
                {
                    "measurement_id": 256,
                    "moulding_type":"Vinyl White"
                }
            }

            @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
            "result": "Success",
            "values": [
                {
                    "contract_measurement_id": 212,
                    "name": "Bathroom 3-71.0",
                    "material_id": 100,
                    "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Windsong%20Oak.png",
                    "color": "Windsong Oak",
                    "material_name": "Premium Package",
                    "room_image_url": "http://server.oneteamus.com:2446/web/image/2745?access_token=bc5fdc05-e0f8-4ed9-8e46-1052112264c5",
                    "room_image_id": 2745,
                    "material_colors": [
                        {
                            "material_id": 378,
                            "name": "Premium Package",
                            "color": "Alabaster",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Vienna%20Alabaster.jpg"
                        },
                        {
                            "material_id": 103,
                            "name": "",
                            "color": "Antique Pine",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/AntiquePine.jpg"
                        },
                        {
                            "material_id": 333,
                            "name": "Premium Package",
                            "color": "Beverly Hills",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Coastal%20Beverly%20Hills.jpg"
                        },
                        {
                            "material_id": 342,
                            "name": "Premium Package",
                            "color": "Broadway",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Evolve%20Broadway.png"
                        },
                        {
                            "material_id": 104,
                            "name": "",
                            "color": "Burnished Hickory",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Burnished%20Hickory.jpg"
                        },
                        {
                            "material_id": 367,
                            "name": "Premium Package",
                            "color": "Carbon",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Meridian%20Carbon.jpg"
                        },
                        {
                            "material_id": 106,
                            "name": "",
                            "color": "Cordova Cherry",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Cordova%20Cherry.png"
                        },
                        {
                            "material_id": 354,
                            "name": "Premium Package",
                            "color": "Corinthian Coast",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Athena%20Corinthian%20Coast.jpg"
                        },
                        {
                            "material_id": 107,
                            "name": "",
                            "color": "Country Natural",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/CountryNatural.png"
                        },
                        {
                            "material_id": 355,
                            "name": "Premium Package",
                            "color": "Cyprus",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Athena%20Cyprus.jpg"
                        },
                        {
                            "material_id": 108,
                            "name": "",
                            "color": "Delacy",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Delacy.png"
                        },
                        {
                            "material_id": 353,
                            "name": "Premium Package",
                            "color": "Farmhouse White",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Achim%20Farmhouse%20White.jpg"
                        },
                        {
                            "material_id": 109,
                            "name": "",
                            "color": "Finnish Pine",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/FinnishPine.jpg"
                        },
                        {
                            "material_id": 110,
                            "name": "",
                            "color": "Forest Grove",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/ForestGrove.png"
                        },
                        {
                            "material_id": 368,
                            "name": "Premium Package",
                            "color": "Fossil",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Meridian%20Fossil.jpg"
                        },
                        {
                            "material_id": 111,
                            "name": "",
                            "color": "Frontier",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Frontier.png"
                        },
                        {
                            "material_id": 360,
                            "name": "Premium Package",
                            "color": "Harbor Beige",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Cascade%20Harbor%20Beige.jpg"
                        },
                        {
                            "material_id": 112,
                            "name": "",
                            "color": "Hermitage",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Hermitage.png"
                        },
                        {
                            "material_id": 334,
                            "name": "Premium Package",
                            "color": "Highland Grey",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/HighlandGrey.png"
                        },
                        {
                            "material_id": 344,
                            "name": "Premium Package",
                            "color": "Jurassic",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Evolve%20Jurassic.png"
                        },
                        {
                            "material_id": 115,
                            "name": "",
                            "color": "Long View Pine",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Long%20View%20Pine.png"
                        },
                        {
                            "material_id": 116,
                            "name": "",
                            "color": "Longden",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Longden.png"
                        },
                        {
                            "material_id": 345,
                            "name": "Premium Package",
                            "color": "Malibu",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Coastal%20Malibu.jpg"
                        },
                        {
                            "material_id": 336,
                            "name": "Premium Package",
                            "color": "Melrose Ave",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Coastal%20Melrose%20Ave.jpg"
                        },
                        {
                            "material_id": 373,
                            "name": "Premium Package",
                            "color": "Mineral",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Vienna%20Mineral.jpg"
                        },
                        {
                            "material_id": 118,
                            "name": "",
                            "color": "Old English",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/OldEnglish.jpg"
                        },
                        {
                            "material_id": 343,
                            "name": "Premium Package",
                            "color": "Paradise Bay",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Deco%20Paradise%20Bay.jpg"
                        },
                        {
                            "material_id": 364,
                            "name": "Premium Package",
                            "color": "Patina",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Graffiti%20Patina.jpg"
                        },
                        {
                            "material_id": 361,
                            "name": "Premium Package",
                            "color": "Pebble",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Century%20Pebble.jpg"
                        },
                        {
                            "material_id": 119,
                            "name": "",
                            "color": "Platinum Oak",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/PlatinumOak.jpg"
                        },
                        {
                            "material_id": 375,
                            "name": "Premium Package",
                            "color": "Porcelain",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Meridian%20Porcelain.jpg"
                        },
                        {
                            "material_id": 374,
                            "name": "Premium Package",
                            "color": "Quartz",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Vienna%20Quartz.jpg"
                        },
                        {
                            "material_id": 120,
                            "name": "",
                            "color": "Rain Barrel",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/RainBarrel.jpg"
                        },
                        {
                            "material_id": 346,
                            "name": "Premium Package",
                            "color": "Rodeo Dr",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Coastal%20Rodeo%20Drive.jpg"
                        },
                        {
                            "material_id": 347,
                            "name": "Premium Package",
                            "color": "Sandlot",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Evolve%20Sandlot.png"
                        },
                        {
                            "material_id": 359,
                            "name": "Premium Package",
                            "color": "Sea Mist",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Cascade%20Sea%20Mist.jpg"
                        },
                        {
                            "material_id": 356,
                            "name": "Premium Package",
                            "color": "Seagull",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Cape%20May%20Seagull.jpg"
                        },
                        {
                            "material_id": 372,
                            "name": "Premium Package",
                            "color": "Sediment",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Pasedena%20Sediment.jpg"
                        },
                        {
                            "material_id": 2,
                            "name": "Additional Cost",
                            "color": "Select Color",
                            "material_image_url": "http://server.oneteamus.com:2446/web/image/625?access_token=98353e24-b62f-42d8-b9d4-3d4f08e3625c"
                        },
                        {
                            "material_id": 357,
                            "name": "Premium Package",
                            "color": "Shell",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Cape%20May%20Shell.jpg"
                        },
                        {
                            "material_id": 365,
                            "name": "Premium Package",
                            "color": "Skyline",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Graffiti%20Skyline.jpg"
                        },
                        {
                            "material_id": 369,
                            "name": "Premium Package",
                            "color": "Steel",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Meridian%20Steel.jpg"
                        },
                        {
                            "material_id": 371,
                            "name": "Premium Package",
                            "color": "Stone",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Pasedena%20Stone.jpg"
                        },
                        {
                            "material_id": 348,
                            "name": "Premium Package",
                            "color": "Sundance",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Evolve%20Sundance.png"
                        },
                        {
                            "material_id": 349,
                            "name": "Premium Package",
                            "color": "Sunset Blvd",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Coastal%20Sunset%20Blvd.jpg"
                        },
                        {
                            "material_id": 122,
                            "name": "",
                            "color": "Tavern Hickory",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Tavern%20Hickory.png"
                        },
                        {
                            "material_id": 123,
                            "name": "",
                            "color": "Teak Harbor",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Teak%20Harbor.png"
                        },
                        {
                            "material_id": 350,
                            "name": "Premium Package",
                            "color": "Tivoli",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Evolve%20Tivoli.png"
                        },
                        {
                            "material_id": 358,
                            "name": "Premium Package",
                            "color": "White Cap",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Cape%20May%20White%20Cap.jpg"
                        },
                        {
                            "material_id": 124,
                            "name": "",
                            "color": "Windsong Oak",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Encore%20Windsong%20Oak.png"
                        },
                        {
                            "material_id": 125,
                            "name": "",
                            "color": "Woodland",
                            "material_image_url": "https://refloormichigan.com/FlooringThumbs/Woodland.jpg"
                        }
                    ],
                    "molding_type": [
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
                    "moulding": "Vinyl White",
                    "moulding_id": 2,
                    "striked": "False",
                    "room_id": 5,
                    "room_name": "Bathroom 3",
                    "appointment_id": 171,
                    "room_area": 71,
                    "adjusted_area": 71,
                    "drawing_attachment": [
                        {
                            "id": 2743,
                            "name": "messurementImage.jpeg",
                            "url": "http://server.oneteamus.com:2446/web/image/2743?access_token=d7647d10-81c1-4240-94a3-aaf69a3f851c"
                        }
                    ],
                    "custom_room": "False",
                    "stair_count": 0
                },
                {
                    "total_area": 71,
                    "total_stair_count": 0
                }
            ],
            "message": "Success",
            "override_json_result": 1
            }
            @apiErrorExample {json} Error-Response:
            HTTP/1.1 200 OK
            {
                "result": "AuthFailed",
                "message": "You have been logged into another device using the same account. Please login again.",
                "token": 1
            }

            @apiError (Error Code) {Number} 500 Internal Server Error.

            @apiSampleRequest off
        """
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', '')
        data = params.get('data', {})
        result = {}
        if not token:
            _logger.info("------------Token Missing in update_moulding api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        if not data:
            _logger.info("------------data Missing in update_moulding api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty data.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in update_moulding api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in update_moulding api-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line',
                                       'update_moulding', [data])
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    # listing  material

    @route('/api/material_list', type='json', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def material_list(self, **kwargs):
            models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
            # params = request.jsonrequest.copy()
            params = request.httprequest.get_json()
            params = dict(params)
            token = params.get('token', '')
            data = params.get('data', {})
            result = {}
            if not token:
                _logger.info("------------Token Missing in material_list api ------------------")
                return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
            uid, password = self.get_credentials(token)
            if not uid:
                _logger.info("------------uid missing in material_list api-------------------")
                return json.dumps(
                    {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
            if not password:
                _logger.info("------------password missing in material_list api-------------------")
                return json.dumps(
                    {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
            status, message = self.action_verify_token(uid, token)
            if status:
                result = models.execute_kw(DB, int(uid), password, 'product.product',
                                           'get_material_list',
                                           [data])
            else:
                result = message
            result.update({'override_json_result': 1})
            return json.dumps(result)

        # Unlink Transition

    @route('/api/remove_transition', type='json', auth="none", methods=['POST'], csrf=False)
    def transition_delete_api(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        if not token:
            _logger.info("------------Token Missing in main RemoveTransition api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        status, message = self.action_verify_token(uid, token)
        if status:
            if not data:
                return json.dumps(
                    {'override_json_result': 1, 'result': 'Failed', 'message': 'Empty attachment_ids.'})
            result = models.execute_kw(DB, int(uid), password, 'team.contract.transition.line',
                                       'transition_delete_api',
                                       [data])
        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)




    @route('/api/filter_transitions', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def get_transition_list(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        appointment_id = params.get('appointment_id', 0)
        room_id = params.get('room_id', 0)
        room_measurement_id = params.get('room_measurement_id',0)
        result = {}
        if not token:
            _logger.info("------------Token Missing------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        if not appointment_id:
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID.'})
        if not room_id:
            return json.dumps({'result': 'Failed', 'message': 'Empty Room ID.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing -------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing -------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            transition_list = models.execute_kw(DB, int(uid), password, 'team.contract.transition.line',
                                                'get_transition_data', [{'appointment_id': appointment_id,'room_id':room_id,'room_measurement_id':room_measurement_id}])
            if transition_list:
                result = {
                    'result': 'Success',
                    'transition_data': transition_list,
                    'message': '',
                }
            else:
                result = {
                    'result': 'Success',
                    'transition_data': transition_list,
                    'message': 'Transition Data Not found',
                }
        else:
            result = message
        return json.dumps(result)

    @route('/api/update_appointments', type='json', auth="none", methods=['POST'], csrf=False, allow_none=True, )
    def update_appointments(self, **kwargs):
        """
            update_appointments
            @api {POST}/api/update_appointments Modify Appointment details
            @apiVersion 1.0.0
            @apiName update_appointments
            @apiGroup Salesman
            @apiDescription Modify the details of applicant & co-applicant in the appointment

            @apiParam {String} token Token.
            @apiParam {json} data json values
            @apiParamExample {json} Request-Example:
            {
                "token":"cQQ4u07DsUKBjCzJdG1DZy7RDnvPeEVnnfidHob_EQw.9JCUQFEdzVGdiojIkJ3b3N3chBnIsUTNxojIkl2XyV2c1Jye.9JiN1IzUIJiOicGbhJCLiQ1VKJiOiAXe0Jye",
                "data":
                {
                    "co_applicant" : "Mary Johnson.",
                    "appointment_id": 171
                }
            }

            @apiSuccessExample {json} Success-Response:
            HTTP/1.1 200 OK
            {
                "result": "Success",
                "message": "Appointment Update Success",
                "override_json_result": 1
            }
            @apiErrorExample {json} Error-Response:
            HTTP/1.1 200 OK
            {
                "result": "AuthFailed",
                "message": "You have been logged into another device using the same account. Please login again.",
                "token": 1
            }

            @apiError (Error Code) {Number} 500 Internal Server Error.

            @apiSampleRequest off
        """
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', '')
        data = params.get('data', {})
        result = {}
        if not token:
            _logger.info("------------Token Missing in update_appointments api------------------")
            return json.dumps({'override_json_result':1, 'result': 'Failed', 'message': 'Empty token.'})
        if not data:
            _logger.info("------------Data Missing in update_appointments api------------------")
            return json.dumps({'override_json_result':1, 'result': 'Failed', 'message': 'Empty Data.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in update_appointments api-------------------")
            return json.dumps({'override_json_result':1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in update_appointments api-------------------")
            return json.dumps({'override_json_result':1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            appointment = models.execute_kw(DB, int(uid), password, 'team.customer.appointment', 'update_appointment',
                                            [data])
            if appointment.get('result', False):
                result = {
                    'result': 'Success',
                    'message': appointment['message'],
                }
            else:
                result = {
                    'result': 'Failed',
                    'message': appointment['message'],
                }
        else:
            result = message
        result.update({'override_json_result':1})
        return json.dumps(result)

    @route('/api/filter_appointment', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def get_appointment_data(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        customer_name = params.get('customer_name', '')
        result = {}
        if not token:
            _logger.info("------------Token Missing in appointment_filter------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        if not customer_name:
            _logger.info("------------Customer Name is Missing in appointment_filter------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty customer_name.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in appointment_filter-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in appointment_filter-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                                 'get_appointment_data_filter', [{'customer_name': customer_name, 'user_id': int(uid)}])
        else:
            result = message
        return json.dumps(result)

    @route('/api/get_measurement_questions', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def get_measurement_questions(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        room_id = params.get('room_id', False)
        if not token:
            _logger.info("------------Token Missing in main question_measurement ------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        if not room_id:
            _logger.info("------------Room ID Missing in main question_measurement ------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Room ID.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main question_measurement-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main question_measurement-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            question_data_measurement = models.execute_kw(DB, int(uid), password, 'team.quote.question',
                                                          'get_question_data', [{'type':'show_in_measurement','room_id':room_id}])
            result = {
                'result': 'Success',
                'questions_measurement': question_data_measurement,
                'message': '',
            }
        else:
            result = message
        return json.dumps(result)

    @route('/api/get_contract_questions', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def get_contract_questions(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        room_id = params.get('room_id', False)
        if not token:
            _logger.info("------------Token Missing in main question_contract ------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        if not room_id:
            _logger.info("------------Room ID Missing in main question_contract ------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Room ID.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main question_contract-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main question_contract-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:

            question_data_contract = models.execute_kw(DB, int(uid), password, 'team.quote.question',
                                                       'get_question_data', [{'type':'show_in_contract','room_id':room_id}])
            result = {
                'result': 'Success',
                'questions_contract': question_data_contract,
                'message': '',
            }
        else:
            result = message
        return json.dumps(result)

    @route('/api/add_contract_measurement_questions', type='json', auth="none", methods=['POST'], csrf=False,allow_none=True, )
    def add_contract_measurement_questions(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', '')
        data = params.get('data', {})
        result = {}
        if not token:
            _logger.info("------------Token Missing in contract_measurement_questions------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        if not data:
            _logger.info("------------data Missing in contract_measurement_questions------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty data.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in contract_measurement_questions-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in contract_measurement_questions-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.contract.question.line', 'create_contract_questions',
                                       [data])
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/list_contract_measurement_questions', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def list_contract_measurement_questions(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        appointment_id = params.get('appointment_id', '')
        room_id = params.get('room_id', '')
        room_measurement_id = params.get('room_measurement_id', '')

        result = {}
        if not token:
            _logger.info("------------Token Missing in list_contract_measurement_questions------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        if not appointment_id:
            _logger.info("------------Appointment ID is Missing in list_contract_measurement_questions------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID.'})
        if not room_id:
            _logger.info("------------Room ID is Missing in list_contract_measurement_questions------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Room ID.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in list_contract_measurement_questions-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in list_contract_measurement_questions-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.contract.question.line','list_contract_question_line',[{'appointment_id': appointment_id,'room_id': room_id,'room_measurement_id':room_measurement_id}])
        else:
            result = message
        return json.dumps(result)

    @route('/api/update_contract_measurement_questions', type='json', auth="none", methods=['POST'], csrf=False,allow_none=True, )
    def update_contract_measurement_questions(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        token = params.get('token', '')
        data = params.get('data', [])
        result = {}
        if not token:
            _logger.info("------------Token Missing in update_contract_measurement_questions------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        if not data:
            _logger.info("------------Data Missing in update_contract_measurement_questions------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty Data.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in update_contract_measurement_questions-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in update_contract_measurement_questions-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            questions = models.execute_kw(DB, int(uid), password,'team.contract.question.line',
                                            'update_contract_question_line',
                                            [data])
            if questions.get('result', False):
                result = {
                    'result': 'Success',
                    'message': questions['message'],
                    'question_answer_ids':questions['question_answer_ids']
                }
            else:
                result = {
                    'result': 'Failed',
                    'message': questions['message'],
                }
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    # Unlink Attachment
    @route('/api/UnlinkAttachment', type='json', auth="none", methods=['POST'], csrf=False)
    def unlink_attachment_api(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        if not token:
            _logger.info("------------Token Missing in main UnlinkAttachment api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        status, message = self.action_verify_token(uid, token)
        if status:
            if not data:
                return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty attachment_ids.'})
            result = models.execute_kw(DB, int(uid), password, 'ir.attachment', 'unlink_attachment_api',
                                     [data])
        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/add_contract_stair_room_measurement', type='http', auth="none", methods=['POST'], csrf=False,
           allow_none=True, )
    def add_contract_stair_room_measurement(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        appointment_id = int(params.get('appointment_id', 0))
        room_id = int(params.get('room_id', 0))
        room_measurement_id = int(params.get('room_measurement_id', 0))
        result = {}
        if not token:
            _logger.info("------------Token Missing in add_contract_room_measurement------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in add_contract_room_measurement-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in add_contract_room_measurement-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line',
                                       'create_stair_room_measurement', [{
                    'appointment_id': appointment_id,
                    'room_id': room_id,
                    'room_measurement_id': room_measurement_id,
                }])
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/add_contract_room_measurement', type='http', auth="none", methods=['POST'], csrf=False,allow_none=True, )
    def add_contract_room_measurement(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        appointment_id = int(params.get('appointment_id',0))
        room_id = int(params.get('room_id', 0))
        room_measurement_id = int(params.get('room_measurement_id', 0))
        room_area = float(params.get('room_area', 0))
        room_perimeter = float(params.get('room_perimeter', 0))
        file = params.get('attachment', False)
        _logger.info("------------add_contract_room_measurement params: %s------------------"%(params))
        data=[]
        file_data = {}
        transitions = []
        if params.get('transition1_name', '') and params.get('transition1_width'):
            transitions.append({
                'transition_type': params.get('transition1_name', ''),
                'transition_width': params.get('transition1_width', ''),
            })
        if params.get('transition2_name', '') and params.get('transition2_width'):
            transitions.append({
                'transition_type': params.get('transition2_name', ''),
                'transition_width': params.get('transition2_width', ''),
            })
        if params.get('transition3_name', '') and params.get('transition3_width'):
            transitions.append({
                'transition_type': params.get('transition3_name', ''),
                'transition_width': params.get('transition3_width', ''),
            })
        if params.get('transition4_name', '') and params.get('transition4_width'):
            transitions.append({
                'transition_type': params.get('transition4_name', ''),
                'transition_width': params.get('transition4_width', ''),
            })
        result = {}
        image_id=0
        if not token:
            _logger.info("------------Token Missing in add_contract_room_measurement------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in add_contract_room_measurement-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in add_contract_room_measurement-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:

            if not file:
                return json.dumps({'result': 'Failed', 'message': 'Empty attachment in values.'})

            if type(file) == werkzeug.datastructures.FileStorage:
                image_binary = (file.read())
                file_data.update(
                    {'uid': int(uid), 'image': base64.b64encode(image_binary).decode('utf-8'), 'file_name': file.filename})
                data = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'ir.attachment', 'create_attachment',
                                         [file_data])
            if data:
                image_id = data[0].get('id',False)
            result = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line',
                                       'create_room_measurement',
                                       [{'appointment_id': appointment_id, 'room_id': room_id,
                                         'room_area':room_area,'shape_image_id':image_id,'room_measurement_id':room_measurement_id, 'room_perimeter': room_perimeter, 'transitions': transitions}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/update_contract_room_measurement', type='http', auth="none", methods=['POST'], csrf=False,allow_none=True, )
    def update_contract_room_measurement(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        contract_measurement_id = int(params.get('contract_measurement_id',0))
        comments = params.get('comments','')
        name = params.get('name', '')
        adjusted_area = float(params.get('adjusted_area',0))
        result = {}
        file = params.get('attachment', False)
        file_data = {}
        image_id=0
        image=[]
        if not token:
            _logger.info("------------Token Missing in update_contract_room_measurement------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in update_contract_room_measurement-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in update_contract_room_measurement-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            if file:
                if type(file) == werkzeug.datastructures.FileStorage:
                    image_binary = (file.read())
                    file_data.update(
                        {'uid': int(uid), 'image': base64.encodestring(image_binary), 'file_name': file.filename})
                    image = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'ir.attachment', 'create_attachment',
                                             [file_data])
            if image:
                image_id = image[0].get('id',0)
            appointment = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line',
                                            'update_room_measurement',
                                            [{'contract_measurement_id':contract_measurement_id,'image_id':image_id,'adjusted_area':adjusted_area
                                              ,'comments':comments,'name':name}])
            if appointment.get('result', False):
                result = {
                    'result': 'Success',
                    'message': appointment['message'],
                }
            else:
                result = {
                    'result': 'Failed',
                    'message': appointment['message'],
                }
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/get_contract_room_measurement', type='http', auth="none", methods=['POST'], csrf=False,allow_none=True)
    def get_contract_room_measurement(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        appointment_id = params.get('appointment_id', '')
        room_id = params.get('room_id', '')
        room_measurement_id = params.get('room_measurement_id', '')
        result = {}
        if not token:
            _logger.info("------------Token Missing in get_contract_room_measurement------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        if not appointment_id:
            _logger.info("------------Appointment ID is Missing in get_contract_room_measurement------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID.'})
        if not room_id:
            _logger.info("------------Room ID is Missing in get_contract_room_measurement------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Room ID.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in get_contract_room_measurement-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in get_contract_room_measurement-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line',
                                       'list_room_measurement',
                                       [{'appointment_id': appointment_id,'room_id': room_id,'room_measurement_id':room_measurement_id}])
        else:
            result = message
        return json.dumps(result)

    @route('/api/get_overall_room_summary', type='http', auth="none", methods=['POST'], csrf=False,allow_none=True)
    def get_overall_room_summary(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        appointment_id = params.get('appointment_id', '')
        result = {}
        if not token:
            _logger.info("------------Token Missing in get_overall_room_summary------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        if not appointment_id:
            _logger.info("------------Appointment ID is Missing in get_overall_room_summary------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in get_overall_room_summary-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in get_overall_room_summary-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line',
                                       'list_overall_room_summary',
                                       [{'appointment_id': appointment_id}])
        else:
            result = message
        return json.dumps(result)

    @route('/api/remove_contract_question_line', type='json', auth="none", methods=['POST'], csrf=False)
    def remove_contract_question_api(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        if not token:
            _logger.info("------------Token Missing in main remove_contract_question api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)

        status, message = self.action_verify_token(uid, token)
        if status:
            if not data:
                return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty Contract Question IDS.'})
            result = models.execute_kw(DB, int(uid), password, 'team.contract.question.line', 'remove_contract_question_line',
                                       [data])
        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/remove_contract_room_measurement_line', type='json', auth="none", methods=['POST'], csrf=False)
    def remove_contract_room_measurement_api(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        if not token:
            _logger.info("------------Token Missing in remove_contract_room_measurement_api ------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)

        status, message = self.action_verify_token(uid, token)
        if status:
            if not data:
                return json.dumps(
                    {'override_json_result': 1, 'result': 'Failed', 'message': 'Empty Contract Room Measurement IDS.'})
            result = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line',
                                       'remove_contract_room_measurement_line',
                                       [data])
        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/edit_contract_room_measurement_line', type='json', auth="none", methods=['POST'], csrf=False)
    def edit_contract_room_measurement_line(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        if not token:
            _logger.info("------------Token Missing in edit_contract_room_measurement_api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)

        status, message = self.action_verify_token(uid, token)
        if status:
            if not data:
                return json.dumps(
                    {'override_json_result': 1, 'result': 'Failed', 'message': 'Empty Contract Room Measurement IDS.'})
            result = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line',
                                       'edit_contract_room_measurement_line',
                                       [data])
        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/list_contract_room_measurement_line', type='json', auth="none", methods=['POST'], csrf=False)
    def list_contract_room_measurement_line(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        if not token:
            _logger.info("------------Token Missing in list_contract_room_measurement_api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)

        status, message = self.action_verify_token(uid, token)
        if status:
            if not data:
                return json.dumps(
                    {'override_json_result': 1, 'result': 'Failed', 'message': 'Empty Contract Room Measurement IDS.'})
            result = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line',
                                       'list_contract_room_measurement_line',
                                       [data])

        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)


    @route('/api/summary_contract_room_measurement_line', type='json', auth="none", methods=['POST'], csrf=False)
    def summary_contract_room_measurement_line(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        if not token:
            _logger.info("------------Token Missing in Summary Contract Room_Measurement_Line------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)

        status, message = self.action_verify_token(uid, token)
        if status:
            if not data:
                return json.dumps(
                    {'override_json_result': 1, 'result': 'Failed', 'message': 'Empty Contract Room Measurement IDS.'})
            result = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line',
                                       'summary_contract_room_measurement_line',
                                       [data])
        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    # Create Sale Quotation
    @route('/api/create_sale_quotation', type='json', auth="none", methods=['POST'], csrf=False)
    def create_sale_quotation(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        appointment_id = data.get('appointment_id', '')
        floor_type = data.get('floor_type', '')
        if not token:
            _logger.info("------------Token Missing in main Create Sale Order api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        status, message = self.action_verify_token(uid, token)
        if status:
            if not appointment_id and not floor_type:
                return json.dumps(
                    {'override_json_result': 1, 'result': 'Failed', 'message': 'Empty appointment_id or floor_type.'})
            result = models.execute_kw(DB, int(uid), password, 'sale.order',
                                       'create_sale_quotation_api',
                                       [data])
        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/update_summary_contract_room_measurement_line', type='json', auth="none", methods=['POST'], csrf=False)
    def update_summary_contract_room_measurement_line(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        if not token:
            _logger.info("------------Token Missing in update_summary_contract_room_measurement_line------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)

        status, message = self.action_verify_token(uid, token)
        if status:
            if not data:
                return json.dumps(
                    {'override_json_result': 1, 'result': 'Failed', 'message': 'Empty Contract Room Measurement IDS.'})
            result = models.execute_kw(DB, int(uid), password, 'team.contract.room.measurement.line',
                                       'update_summary_contract_room_measurement',
                                       [data])
        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/create_payment_transaction', type='json', auth="none", methods=['POST'], csrf=False)
    def create_payment_transaction(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        if not token:
            _logger.info("------------Token Missing in create_payment_transaction ------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.payment.transaction.line',
                                       'create_payment_transaction',
                                       [data])
        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/create_payment_transaction_cash', type='json', auth="none", methods=['POST'], csrf=False)
    def create_payment_transaction_cash(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        if not token:
            _logger.info("------------Token Missing in  create_payment_transaction_cash------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'sale.order',
                                       'create_payment_transaction_cash',
                                       [data])
        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/create_payment_transaction_card', type='json', auth="none", methods=['POST'], csrf=False)
    def create_payment_transaction_card(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        if not token:
            _logger.info("------------Token Missing in  create_payment_transaction_card------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'sale.order',
                                       'create_payment_transaction_card',
                                       [data])
        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/create_payment_transaction_check', type='json', auth="none", methods=['POST'], csrf=False)
    def create_payment_transaction_check(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        if not token:
            _logger.info("------------Token Missing in  create_payment_transaction_checkh------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'sale.order',
                                       'create_payment_transaction_check',
                                       [data])
        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)


    @route('/api/check_document_status', type='http', auth="none", methods=['POST'], csrf=False,allow_none=True)
    def check_document_status(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        sale_order_id = params.get('sale_order_id', False)
        if not sale_order_id:
            _logger.info(
                "------------Sale Order ID  Missing in main check_document_status api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID'})
        if not token:
            _logger.info("------------Token Missing in main check_document_status api api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main  check_document_status api api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main check_document_status api api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'sale.order', 'check_document_status',
                                       [{'sale_order_id': sale_order_id}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/propose_reject_quote', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def propose_reject_quote(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        sale_order_id = params.get('sale_order_id', False)
        order_status = params.get('status', False)
        if not sale_order_id:
            _logger.info(
                "------------Sale Order ID  Missing in propose_reject_quote api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty sale order  ID'})
        if not order_status:
            _logger.info(
                "------------status  Missing in main propose_reject_quote api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty status parameter'})
        if not token:
            _logger.info("------------Token Missing in main propose_reject_quote api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main propose_reject_quote api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main propose_reject_quote api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'sale.order', 'propose_reject_quote',
                                       [{'sale_order_id': sale_order_id,'status':order_status}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/add_applicant_signature', type='http', auth="none", methods=['POST'], csrf=False,allow_none=True, )
    def add_applicant_signature(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        appointment_id = params.get('appointment_id', 0)
        credit_card = params.get('credit_card', 0)
        finance_application = params.get('finance_application', 0)
        contract = params.get('contract', 0)
        applicant_signature = params.get('applicant_signature', False)
        co_applicant_signature = params.get('co_applicant_signature', False)
        applicant_initial = params.get('applicant_initial', False)
        co_applicant_initial = params.get('co_applicant_initial', False)

        data = []
        file_data = {}
        result = {}
        applicant_signature_id = 0
        co_applicant_signature_id = 0
        applicant_initial_id = 0
        co_applicant_initial_id = 0

        if not token:
            _logger.info("------------Token Missing in add_contract_room_measurement------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in add_contract_room_measurement-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in add_contract_room_measurement-------------------")
            return json.dumps(
                {'override_json_result': 1, 'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:


            if applicant_signature:
                if type(applicant_signature) == werkzeug.datastructures.FileStorage:
                    image_binary = (applicant_signature.read())
                    file_data.update(
                        {'uid': int(uid), 'image': base64.b64encode(image_binary).decode('utf-8'),
                         'file_name': applicant_signature.filename})
                    applicant_signature_data = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'ir.attachment',
                                                                 'create_attachment',
                                                                 [file_data])
                if applicant_signature_data:
                    applicant_signature_id = applicant_signature_data[0].get('id', False)

            if co_applicant_signature:
                if type(co_applicant_signature) == werkzeug.datastructures.FileStorage:
                    image_binary = (co_applicant_signature.read())
                    file_data.update(
                        {'uid': int(uid), 'image': base64.b64encode(image_binary).decode('utf-8'),
                         'file_name': co_applicant_signature.filename})
                    co_applicant_signature_data = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'ir.attachment',
                                                                    'create_attachment',
                                                                    [file_data])
                if co_applicant_signature_data:
                    co_applicant_signature_id = co_applicant_signature_data[0].get('id', False)

            if applicant_initial:
                if type(applicant_initial) == werkzeug.datastructures.FileStorage:
                    image_binary = (applicant_initial.read())
                    file_data.update(
                        {'uid': int(uid), 'image': base64.b64encode(image_binary).decode('utf-8'),
                         'file_name': applicant_initial.filename})
                    applicant_initial_data = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'ir.attachment',
                                                                 'create_attachment',
                                                                 [file_data])
                if applicant_initial_data:
                    applicant_initial_id = applicant_initial_data[0].get('id', False)

            if co_applicant_initial:
                if type(co_applicant_initial) == werkzeug.datastructures.FileStorage:
                    image_binary = (co_applicant_initial.read())
                    file_data.update(
                        {'uid': int(uid), 'image': base64.b64encode(image_binary).decode('utf-8'),
                         'file_name': co_applicant_initial.filename})
                    co_applicant_initial_data = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'ir.attachment',
                                                                    'create_attachment',
                                                                    [file_data])
                if co_applicant_initial_data:
                    co_applicant_initial_id = co_applicant_initial_data[0].get('id', False)


            result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                       'add_applicant_signature',
                                       [{'appointment_id': appointment_id,
                                         'finance_application': finance_application,
                                         'credit_card': credit_card,
                                         'contract': contract,
                                         'applicant_signature_id': applicant_signature_id,
                                         'co_applicant_signature_id': co_applicant_signature_id,
                                         'applicant_initial_id':applicant_initial_id,
                                         'co_applicant_initial_id':co_applicant_initial_id
                                         }]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/create_credit_application', type='json', auth="none", methods=['POST'], csrf=False)
    def create_credit_application(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        # params = request.jsonrequest.copy()
        params = request.httprequest.get_json()
        params = dict(params)
        token = params.get('token', False)
        data = params.get('data', False)
        if not token:
            _logger.info("------------Token Missing in  create_credit_application api------------------")
            return json.dumps({'override_json_result': 1, 'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'sale.order',
                                       'create_credit_application',
                                       [data])
        else:
            _logger.info("------------Token validation failed------------------")
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/list_credit_application', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def list_credit_application(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        appointment_id = params.get('appointment_id', False)
        if not appointment_id:
            _logger.info(
                "------------Appointment ID  Missing in main list_credit_application api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID'})
        if not token:
            _logger.info("------------Token Missing in main list_credit_application api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main  list_credit_application api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main list_credit_application api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'sale.order', 'list_credit_application',
                                       [{'appointment_id': appointment_id}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/list_applicant_signature', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def list_applicant_signature(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        appointment_id = params.get('appointment_id', False)
        if not appointment_id:
            _logger.info(
                "------------Appointment ID  Missing in main list_credit_application api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID'})
        if not token:
            _logger.info("------------Token Missing in main list_credit_application api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main  list_credit_application api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main list_credit_application api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'sale.order', 'list_applicant_signature',
                                       [{'appointment_id': appointment_id}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)


    @route('/api/get_contract_document_status', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def get_contract_document_status(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        sale_order_id = params.get('sale_order_id', False)
        _logger.info('--/api/get_contract_document_status params: %s'%(params))
        if not sale_order_id:
            _logger.info("------------sale_order  ID  Missing in main get_contract_document_status api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Sale Order ID'})
        if not token:
            _logger.info("------------Token Missing in main get_contract_document_status api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main  get_contract_document_status api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main get_contract_document_status api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'sale.order', 'get_contract_document_status',
                                       [{'sale_order_id': sale_order_id}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/capture_payment', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def capture_payment(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        sale_order_id = params.get('sale_order_id', False)
        if not sale_order_id:
            _logger.info("------------sale_order  ID  Missing in main capture_payment api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Sale Order ID'})
        if not token:
            _logger.info("------------Token Missing in main capture_payment api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main  capture_payment api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main capture_payment api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'sale.order', 'capture_payment',
                                       [{'sale_order_id': sale_order_id}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/generate_credit_application', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def generate_credit_application(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        appointment_id = params.get('appointment_id', False)
        if not appointment_id:
            _logger.info(
                "------------Appointment ID  Missing in main generate_credit_application api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID'})
        if not token:
            _logger.info("------------Token Missing in main generate_credit_application api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main  generate_credit_application api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main generate_credit_application api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'sale.order', 'generate_credit_application',
                                       [{'appointment_id': appointment_id}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/get_appointment_result', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def get_appointment_result(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        if not token:
            _logger.info("------------Token Missing in main get_appointment_result api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main  get_appointment_result api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main get_appointment_result api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment', 'get_appointment_result',
                                       [int(uid)]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/submit_appointment_result', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def submit_appointment_result(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        result = params.get('result', False)
        appointment_id = params.get('appointment_id', False)
        if not appointment_id:
            _logger.info(
                "------------Appointment ID  Missing in main submit_appointment_result api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID'})
        if not result:
            _logger.info("------------Result Missing in main submit_appointment_result api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty  Value for parameter result'})
        if not token:
            _logger.info("------------Token Missing in main submit_appointment_result api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main  submit_appointment_result api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main submit_appointment_result api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment', 'submit_appointment_result',
                                       [{'result': result,'appointment_id':appointment_id}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/sync_master_data', type='http', auth="none", methods=['POST'], csrf=False)
    def sync_master_data(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        result = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'team.improveit.configuration', 'action_sync_master_data',[{}])
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/capture_payment_without_upload', type='http', auth="none", methods=['POST'], csrf=False, allow_none=True)
    def capture_payment_without_upload(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        sale_order_id = params.get('sale_order_id', False)
        if not sale_order_id:
            _logger.info("------------sale_order  ID  Missing in main capture_payment api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Sale Order ID'})
        if not token:
            _logger.info("------------Token Missing in main capture_payment api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main  capture_payment api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main capture_payment api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'sale.order', 'capture_payment_without_upload',
                                       [{'sale_order_id': sale_order_id}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/do_file_upload', type='http', auth="none", methods=['POST'], csrf=False)
    def do_file_upload(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        sale_order_id = params.get('sale_order_id', False)
        if not sale_order_id:
            _logger.info("------------sale_order  ID  Missing in main do_file_upload api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Sale Order ID'})
        if not token:
            _logger.info("------------Token Missing in main do_file_upload api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main  do_file_upload api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main do_file_upload api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'sale.order', 'action_do_file_upload',
                                       [{'sale_order_id': sale_order_id}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/submit_appointment_result_without_upload', type='http', auth="none", methods=['POST'], csrf=False,
           allow_none=True)
    def submit_appointment_result_without_upload(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        result = params.get('result', False)
        what_happened_notes = params.get('what_happened_notes', '')
        whats_next_notes = params.get('whats_next_notes', '')
        appointment_id = params.get('appointment_id', False)
        if not appointment_id:
            _logger.info(
                "------------Appointment ID  Missing in main submit_appointment_result api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID'})
        if not result:
            _logger.info("------------Result Missing in main submit_appointment_result api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty  Value for parameter result'})
        if not what_happened_notes:
            _logger.info("------------What Happened Notes Missing in main submit_appointment_result api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty  Value for What Happened Notes'})
        if not params.get('last_price_quoted_value'):
            _logger.info("------------Whats Next Notes Missing in main submit_appointment_result api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty  Value for Last Price Quoted Value'})
        if not whats_next_notes:
            _logger.info("------------Whats Next Notes Missing in main submit_appointment_result api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty  Value for Whats Next Notes'})
        if not token:
            _logger.info("------------Token Missing in main submit_appointment_result api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main  submit_appointment_result api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main submit_appointment_result api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            param_vals = {
                'result': result,
                'what_happened_notes': what_happened_notes,
                'whats_next_notes': whats_next_notes,
                'appointment_id': appointment_id,
                'last_price_quoted_value': params.get('last_price_quoted_value') if 'last_price_quoted_value' in params else 0,
            }
            result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                       'submit_appointment_result_without_upload',
                                       [param_vals]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/submit_appointment_file_upload', type='http', auth="none", methods=['POST'], csrf=False,
           allow_none=True)
    def submit_appointment_file_upload(self, **kwargs):
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', False)
        appointment_id = params.get('appointment_id', False)
        if not appointment_id:
            _logger.info(
                "------------Appointment ID  Missing in main submit_appointment_result api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty Appointment ID'})
        if not token:
            _logger.info("------------Token Missing in main submit_appointment_result api------------------")
            return json.dumps({'result': 'Failed', 'message': 'Empty token.'})
        uid, password = self.get_credentials(token)
        if not uid:
            _logger.info("------------uid missing in main  submit_appointment_result api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Token validation Failed', 'token': 1})
        if not password:
            _logger.info("------------password missing in main submit_appointment_result api-------------------")
            return json.dumps({'result': 'Failed', 'message': 'Password validation Failed', 'token': 1})
        status, message = self.action_verify_token(uid, token)
        if status:
            result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment',
                                       'submit_appointment_file_upload',
                                       [{'appointment_id': appointment_id}]
                                       )
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)

    @route('/api/add_screenshots', type='http', auth="none", methods=['POST'], csrf=False,allow_none=True, )
    def add_screenshots(self, **kwargs):
        """
            add_screenshots
            @api {POST}/api/add_screenshots Upload Snapshots
            @apiVersion 1.0.0
            @apiName add_screenshots
            @apiGroup Salesman
            @apiDescription To upload the napshots captured to the system

            @apiParam {String} token Token.
            @apiParam {File} attachment Files to be uploaded.
            @apiParam {Integer} appointment_id Attachment Reference.
            @apiParamExample {form-data} Request-Example:
            token:cQQ4u07DsUKBjCzJdG1DZy7RDnvPeEVnnfidHob_EQw.9JCUQFEdzVGdiojIkJ3b3N3chBnIsUTNxojIkl2XyV2c1Jye.9JiN1IzUIJiOicGbhJCLiQ1VKJiOiAXe0Jye
            attachment: Image.jpg
            appointment_id: 2172
            @apiSuccessExample {json} Success-Response:
             HTTP/1.1 200 OK
             {
                "result": "Success",
                "attachment_id": 2435,
                "message": "Snapshot uploaded successfully"
            }

            @apiErrorExample {json} Error-Response:
             HTTP/1.1 200 OK
            {
                "result": "Failed",
                "message": "Empty Appointment id"
            }

            @apiError (Error Code) {Number} 500 Internal Server Error.

            @apiSampleRequest off
        """
        models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(URL))
        params = request.params.copy()
        token = params.get('token', '')
        appointment_id = params.get('appointment_id',0) and int(params.get('appointment_id',0)) or False
        file = params.get('attachment', False)
        _logger.info("------------add_screenshots params: %s------------------"%(params))
        data=[]
        result = {}
        file_data = {}
        image_id = 0
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
        if status:

            if not file:
                return json.dumps({'result': 'Failed', 'message': 'Empty attachment in values.'})

            if type(file) == werkzeug.datastructures.FileStorage:
                image_binary = (file.read())
                file_data.update(
                    {'uid': int(uid), 'image': base64.b64encode(image_binary).decode('utf-8'), 'file_name': file.filename})
                data = models.execute_kw(DB, API_USER_ID, API_USER_PASSWORD, 'ir.attachment', 'create_attachment',
                                         [file_data])
            if data:
                image_id = data[0].get('id', False)
            result = models.execute_kw(DB, int(uid), password, 'team.customer.appointment', 'add_screenshots',
                                       [{'appointment_id': appointment_id, 'attachment_id': image_id}])
        else:
            result = message
        result.update({'override_json_result': 1})
        return json.dumps(result)
