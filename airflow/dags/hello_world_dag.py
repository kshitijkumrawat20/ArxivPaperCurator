import logging 
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from datetime import datetime, timedelta

def hello_world():
    """A simple function that prints 'Hello, World!'."""
    print("Airflow is printing Hello, World!")
    return "success"

def check_services():
    """checks if the services are running"""

    import requests 
    try: 
        response = requests.get("http://localhost:8000/health")
        print(f"Service is up. Status code: {response.status_code}")

        # check the database connection 
        import psycopg2
        con = psycopg2.connect(
            host = "postgres", 
            database = "rag_db",
            port = 5432,
            user = "rag_user",
            password = "rag_password"
            
        )
        print("Database connection successful")
        con.close()
    except Exception as e:
        print(f"Error: {e}")
        raise e

## DAG configuration 

default_args = {
    'owner': 'rag',
    'depends_on_past': False,
    'start_date': datetime(2026, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5)
}
dag = DAG(
    "testing", 
    default_args=default_args,
    description="A simple hello world DAG",
    schedule = None,
    catchup = False,
    tags = ['testing']
)

# tasks 
hello_task = PythonOperator(
    task_id = "hello_task",
    python_callable=hello_world,
    dag = dag
)

service_check_task = PythonOperator(
    task_id = "service_check_task",
    python_callable = check_services,
    dag = dag
)

hello_task >> service_check_task