# CommissionResponse


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**amount** | **float** |  | [optional] 
**percent** | **float** |  | [optional] 
**sold_price_spiff** | **float** |  | [optional] 
**rep1_amount** | **float** |  | [optional] 
**rep2_amount** | **float** |  | [optional] 
**model** | [**CommissionModel**](CommissionModel.md) |  | [optional] 

## Example

```python
from fusion_refloor.models.commission_response import CommissionResponse

# TODO update the JSON string below
json = "{}"
# create an instance of CommissionResponse from a JSON string
commission_response_instance = CommissionResponse.from_json(json)
# print the JSON string representation of the object
print(CommissionResponse.to_json())

# convert the object into a dict
commission_response_dict = commission_response_instance.to_dict()
# create an instance of CommissionResponse from a dict
commission_response_from_dict = CommissionResponse.from_dict(commission_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


