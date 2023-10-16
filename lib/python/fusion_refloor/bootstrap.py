import datetime
import requests
import fusion_refloor
from pprint import pprint
from fusion_refloor.api import scheduling_services_api
from fusion_refloor.model.schedule_request import ScheduleRequest

# AUTH
FUSION_AUTH_URL = "https://sso.logicdrop.cloud/realms/refloor/protocol/openid-connect/token"
FUSION_AUTH_CLIENT_ID = 'refloor-app'
FUSION_AUTH_CLIENT_SECRET = '71PmpPk3s2axb8ein9ySoGXXsoF7ZERP'
FUSION_AUTH_GRANT_TYPE = 'client_credentials'

# API
FUSION_API_URL = 'https://api.logicdrop.cloud/services/v1/refloor/scheduling/gateway/8/~'

# Get OIDC Token
auth = requests.post(
    FUSION_AUTH_URL,
    data={
        "client_id": FUSION_AUTH_CLIENT_ID,
        "client_secret": FUSION_AUTH_CLIENT_SECRET,
        "grant_type": FUSION_AUTH_GRANT_TYPE,
        "Content-Type": "application/x-www-form-urlencoded"})
auth_json = auth.json()
auth_token = auth_json['access_token']
print(auth_token)

# Setup API configuration
configuration = fusion_refloor.Configuration(
    host=FUSION_API_URL,
    access_token=auth_token)
configuration.debug = True

# Make API call
# Enter a context with an instance of the API client
with fusion_refloor.ApiClient(configuration) as api_client:
    # Sale ID or Salesforce ID (required)
    SALE_ID = "a0f4V00000HZx7O"

    # Create an instance of the API class
    api_instance = scheduling_services_api.SchedulingServicesApi(api_client)

    # Request model (optional)
    model = ScheduleRequest()
    model.proposed_start_date = datetime.date.today()

    # Request schedule using an existing sales order
    try:
        api_response = api_instance.schedule_existing_order(
            SALE_ID,
            schedule_request=model)
        pprint(api_response)
    except fusion_refloor.ApiException as e:
        print("Exception when calling SchedulingServicesApi->schedule_existing_order: %s\n" % e)
