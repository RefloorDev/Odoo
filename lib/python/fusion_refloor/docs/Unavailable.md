# Unavailable


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** |  | [optional] 
**comments** | **str** |  | [optional] 
**assigned_to_name** | **str** |  | [optional] 
**assigned_to_phone** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**assigned_to_email** | **str** |  | [optional] 
**activity_type** | **str** |  | [optional] 
**assigned_to** | **str** |  | [optional] 
**market_segment** | **str** |  | [optional] 
**end_date** | **datetime** |  | [optional] 
**start_date** | **datetime** |  | [optional] 

## Example

```python
from fusion_refloor.models.unavailable import Unavailable

# TODO update the JSON string below
json = "{}"
# create an instance of Unavailable from a JSON string
unavailable_instance = Unavailable.from_json(json)
# print the JSON string representation of the object
print(Unavailable.to_json())

# convert the object into a dict
unavailable_dict = unavailable_instance.to_dict()
# create an instance of Unavailable from a dict
unavailable_from_dict = Unavailable.from_dict(unavailable_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


