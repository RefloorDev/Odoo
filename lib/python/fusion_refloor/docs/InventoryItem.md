# InventoryItem


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** |  | [optional] 
**no** | **str** |  | [optional] 
**location_name** | **str** |  | [optional] 
**sqft_per_case** | **float** |  | [optional] 
**description** | **str** |  | [optional] 
**item_category_code** | **str** |  | [optional] 
**qoh** | **float** |  | [optional] 
**location_code** | **str** |  | [optional] 
**linear_ft_per_unit** | **float** |  | [optional] 

## Example

```python
from fusion_refloor.models.inventory_item import InventoryItem

# TODO update the JSON string below
json = "{}"
# create an instance of InventoryItem from a JSON string
inventory_item_instance = InventoryItem.from_json(json)
# print the JSON string representation of the object
print(InventoryItem.to_json())

# convert the object into a dict
inventory_item_dict = inventory_item_instance.to_dict()
# create an instance of InventoryItem from a dict
inventory_item_from_dict = InventoryItem.from_dict(inventory_item_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


