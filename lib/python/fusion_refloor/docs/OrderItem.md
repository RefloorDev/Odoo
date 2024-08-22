# OrderItem


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** |  | [optional] 
**appliance_count** | **int** |  | [optional] 
**move_piano_pool_table** | **str** |  | [optional] 
**multiple_layers** | **int** |  | [optional] 
**open_stair_count** | **int** |  | [optional] 
**patch_leveling_required** | **bool** |  | [optional] 
**pedestal_sink_rr** | **bool** |  | [optional] 
**plywood_half_inch_sheets** | **int** |  | [optional] 
**plywood_quarter_inch_sheets** | **int** |  | [optional] 
**plywood_three_quarter_inch_sheets** | **int** |  | [optional] 
**primer_type** | **str** |  | [optional] 
**room_sq_ft** | **int** |  | [optional] 
**stair_count** | **int** |  | [optional] 
**toilet_rr** | **bool** |  | [optional] 
**true_self_leveling_required** | **bool** |  | [optional] 
**vapor_barrier** | **float** |  | [optional] 
**sale** | **str** |  | [optional] 
**bifold_door_count** | **int** |  | [optional] 
**build_up_leveling_required** | **int** |  | [optional] 
**product_selected** | **str** |  | [optional] 
**bcid** | **str** |  | [optional] 
**molding_type** | **str** |  | [optional] 
**current_covering_type** | **str** |  | [optional] 
**remove_current_surface** | **bool** |  | [optional] 
**available** | **bool** |  | [optional] 
**product_name** | **str** |  | [optional] 
**product_grade** | **str** |  | [optional] 
**non_commissionable_item_total** | **float** |  | [optional] 

## Example

```python
from fusion_refloor.models.order_item import OrderItem

# TODO update the JSON string below
json = "{}"
# create an instance of OrderItem from a JSON string
order_item_instance = OrderItem.from_json(json)
# print the JSON string representation of the object
print(OrderItem.to_json())

# convert the object into a dict
order_item_dict = order_item_instance.to_dict()
# create an instance of OrderItem from a dict
order_item_from_dict = OrderItem.from_dict(order_item_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


