# SoldOrder


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
**list_price** | **float** |  | [optional] 
**loan_amount** | **float** |  | [optional] 
**buydown** | **float** |  | [optional] 
**rep_split** | **float** |  | [optional] 
**sales_rep1** | **str** |  | [optional] 
**lender** | [**Lender**](Lender.md) |  | [optional] 
**product_package** | **str** |  | [optional] 

## Example

```python
from fusion_refloor.models.sold_order import SoldOrder

# TODO update the JSON string below
json = "{}"
# create an instance of SoldOrder from a JSON string
sold_order_instance = SoldOrder.from_json(json)
# print the JSON string representation of the object
print(SoldOrder.to_json())

# convert the object into a dict
sold_order_dict = sold_order_instance.to_dict()
# create an instance of SoldOrder from a dict
sold_order_from_dict = SoldOrder.from_dict(sold_order_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


