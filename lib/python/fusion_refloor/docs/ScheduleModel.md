# ScheduleModel


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**order** | [**Order**](Order.md) |  | [optional] 
**sale_order_items** | [**List[OrderItem]**](OrderItem.md) |  | [optional] 
**inventory_items** | [**List[InventoryItem]**](InventoryItem.md) |  | [optional] 
**purchase_order_items** | [**List[PurchaseOrderItem]**](PurchaseOrderItem.md) |  | [optional] 
**flooring_colors** | [**List[FlooringColor]**](FlooringColor.md) |  | [optional] 
**crews** | [**List[Crew]**](Crew.md) |  | [optional] 
**unavailability** | [**List[Unavailable]**](Unavailable.md) |  | [optional] 
**inventory_available** | **bool** |  | [optional] 
**color_not_in_stock** | **bool** |  | [optional] 
**glue_down_order** | **bool** |  | [optional] 
**total_stairs** | **int** |  | [optional] 

## Example

```python
from fusion_refloor.models.schedule_model import ScheduleModel

# TODO update the JSON string below
json = "{}"
# create an instance of ScheduleModel from a JSON string
schedule_model_instance = ScheduleModel.from_json(json)
# print the JSON string representation of the object
print(ScheduleModel.to_json())

# convert the object into a dict
schedule_model_dict = schedule_model_instance.to_dict()
# create an instance of ScheduleModel from a dict
schedule_model_from_dict = ScheduleModel.from_dict(schedule_model_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


