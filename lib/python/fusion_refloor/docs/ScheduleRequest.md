# ScheduleRequest


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** |  | [optional] 
**sale_id** | **str** |  | [optional] 
**sold_price** | **float** |  | [optional] 
**total_sqft** | **int** |  | [optional] 
**market_segment** | **str** |  | [optional] 
**sale_order_items** | [**List[OrderItem]**](OrderItem.md) |  | [optional] 
**proposed_start_date** | **date** |  | [optional] 
**proposed_end_date** | **date** |  | [optional] 

## Example

```python
from fusion_refloor.models.schedule_request import ScheduleRequest

# TODO update the JSON string below
json = "{}"
# create an instance of ScheduleRequest from a JSON string
schedule_request_instance = ScheduleRequest.from_json(json)
# print the JSON string representation of the object
print(ScheduleRequest.to_json())

# convert the object into a dict
schedule_request_dict = schedule_request_instance.to_dict()
# create an instance of ScheduleRequest from a dict
schedule_request_from_dict = ScheduleRequest.from_dict(schedule_request_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


