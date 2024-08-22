# fusion_refloor.SchedulingServicesApi

All URIs are relative to *http://localhost:8080*

Method | HTTP request | Description
------------- | ------------- | -------------
[**schedule_existing_order**](SchedulingServicesApi.md#schedule_existing_order) | **POST** /scheduling/{saleId} | Schedule crews using existing order
[**schedule_new_order**](SchedulingServicesApi.md#schedule_new_order) | **POST** /scheduling | Schedule crews using populated order
[**schedule_resource_get_order**](SchedulingServicesApi.md#schedule_resource_get_order) | **GET** /scheduling/{saleId} | Get an existing order


# **schedule_existing_order**
> ScheduleResponse schedule_existing_order(sale_id, schedule_request=schedule_request)

Schedule crews using existing order

### Example

* Bearer (Opaque) Authentication (SecurityScheme):

```python
import fusion_refloor
from fusion_refloor.models.schedule_request import ScheduleRequest
from fusion_refloor.models.schedule_response import ScheduleResponse
from fusion_refloor.rest import ApiException
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
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with fusion_refloor.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = fusion_refloor.SchedulingServicesApi(api_client)
    sale_id = 'sale_id_example' # str | 
    schedule_request = fusion_refloor.ScheduleRequest() # ScheduleRequest |  (optional)

    try:
        # Schedule crews using existing order
        api_response = api_instance.schedule_existing_order(sale_id, schedule_request=schedule_request)
        print("The response of SchedulingServicesApi->schedule_existing_order:\n")
        pprint(api_response)
    except Exception as e:
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
> ScheduleResponse schedule_new_order(schedule_request=schedule_request)

Schedule crews using populated order

### Example

* Bearer (Opaque) Authentication (SecurityScheme):

```python
import fusion_refloor
from fusion_refloor.models.schedule_request import ScheduleRequest
from fusion_refloor.models.schedule_response import ScheduleResponse
from fusion_refloor.rest import ApiException
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
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with fusion_refloor.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = fusion_refloor.SchedulingServicesApi(api_client)
    schedule_request = fusion_refloor.ScheduleRequest() # ScheduleRequest |  (optional)

    try:
        # Schedule crews using populated order
        api_response = api_instance.schedule_new_order(schedule_request=schedule_request)
        print("The response of SchedulingServicesApi->schedule_new_order:\n")
        pprint(api_response)
    except Exception as e:
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

# **schedule_resource_get_order**
> ScheduleModel schedule_resource_get_order(sale_id)

Get an existing order

### Example

* Bearer (Opaque) Authentication (SecurityScheme):

```python
import fusion_refloor
from fusion_refloor.models.schedule_model import ScheduleModel
from fusion_refloor.rest import ApiException
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
    access_token = os.environ["BEARER_TOKEN"]
)

# Enter a context with an instance of the API client
with fusion_refloor.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = fusion_refloor.SchedulingServicesApi(api_client)
    sale_id = 'sale_id_example' # str | 

    try:
        # Get an existing order
        api_response = api_instance.schedule_resource_get_order(sale_id)
        print("The response of SchedulingServicesApi->schedule_resource_get_order:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling SchedulingServicesApi->schedule_resource_get_order: %s\n" % e)
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

