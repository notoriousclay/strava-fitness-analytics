"""
Google Fit 2026 Backfill Engine
-------------------------------
Extracts historical daily step counts from Google Fit in 30-day windows
from 2026-01-01 to the current date and merges into BigQuery.
"""

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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(SCRIPT_DIR, ".env"))

from sync_google_fit import get_fit_access_token, init_bigquery

bq_client, PROJECT_ID = init_bigquery()
TARGET_TABLE = f"{PROJECT_ID}.strava_data.daily_steps"
STAGING_TABLE = f"{PROJECT_ID}.strava_data.stg_daily_steps_backfill"


def fetch_date_range_steps(start_dt, end_dt, access_token):
    """Fetch steps for a specific date window (max 30 days)."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)

    url = "https://fitness.googleapis.com/fitness/v1/users/me/dataset:aggregate"
    payload = {
        "aggregateBy": [{
            "dataTypeName": "com.google.step_count.delta",
            "dataSourceId": "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps"
        }],
        "bucketByTime": {"durationMillis": 86400000},
        "startTimeMillis": start_ms,
        "endTimeMillis": end_ms
    }

    res = requests.post(url, headers=headers, json=payload, timeout=20)
    res.raise_for_status()

    records = []
    buckets = res.json().get("bucket", [])
    for b in buckets:
        start_time_ms = int(b["startTimeMillis"])
        day_str = datetime.fromtimestamp(start_time_ms / 1000).strftime('%Y-%m-%d')

        total_steps = 0
        for dataset in b.get("dataset", []):
            for point in dataset.get("point", []):
                for val in point.get("value", []):
                    total_steps += val.get("intVal", 0)

        records.append({
            "Date": day_str,
            "Total_Steps": total_steps,
            "Source": "Google Fit (Pixel 8a)"
        })
    return records


def run_full_2026_backfill():
    print("=" * 70)
    print("🚀 STARTING GOOGLE FIT 2026 HISTORICAL BACKFILL")
    print("=" * 70)

    token = get_fit_access_token()
    start_global = datetime(2026, 1, 1, 0, 0, 0)
    end_global = datetime.now()

    all_records = []
    cur_start = start_global

    while cur_start < end_global:
        cur_end = min(cur_start + timedelta(days=29, hours=23, minutes=59, seconds=59), end_global)
        print(f"📦 Fetching window: {cur_start.strftime('%Y-%m-%d')} to {cur_end.strftime('%Y-%m-%d')}...")

        try:
            records = fetch_date_range_steps(cur_start, cur_end, token)
            all_records.extend(records)
            print(f"   ↳ Retrieved {len(records)} days.")
        except Exception as e:
            print(f"   ⚠️ Error fetching window: {e}")
            # Refresh token in case of expiry
            token = get_fit_access_token()

        cur_start = cur_end + timedelta(seconds=1)
        time.sleep(0.5)  # Respect API pacing

    # Deduplicate by Date (if any overlapping boundaries)
    unique_records = {r["Date"]: r for r in all_records}
    final_records = list(unique_records.values())
    print(f"\n📊 Total Unique Daily Records Collected: {len(final_records)} days (Jan 1, 2026 to {end_global.strftime('%Y-%m-%d')})")

    # Ingest into BigQuery using Batch Staging Table
    print("\n⚡ Ingesting into BigQuery via Staging Merge...")

    # Define schema for staging table
    schema = [
        bigquery.SchemaField("Date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("Total_Steps", "INT64", mode="REQUIRED"),
        bigquery.SchemaField("Source", "STRING", mode="NULLABLE")
    ]

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )

    load_job = bq_client.load_table_from_json(final_records, STAGING_TABLE, job_config=job_config)
    load_job.result()
    print("   ↳ Staged data successfully.")

    # Execute Batch MERGE into production daily_steps
    merge_sql = f"""
    MERGE `{TARGET_TABLE}` T
    USING `{STAGING_TABLE}` S
    ON T.Date = S.Date
    WHEN MATCHED THEN
        UPDATE SET Total_Steps = S.Total_Steps, Ingested_At = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN
        INSERT (Date, Total_Steps, Source, Ingested_At)
        VALUES (S.Date, S.Total_Steps, S.Source, CURRENT_TIMESTAMP());
    
    DROP TABLE IF EXISTS `{STAGING_TABLE}`;
    """

    bq_client.query(merge_sql).result()
    print(f"✅ Master Backfill Complete! Reconciled {len(final_records)} records into {TARGET_TABLE}.")


if __name__ == "__main__":
    run_full_2026_backfill()
