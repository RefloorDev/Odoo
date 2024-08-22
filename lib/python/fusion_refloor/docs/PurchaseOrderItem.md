# PurchaseOrderItem


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** |  | [optional] 
**no** | **str** |  | [optional] 
**qpo** | **int** |  | [optional] 
**location_name** | **str** |  | [optional] 
**sqft_per_case** | **float** |  | [optional] 
**description** | **str** |  | [optional] 
**item_category_code** | **str** |  | [optional] 
**location_code** | **str** |  | [optional] 
**linear_ft_per_unit** | **float** |  | [optional] 

## Example

```python
from fusion_refloor.models.purchase_order_item import PurchaseOrderItem

# TODO update the JSON string below
json = "{}"
# create an instance of PurchaseOrderItem from a JSON string
purchase_order_item_instance = PurchaseOrderItem.from_json(json)
# print the JSON string representation of the object
print(PurchaseOrderItem.to_json())

# convert the object into a dict
purchase_order_item_dict = purchase_order_item_instance.to_dict()
# create an instance of PurchaseOrderItem from a dict
purchase_order_item_from_dict = PurchaseOrderItem.from_dict(purchase_order_item_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


