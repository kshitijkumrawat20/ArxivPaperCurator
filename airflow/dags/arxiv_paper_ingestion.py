from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operator.python import PythonOperator
from arxiv_ingestion.tasks import (
    create_opensearch_placeholder,
    fetch_daily_papers,
    generate_daily_report, 
    process_failed_papers,
    setup_environment
)
from datetime import datetime, timedelta
# default DAG arguments 
default_args ={
    "owner": "arxiv_curator",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "catchup": False,
    "start_date": datetime(2026, 2, 20)

}

# defining the DAG
dag = DAG(
    "arxiv_paper_ingestion",
    default_args=default_args,
    description="DAG for ingesting arXiv papers, extracting metadata, and generating reports",
    schedule = "0 6 * * *", # daily at 6 AM UTC
    max_active_runs = 1, 
    tags = ["arxiv", "ingestion", "metadata", "reporting"]

)

# task definations 
setup_task = PythonOperator(
    task_id = "setup_environment",
    python_callable = setup_environment,
    dag = dag,
)

fetch_task = PythonOperator(
    task_id = "fetch_daily_papers",
    python_callable = fetch_daily_papers,
    dag = dag,
)

retry_task = PythonOperator(
    task_id = "process_failed_papers",
    python_callable = process_failed_papers,
    dag = dag,
)

opensearch_task = PythonOperator(
    task_id = "create_opensearch_placeholder",
    python_callable = create_opensearch_placeholder,
    dag = dag,
)
report_task = PythonOperator(
    task_id = "generate_daily_report",
    python_callable = generate_daily_report,
    dag = dag,
)

cleanup_task = BashOperator(
    task_id = "cleanup_temp_files",
    bash_command = """
    echo "Cleaning up temporary files..."
    # remove PDFs older than 30 days to manage disk space
    find /tmp -type f -name "*.pdf" -mtime + 30 -delete 2>/dev/null || true
""",
    dag = dag,
)

# task dependecies 
# Pipeline 1: Setup -> Fetch -> Opensearch -> Report -> Cleanup
setup_task >> fetch_task >> [retry_task, opensearch_task] >> report_task >> cleanup_task
