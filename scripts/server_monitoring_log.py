import psutil
import psycopg2
import requests
import json
from datetime import datetime

# Database connection details
DB_NAME = 'refloor_dev'
DB_USER = 'odoo'
DB_PASSWORD = 'odoo'
DB_HOST = 'localhost'
DB_PORT = '5432'
ODOO_URL= 'http://localhost:7005/web/login'

def get_db_connection_count():
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM pg_stat_activity;")
        connection_count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return connection_count
    except Exception as e:
        return f"Error: {e}"

def get_system_metrics():
    metrics = {}
    metrics['cpu_usage_percent'] = psutil.cpu_percent(interval=1)
    memory_usage_dict = psutil.virtual_memory()._asdict()
    metrics['memory_usage'] = {
        "total": memory_usage_dict.get('total') and round(memory_usage_dict.get('total')/1024**3, 2) or 0,
        "available": memory_usage_dict.get('available') and round(memory_usage_dict.get('available')/1024**3, 2) or 0,
        "percentage": memory_usage_dict.get('percent', 0) ,
        "used": memory_usage_dict.get('used') and round(memory_usage_dict.get('used')/1024**3, 2) or 0,
        "free": memory_usage_dict.get('free') and round(memory_usage_dict.get('free')/1024**3, 2) or 0
    }
    disk_usage_dict =  psutil.disk_usage('/')._asdict()
    metrics['disk_usage'] = {
        "total": disk_usage_dict.get('total') and round(disk_usage_dict.get('total')/1024**3, 2) or 0,
        "used": disk_usage_dict.get('used') and round(disk_usage_dict.get('used')/1024**3, 2) or 0,
        "free": disk_usage_dict.get('free') and round(disk_usage_dict.get('free')/1024**3, 2) or 0,
        "percentage": disk_usage_dict.get('percent', 0)
    }
    return metrics

def store_metrics_to_file(metrics, filename='system_metrics.json'):
    with open(filename, 'a') as file:
        json.dump(metrics, file, separators=(',', ':'))
        file.write('\n')

def check_odoo_instance_working_fine():
    result= False
    try:
        response = requests.get(ODOO_URL)
        if response.status_code == 200:
            result = True
        else:
            result = False
    except requests.exceptions.RequestException as e:
        print(f"Failed to reach Odoo instance at {ODOO_URL}. Error: {e}")
        result= False
    return result

def main():
    metrics = {}
    metrics['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    metrics['db_connection_count'] = get_db_connection_count()
    metrics.update(get_system_metrics())
    if check_odoo_instance_working_fine():
        metrics['odoo_status'] = 'running'
    else:
        metrics['odoo_status'] = 'not_running'

    store_metrics_to_file(metrics)
    print(f"Metrics stored to file successfully.")

if __name__ == "__main__":
    main()
