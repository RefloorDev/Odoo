# ScheduleResponse


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**market** | **str** |  | [optional] 
**start_date** | **datetime** |  | [optional] 
**end_date** | **datetime** |  | [optional] 
**crews** | [**List[ProposedCrew]**](ProposedCrew.md) |  | [optional] 
**model** | [**ScheduleModel**](ScheduleModel.md) |  | [optional] 

## Example

```python
from fusion_refloor.models.schedule_response import ScheduleResponse

# TODO update the JSON string below
json = "{}"
# create an instance of ScheduleResponse from a JSON string
schedule_response_instance = ScheduleResponse.from_json(json)
# print the JSON string representation of the object
print(ScheduleResponse.to_json())

# convert the object into a dict
schedule_response_dict = schedule_response_instance.to_dict()
# create an instance of ScheduleResponse from a dict
schedule_response_from_dict = ScheduleResponse.from_dict(schedule_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


