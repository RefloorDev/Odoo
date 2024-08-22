# ProposedCrew


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**id** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**active** | **str** |  | [optional] 
**email** | **str** |  | [optional] 
**city** | **str** |  | [optional] 
**company_name** | **str** |  | [optional] 
**market_segment** | **str** |  | [optional] 
**mobile_phone** | **str** |  | [optional] 
**street_address1** | **str** |  | [optional] 
**state_province** | **str** |  | [optional] 
**sqft_per_day** | **int** |  | [optional] 
**sqft_per_week** | **int** |  | [optional] 
**works_saturday** | **bool** |  | [optional] 
**total_completed_installs** | **int** |  | [optional] 
**total_be_backs** | **int** |  | [optional] 
**percent_of_be_backs_to_installs** | **float** |  | [optional] 
**move_appliances** | **bool** |  | [optional] 
**rip_and_haul** | **bool** |  | [optional] 
**stairs** | **bool** |  | [optional] 
**leveling** | **bool** |  | [optional] 
**position_title** | **str** |  | [optional] 
**glue_down_installation** | **bool** |  | [optional] 
**date_certified** | **date** |  | [optional] 
**project_capabilities** | **str** |  | [optional] 
**plywood_and_subfloor_replacement** | **bool** |  | [optional] 
**baseboard_installation** | **bool** |  | [optional] 
**star_rating** | **float** |  | [optional] 
**attendance_violations** | **int** |  | [optional] 
**stairs_per_day** | **int** |  | [optional] 
**leveling_sqft** | **int** |  | [optional] 
**grade** | **str** |  | [optional] 
**slot** | [**ProposedSlot**](ProposedSlot.md) |  | [optional] 

## Example

```python
from fusion_refloor.models.proposed_crew import ProposedCrew

# TODO update the JSON string below
json = "{}"
# create an instance of ProposedCrew from a JSON string
proposed_crew_instance = ProposedCrew.from_json(json)
# print the JSON string representation of the object
print(ProposedCrew.to_json())

# convert the object into a dict
proposed_crew_dict = proposed_crew_instance.to_dict()
# create an instance of ProposedCrew from a dict
proposed_crew_from_dict = ProposedCrew.from_dict(proposed_crew_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


