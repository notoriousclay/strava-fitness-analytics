import os
import sys
import time
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# --- 1. LOAD CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(SCRIPT_DIR, ".env")
load_dotenv(dotenv_path)

GOOGLE_FIT_CLIENT_ID = os.getenv("GOOGLE_FIT_CLIENT_ID")
GOOGLE_FIT_CLIENT_SECRET = os.getenv("GOOGLE_FIT_CLIENT_SECRET")
GOOGLE_FIT_REFRESH_TOKEN = os.getenv("GOOGLE_FIT_REFRESH_TOKEN")

def init_bigquery():
    """Initializes BigQuery client using local credentials.json if present, or ADC."""
    creds_path = os.path.join(SCRIPT_DIR, 'credentials.json')
    if os.path.exists(creds_path):
        creds = service_account.Credentials.from_service_account_file(creds_path)
        proj_id = creds.project_id
        return bigquery.Client(credentials=creds, project=proj_id), proj_id
    else:
        proj_id = os.getenv("GCP_PROJECT_ID", "strava-sync-505308")
        return bigquery.Client(project=proj_id), proj_id

bq_client, PROJECT_ID = init_bigquery()
TABLE_ID = f"{PROJECT_ID}.strava_data.daily_steps"


# --- 2. GOOGLE FIT API CALLS ---
def get_fit_access_token():
    """Exchange refresh token for fresh ephemeral access token."""
    if not GOOGLE_FIT_REFRESH_TOKEN:
        raise ValueError("Missing GOOGLE_FIT_REFRESH_TOKEN in environment or .env file.")
    
    url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": GOOGLE_FIT_CLIENT_ID,
        "client_secret": GOOGLE_FIT_CLIENT_SECRET,
        "refresh_token": GOOGLE_FIT_REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }
    response = requests.post(url, data=payload, timeout=10)
    response.raise_for_status()
    return response.json()["access_token"]


def fetch_google_fit_steps(days=7):
    """
    Fetch aggregated 24h step counts from Google Fit API for Pixel 8a.
    Groups telemetry into 86,400,000 ms (1-day) intervals.
    """
    access_token = get_fit_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    now = datetime.now()
    start_date = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    start_ms = int(start_date.timestamp() * 1000)
    end_ms = int(end_date.timestamp() * 1000)

    url = "https://fitness.googleapis.com/fitness/v1/users/me/dataset:aggregate"
    payload = {
        "aggregateBy": [{
            "dataTypeName": "com.google.step_count.delta",
            "dataSourceId": "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps"
        }],
        "bucketByTime": {"durationMillis": 86400000},  # 24 hours in ms
        "startTimeMillis": start_ms,
        "endTimeMillis": end_ms
    }

    print(f"🔄 Querying Google Fit API for the last {days} days ({start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')})...")
    response = requests.post(url, headers=headers, json=payload, timeout=15)
    response.raise_for_status()

    records = []
    buckets = response.json().get("bucket", [])
    for bucket in buckets:
        start_time_ms = int(bucket["startTimeMillis"])
        # Format as standard YYYY-MM-DD
        day_str = datetime.fromtimestamp(start_time_ms / 1000).strftime('%Y-%m-%d')

        total_steps = 0
        for dataset in bucket.get("dataset", []):
            for point in dataset.get("point", []):
                for val in point.get("value", []):
                    total_steps += val.get("intVal", 0)

        records.append({
            "Date": day_str,
            "Total_Steps": total_steps,
            "Source": "Google Fit (Pixel 8a)"
        })

    print(f"📊 Retrieved {len(records)} daily step records from Google Fit.")
    return records


# --- 3. BIGQUERY UPSERT (IDEMPOTENT MERGE) ---
def upsert_daily_steps(records):
    """Upsert daily steps into BigQuery table strava_data.daily_steps."""
    if not records:
        print("⏭️ No step records to load.")
        return

    # Ensure table exists
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS `{TABLE_ID}` (
        Date DATE NOT NULL,
        Total_Steps INT64 NOT NULL,
        Source STRING DEFAULT 'Google Fit (Pixel 8a)',
        Ingested_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
    )
    PARTITION BY Date;
    """
    bq_client.query(create_table_sql).result()

    merge_sql = f"""
    MERGE `{TABLE_ID}` T
    USING (
        SELECT 
            PARSE_DATE('%Y-%m-%d', @Date) AS Date,
            @Total_Steps AS Total_Steps,
            @Source AS Source,
            CURRENT_TIMESTAMP() AS Ingested_At
    ) S
    ON T.Date = S.Date
    WHEN MATCHED THEN
        UPDATE SET Total_Steps = S.Total_Steps, Ingested_At = S.Ingested_At
    WHEN NOT MATCHED THEN
        INSERT (Date, Total_Steps, Source, Ingested_At)
        VALUES (S.Date, S.Total_Steps, S.Source, S.Ingested_At);
    """

    for r in records:
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("Date", "STRING", r["Date"]),
                bigquery.ScalarQueryParameter("Total_Steps", "INT64", r["Total_Steps"]),
                bigquery.ScalarQueryParameter("Source", "STRING", r["Source"]),
            ]
        )
        bq_client.query(merge_sql, job_config=job_config).result()

    print(f"✅ Successfully reconciled {len(records)} daily step records into {TABLE_ID}.")


def run_fit_sync(days=7):
    """Main execution function."""
    records = fetch_google_fit_steps(days=days)
    upsert_daily_steps(records)


if __name__ == "__main__":
    run_fit_sync(days=7)
