# fusion_refloor.CommissionsServicesApi

All URIs are relative to *http://localhost:8080*

Method | HTTP request | Description
------------- | ------------- | -------------
[**commission_resource_calculate**](CommissionsServicesApi.md#commission_resource_calculate) | **POST** /commissions | Calculate commision
[**commission_resource_get_commission**](CommissionsServicesApi.md#commission_resource_get_commission) | **GET** /commissions/{saleId} | Get commission
[**commission_resource_get_commission_order**](CommissionsServicesApi.md#commission_resource_get_commission_order) | **GET** /commissions/{saleId}/mapped | Get commission


# **commission_resource_calculate**
> CommissionResponse commission_resource_calculate(commission_request=commission_request)

Calculate commision

### Example

* Bearer (Opaque) Authentication (SecurityScheme):

```python
import fusion_refloor
from fusion_refloor.models.commission_request import CommissionRequest
from fusion_refloor.models.commission_response import CommissionResponse
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
    api_instance = fusion_refloor.CommissionsServicesApi(api_client)
    commission_request = fusion_refloor.CommissionRequest() # CommissionRequest |  (optional)

    try:
        # Calculate commision
        api_response = api_instance.commission_resource_calculate(commission_request=commission_request)
        print("The response of CommissionsServicesApi->commission_resource_calculate:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling CommissionsServicesApi->commission_resource_calculate: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **commission_request** | [**CommissionRequest**](CommissionRequest.md)|  | [optional] 

### Return type

[**CommissionResponse**](CommissionResponse.md)

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

# **commission_resource_get_commission**
> CommissionResponse commission_resource_get_commission(sale_id)

Get commission

### Example

* Bearer (Opaque) Authentication (SecurityScheme):

```python
import fusion_refloor
from fusion_refloor.models.commission_response import CommissionResponse
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
    api_instance = fusion_refloor.CommissionsServicesApi(api_client)
    sale_id = 'sale_id_example' # str | 

    try:
        # Get commission
        api_response = api_instance.commission_resource_get_commission(sale_id)
        print("The response of CommissionsServicesApi->commission_resource_get_commission:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling CommissionsServicesApi->commission_resource_get_commission: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **sale_id** | **str**|  | 

### Return type

[**CommissionResponse**](CommissionResponse.md)

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

# **commission_resource_get_commission_order**
> SoldOrder commission_resource_get_commission_order(sale_id)

Get commission

### Example

* Bearer (Opaque) Authentication (SecurityScheme):

```python
import fusion_refloor
from fusion_refloor.models.sold_order import SoldOrder
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
    api_instance = fusion_refloor.CommissionsServicesApi(api_client)
    sale_id = 'sale_id_example' # str | 

    try:
        # Get commission
        api_response = api_instance.commission_resource_get_commission_order(sale_id)
        print("The response of CommissionsServicesApi->commission_resource_get_commission_order:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling CommissionsServicesApi->commission_resource_get_commission_order: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **sale_id** | **str**|  | 

### Return type

[**SoldOrder**](SoldOrder.md)

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

