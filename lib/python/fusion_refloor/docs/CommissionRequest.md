# CommissionRequest


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**sale_id** | **str** |  | [optional] 
**product_package** | **str** |  | [optional] 
**sold_price** | **float** |  | [optional] 
**list_price** | **float** |  | [optional] 
**lender_fees** | **float** |  | [optional] 
**loan_amount** | **float** |  | [optional] 
**below_list_percent** | **float** |  | [optional] 
**lender** | [**Lender**](Lender.md) |  | [optional] 
**rep_split** | **float** |  | [optional] 
**non_commissionable_total** | **float** |  | [optional] 

## Example

```python
from fusion_refloor.models.commission_request import CommissionRequest

# TODO update the JSON string below
json = "{}"
# create an instance of CommissionRequest from a JSON string
commission_request_instance = CommissionRequest.from_json(json)
# print the JSON string representation of the object
print(CommissionRequest.to_json())

# convert the object into a dict
commission_request_dict = commission_request_instance.to_dict()
# create an instance of CommissionRequest from a dict
commission_request_from_dict = CommissionRequest.from_dict(commission_request_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


