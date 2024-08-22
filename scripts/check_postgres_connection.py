
import psycopg2
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

DATABASE= "refloor"
DB_USER= "odoo"
DB_PASSWORD = "odoo"
MAX_ALLOWED_CONNECTION = 60

SMTP_ENCRYPTION = "none"
SMTP_TIMEOUT = 60
SMTP_SERVER = "secure266.inmotionhosting.com"
SMTP_PORT = "25"
SMTP_USER = "ajay.jayaram@oneteamus.com"
SMTP_PASSWORD = ""

SMTP_FROM = "ajay.jayaram@oneteamus.com"
SMTP_TO = ["ajay.jayaram@oneteam.us", "shelton.freddy@oneteam.us"]

FAILURE_MSG = {
    "subject": "Refloor: Postgres Maximum Connection Reached",
    "body": """
            Hi,\n
            Something went wrong while connecting to postgres database
            """
}

CONNECTION_LIMIT_MSG = {
    "subject": "Refloor: Postgres Connection Failed",
    "body": """
        Hi,\n        
        Maximum allowed connection is reached in postgres. Please do needful.
        """
}

def send_email(message):
    if SMTP_ENCRYPTION == 'ssl':
        connection = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=SMTP_TIMEOUT)
    else:
        connection = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=SMTP_TIMEOUT)
    connection.login(SMTP_USER, SMTP_PASSWORD)
    msg = MIMEMultipart()
    msg['Subject'] = message.get('subject', '')
    email_text_part = MIMEText(message.get('body', ''), _subtype='plain', _charset='utf-8')
    msg.attach(email_text_part)
    connection.sendmail(SMTP_FROM, SMTP_TO, msg.as_string())
    print(connection)
    connection.quit()
    return True

try:
    #establishing the connection
    conn = psycopg2.connect(database=DATABASE, user=DB_USER, password=DB_PASSWORD, host='localhost', port= '5432')
    #Creating a cursor object using the cursor() method
    cursor = conn.cursor()

    #Executing an MYSQL function using the execute() method
    cursor.execute("SELECT sum(numbackends) FROM pg_stat_database;")

    # Fetch a single row using fetchone() method.
    result = cursor.fetchone() or 0
    no_of_connection = result and int(result[0]) or 0
    if int(no_of_connection) > MAX_ALLOWED_CONNECTION:
        send_email(CONNECTION_LIMIT_MSG)
    print("No of Current Connection: ",no_of_connection)

    #Closing the connection
    conn.close()
except:
    send_email(FAILURE_MSG)

