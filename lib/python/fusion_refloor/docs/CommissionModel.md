# CommissionModel


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**commission** | **Dict[str, object]** |  | [optional] 
**order** | **Dict[str, object]** |  | [optional] 

## Example

```python
from fusion_refloor.models.commission_model import CommissionModel

# TODO update the JSON string below
json = "{}"
# create an instance of CommissionModel from a JSON string
commission_model_instance = CommissionModel.from_json(json)
# print the JSON string representation of the object
print(CommissionModel.to_json())

# convert the object into a dict
commission_model_dict = commission_model_instance.to_dict()
# create an instance of CommissionModel from a dict
commission_model_from_dict = CommissionModel.from_dict(commission_model_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


