# ProposedSlot


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**start_date** | **datetime** |  | [optional] 
**end_date** | **datetime** |  | [optional] 

## Example

```python
from fusion_refloor.models.proposed_slot import ProposedSlot

# TODO update the JSON string below
json = "{}"
# create an instance of ProposedSlot from a JSON string
proposed_slot_instance = ProposedSlot.from_json(json)
# print the JSON string representation of the object
print(ProposedSlot.to_json())

# convert the object into a dict
proposed_slot_dict = proposed_slot_instance.to_dict()
# create an instance of ProposedSlot from a dict
proposed_slot_from_dict = ProposedSlot.from_dict(proposed_slot_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


