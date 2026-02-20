#!/bin/bash \

set -e 

# clean up any existing PID files and processes 

echo "cleaning up existing Airflow processes...."
pkill -f "airflow webserver" || true
pkill -f "airflow scheduler" || true
rm -f /opt/airflow/airflow-webserver.pid
rm -f /opt/airflow/airflow-scheduler.pid

# wait a moment for processes to terminate\
sleep 2 

# initialize airflow database 
echo "initializing airflow database"
airflow db init

# create admin user with admin/ admin  credentials 
airflow user create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \ 
    --password admin || echo "Admin user already exists, skipping creation"

# start the webserver and scheduler in the background
echo "starting airflow webserver and scheduler..."
airflow webserver -port 8080 --daemon & airflow scheduler

