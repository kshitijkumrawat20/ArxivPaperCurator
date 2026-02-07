FROM python:3.13-slim
# Set environment variables for the application

ENV AIRFLOW_HOME=/opt/airflow
ENV AIRFLOW_VERSION=2.10.3
ENV PYTHON_VERSION=3.13
# constraints URL for Airflow dependencies

ENV CONSTRAINTS_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"  

# Install airflow and its deps 
RUN apt-get update && \ 
    apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libpq-dev \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# create airflow user with UID/GID 50000 for cross platform compatibility
RUN groupadd -r -g 50000 airflow && useradd -r -u 50000 -g airflow -d ${AIRFLOW_HOME} -s /bin/bash airflow

RUN pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    --constraint "${CONSTRAINTS_URL}"  \
    psycopg2-binary 

# copy requirements and install project deps 
COPY requirements.txt /tmp/requirements-airflow.txt
RUN pip install --no-cache-dir -r /tmp/requirements-airflow.txt

# copy and set up entrypoint scripts 
COPY entrypoint.sh /entrypoint.sh
# set permissions for airflow user to access the entrypoint script
RUN chmod +x /entrypoint.sh 

# switch to airflow user and set working directory 
USER airflow
WORKDIR ${AIRFLOW_HOME}

# EXPOSE PORT 
EXPOSE 8080 

CMD ["/entrypoint.sh"]