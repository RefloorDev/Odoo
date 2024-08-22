#!/bin/bash
python3 check_postgres_connection.py
SERVICE="/opt/refloor/Refloor_odoo/odoo_server/odoo-bin"
echo "$SERVICE"
echo "ps ax | grep -v grep | grep $SERVICE"
if ps ax | grep -v grep | grep $SERVICE > /dev/null
then
    #echo "1"
    echo "$SERVICE is running well at `date`" >> /home/refloor/odoo_script_log/restart.log
else
    #echo "2"
    echo "$SERVICE is not running. Restarting... at `date`" >> /home/refloor/odoo_script_log/restart.log
    sudo /etc/init.d/refloor start > /dev/null
fi
