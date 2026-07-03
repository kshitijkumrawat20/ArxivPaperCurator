"""
Hello World DAG for Week 1 testing.

This is a simple DAG to verify Airflow is working correctly.
"""


from datetime import datetime 
import psycopg2
import requests
from airflow import DAG 
from datetime import timedelta, datetime
# from airflow.providers.standard.operators.python import PythonOperator
from airflow.operators.python import PythonOperator


def hello_world():
    """Simple hello world function """
    print("Hello World!")
    return "success"

def check_services():
    """check if other services are accessible"""
    try: 
        # check API response 
        response = requests.get("http:rag-app:8000/api/v1/health")
        print(f"API response: {response.status_code}")

        # check database connection 
        conn = psycopg2.connect(
            host="postgres",
            port=5432,
            database="rag_db",
            user="rag_user",
            password="rag_password"

        )

        print("Database connection successful")
        conn.close()

        return "services are accessible"
    
    except Exception as e:
        print(f"Error accessing services: {e}")
        raise

# DAG configuration 
default_args = {
    "owner": "rag",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "retries": 1,
    "email_on_failure": False,
    "email_on_retry": False,
    "retry_delay": timedelta(minutes=5),
}

# Creating the DAG
dag = DAG(
    "hello_world_dag",
    default_args=default_args,
    description="A simple hello world DAG for testing",
    schedule_interval=None,
    catchup=False,
    tags = ["weekl", "tesing"]
)

# defining the task 
hello_task = PythonOperator(
    task_id="hello_world_task",
    python_callable=hello_world,
    dag=dag,
)

service_check_task = PythonOperator(
    task_id="check_services_task",
    python_callable=check_services,
    dag=dag,
)

# task deps 
hello_task >> service_check_task