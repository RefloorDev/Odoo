# fusion_refloor.SchedulingServicesApi

All URIs are relative to *http://localhost:8080*

Method | HTTP request | Description
------------- | ------------- | -------------
[**schedule_existing_order**](SchedulingServicesApi.md#schedule_existing_order) | **POST** /scheduling/{saleId} | Schedule crews using existing order
[**schedule_new_order**](SchedulingServicesApi.md#schedule_new_order) | **POST** /scheduling | Schedule crews using populated order
[**scheduling_sale_id_get**](SchedulingServicesApi.md#scheduling_sale_id_get) | **GET** /scheduling/{saleId} | Get an existing order


# **schedule_existing_order**
> ScheduleResponse schedule_existing_order(sale_id)

Schedule crews using existing order

### Example

* Bearer (Opaque) Authentication (SecurityScheme):

```python
import time
import fusion_refloor
from fusion_refloor.api import scheduling_services_api
from fusion_refloor.model.schedule_response import ScheduleResponse
from fusion_refloor.model.schedule_request import ScheduleRequest
from pprint import pprint
# Defining the host is optional and defaults to http://localhost:8080
# See configuration.py for a list of all supported configuration parameters.
configuration = fusion_refloor.Configuration(
    host = "http://localhost:8080"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure Bearer authorization (Opaque): SecurityScheme
configuration = fusion_refloor.Configuration(
    access_token = 'YOUR_BEARER_TOKEN'
)

# Enter a context with an instance of the API client
with fusion_refloor.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = scheduling_services_api.SchedulingServicesApi(api_client)
    sale_id = "saleId_example" # str | 
    schedule_request = ScheduleRequest(
        id="id_example",
        sale_id="sale_id_example",
        sold_price=1,
        total_sqft=1,
        market_segment="market_segment_example",
        sale_order_items=[
            OrderItem(
                id="id_example",
                appliance_count=1,
                move_piano_pool_table="move_piano_pool_table_example",
                multiple_layers=1,
                open_stair_count=1,
                patch_leveling_required=True,
                pedestal_sink_rr=True,
                plywood_half_inch_sheets=1,
                plywood_quarter_inch_sheets=1,
                plywood_three_quarter_inch_sheets=1,
                primer_type="primer_type_example",
                room_sq_ft=1,
                stair_count=1,
                toilet_rr=True,
                true_self_leveling_required=True,
                vapor_barrier=1,
                sale="sale_example",
                bifold_door_count=1,
                build_up_leveling_required=1,
                product_selected="product_selected_example",
                bcid="bcid_example",
                molding_type="molding_type_example",
                current_covering_type="current_covering_type_example",
                remove_current_surface=True,
                available=True,
            ),
        ],
        proposed_start_date=dateutil_parser('Wed Mar 09 19:00:00 EST 2022').date(),
        proposed_end_date=dateutil_parser('Wed Mar 09 19:00:00 EST 2022').date(),
    ) # ScheduleRequest |  (optional)

    # example passing only required values which don't have defaults set
    try:
        # Schedule crews using existing order
        api_response = api_instance.schedule_existing_order(sale_id)
        pprint(api_response)
    except fusion_refloor.ApiException as e:
        print("Exception when calling SchedulingServicesApi->schedule_existing_order: %s\n" % e)

    # example passing only required values which don't have defaults set
    # and optional values
    try:
        # Schedule crews using existing order
        api_response = api_instance.schedule_existing_order(sale_id, schedule_request=schedule_request)
        pprint(api_response)
    except fusion_refloor.ApiException as e:
        print("Exception when calling SchedulingServicesApi->schedule_existing_order: %s\n" % e)
```


### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **sale_id** | **str**|  |
 **schedule_request** | [**ScheduleRequest**](ScheduleRequest.md)|  | [optional]

### Return type

[**ScheduleResponse**](ScheduleResponse.md)

### Authorization

[SecurityScheme](../README.md#SecurityScheme)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json


### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | OK |  -  |
**403** | Not Allowed |  -  |
**401** | Not Authorized |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **schedule_new_order**
> ScheduleResponse schedule_new_order()

Schedule crews using populated order

### Example

* Bearer (Opaque) Authentication (SecurityScheme):

```python
import time
import fusion_refloor
from fusion_refloor.api import scheduling_services_api
from fusion_refloor.model.schedule_response import ScheduleResponse
from fusion_refloor.model.schedule_request import ScheduleRequest
from pprint import pprint
# Defining the host is optional and defaults to http://localhost:8080
# See configuration.py for a list of all supported configuration parameters.
configuration = fusion_refloor.Configuration(
    host = "http://localhost:8080"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure Bearer authorization (Opaque): SecurityScheme
configuration = fusion_refloor.Configuration(
    access_token = 'YOUR_BEARER_TOKEN'
)

# Enter a context with an instance of the API client
with fusion_refloor.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = scheduling_services_api.SchedulingServicesApi(api_client)
    schedule_request = ScheduleRequest(
        id="id_example",
        sale_id="sale_id_example",
        sold_price=1,
        total_sqft=1,
        market_segment="market_segment_example",
        sale_order_items=[
            OrderItem(
                id="id_example",
                appliance_count=1,
                move_piano_pool_table="move_piano_pool_table_example",
                multiple_layers=1,
                open_stair_count=1,
                patch_leveling_required=True,
                pedestal_sink_rr=True,
                plywood_half_inch_sheets=1,
                plywood_quarter_inch_sheets=1,
                plywood_three_quarter_inch_sheets=1,
                primer_type="primer_type_example",
                room_sq_ft=1,
                stair_count=1,
                toilet_rr=True,
                true_self_leveling_required=True,
                vapor_barrier=1,
                sale="sale_example",
                bifold_door_count=1,
                build_up_leveling_required=1,
                product_selected="product_selected_example",
                bcid="bcid_example",
                molding_type="molding_type_example",
                current_covering_type="current_covering_type_example",
                remove_current_surface=True,
                available=True,
            ),
        ],
        proposed_start_date=dateutil_parser('Wed Mar 09 19:00:00 EST 2022').date(),
        proposed_end_date=dateutil_parser('Wed Mar 09 19:00:00 EST 2022').date(),
    ) # ScheduleRequest |  (optional)

    # example passing only required values which don't have defaults set
    # and optional values
    try:
        # Schedule crews using populated order
        api_response = api_instance.schedule_new_order(schedule_request=schedule_request)
        pprint(api_response)
    except fusion_refloor.ApiException as e:
        print("Exception when calling SchedulingServicesApi->schedule_new_order: %s\n" % e)
```


### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **schedule_request** | [**ScheduleRequest**](ScheduleRequest.md)|  | [optional]

### Return type

[**ScheduleResponse**](ScheduleResponse.md)

### Authorization

[SecurityScheme](../README.md#SecurityScheme)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json


### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | OK |  -  |
**403** | Not Allowed |  -  |
**401** | Not Authorized |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **scheduling_sale_id_get**
> ScheduleModel scheduling_sale_id_get(sale_id)

Get an existing order

### Example

* Bearer (Opaque) Authentication (SecurityScheme):

```python
import time
import fusion_refloor
from fusion_refloor.api import scheduling_services_api
from fusion_refloor.model.schedule_model import ScheduleModel
from pprint import pprint
# Defining the host is optional and defaults to http://localhost:8080
# See configuration.py for a list of all supported configuration parameters.
configuration = fusion_refloor.Configuration(
    host = "http://localhost:8080"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure Bearer authorization (Opaque): SecurityScheme
configuration = fusion_refloor.Configuration(
    access_token = 'YOUR_BEARER_TOKEN'
)

# Enter a context with an instance of the API client
with fusion_refloor.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = scheduling_services_api.SchedulingServicesApi(api_client)
    sale_id = "saleId_example" # str | 

    # example passing only required values which don't have defaults set
    try:
        # Get an existing order
        api_response = api_instance.scheduling_sale_id_get(sale_id)
        pprint(api_response)
    except fusion_refloor.ApiException as e:
        print("Exception when calling SchedulingServicesApi->scheduling_sale_id_get: %s\n" % e)
```


### Parameters

Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **sale_id** | **str**|  |

### Return type

[**ScheduleModel**](ScheduleModel.md)

### Authorization

[SecurityScheme](../README.md#SecurityScheme)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json


### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | OK |  -  |
**403** | Not Allowed |  -  |
**401** | Not Authorized |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

