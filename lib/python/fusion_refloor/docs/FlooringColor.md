# FlooringColor


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**name** | **str** |  | [optional] 
**product_lines** | **str** |  | [optional] 
**thumbnail** | **str** |  | [optional] 
**color_upcharge** | **float** |  | [optional] 
**sales_app_display_name** | **str** |  | [optional] 
**in_stock** | **bool** |  | [optional] 
**glue_down** | **bool** |  | [optional] 

## Example

```python
from fusion_refloor.models.flooring_color import FlooringColor

# TODO update the JSON string below
json = "{}"
# create an instance of FlooringColor from a JSON string
flooring_color_instance = FlooringColor.from_json(json)
# print the JSON string representation of the object
print(FlooringColor.to_json())

# convert the object into a dict
flooring_color_dict = flooring_color_instance.to_dict()
# create an instance of FlooringColor from a dict
flooring_color_from_dict = FlooringColor.from_dict(flooring_color_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


