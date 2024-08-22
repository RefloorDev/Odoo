# Order


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** |  | [optional] 
**market_segment** | **str** |  | [optional] 
**sale_id** | **str** |  | [optional] 
**total_sqft** | **int** |  | [optional] 
**total_stairs** | **int** |  | [optional] 
**glue_down_order** | **bool** |  | [optional] 
**additional_sale_comments** | **str** |  | [optional] 
**sold_price** | **float** |  | [optional] 
**payment_type** | **str** |  | [optional] 
**inventory_available** | **bool** |  | [optional] 

## Example

```python
from fusion_refloor.models.order import Order

# TODO update the JSON string below
json = "{}"
# create an instance of Order from a JSON string
order_instance = Order.from_json(json)
# print the JSON string representation of the object
print(Order.to_json())

# convert the object into a dict
order_dict = order_instance.to_dict()
# create an instance of Order from a dict
order_from_dict = Order.from_dict(order_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


