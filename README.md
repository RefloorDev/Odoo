![image](https://github.com/RefloorDev/Odoo/assets/33627068/06d7bd13-15ff-4a31-9038-049cff95295d)# Odoo

Please note that, in order to run the APIs, following details needs to add in the odoo conf file

 

api_url = <BASE_URL>
api_db = <DB NAME>
api_user_id = <API USER ID>
api_user_password = <API USER PASSWORD>

 

Here, these values(<>) should be replaced by odoo base URL, DB name & API User ID & Password to communicate with Odoo in API calls. 
Odoo instance should have only 1 database in order to work API calls.


Install Fustion Refloor library using following steps:
1. cd lib/python/fusion_refloor
2. python3 setup.py install
