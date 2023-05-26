# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


import logging

_logger = logging.getLogger(__name__)

_logger.info("Inside Config file=====================")

import odoo.tools as TOOLS
config = TOOLS.config

_logger.info("Configurations=================")
# This configurations are needs to be provided in the odoo.conf file
_logger.info(config.get('api_url',''))
_logger.info(config.get('api_db',''))
_logger.info(config.get('api_user_id',''))
_logger.info(config.get('api_user_password',''))

URL = config.get('api_url','')
DB = config.get('api_db','')
API_USER_ID = config.get('api_user_id','')
API_USER_PASSWORD = config.get('api_user_password','')
