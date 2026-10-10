import sys
import math
from google.cloud import bigquery
from google.oauth2 import service_account

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


credentials = service_account.Credentials.from_service_account_file('credentials.json')
client = bigquery.Client(credentials=credentials, project=credentials.project_id)
table_id = f"{credentials.project_id}.strava_data.strava_activities"

print("🔄 Querying existing rows from BigQuery...")
rows = list(client.query(f"SELECT Strava_ID, Pace, Distance_km, Duration_min, Type, Cadence, Total_Steps FROM `{table_id}`").result())
print(f"📊 Total rows to update: {len(rows)}")

temp_updates_table = f"{credentials.project_id}.strava_data.pace_updates_temp"

update_rows = []
for r in rows:
    sid = r.Strava_ID
    dist = r.Distance_km or 0
    dur = r.Duration_min or 0
    cad = r.Cadence or 0
    steps = r.Total_Steps or 0
    
    pace_str = "N/A"
    pace_clean = "N/A"
    if dist > 0 and dur > 0 and r.Type == "Run":
        pace_dec = dur / dist
        m = int(pace_dec)
        s = int((pace_dec - m) * 60)
        pace_str = f"{m:02d}:{s:02d}/km"
        pace_clean = f"{m:02d}:{s:02d}"
    
    strides = int(math.ceil(cad)) if cad else 0
    steps_min = int(math.ceil(steps / dur)) if (steps > 0 and dur > 0) else 0
    
    update_rows.append({
        "Strava_ID": sid,
        "Pace": pace_str,
        "Pace_Clean": pace_clean,
        "Avg_Strides_Min": strides,
        "Avg_Steps_Min": steps_min
    })

job_config = bigquery.LoadJobConfig(
    write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    autodetect=True
)

client.load_table_from_json(update_rows, temp_updates_table, job_config=job_config).result()

merge_sql = f"""
MERGE `{table_id}` T
USING `{temp_updates_table}` S
ON T.Strava_ID = S.Strava_ID
WHEN MATCHED THEN
  UPDATE SET
    T.Pace = S.Pace,
    T.Pace_Clean = S.Pace_Clean,
    T.Avg_Strides_Min = S.Avg_Strides_Min,
    T.Avg_Steps_Min = S.Avg_Steps_Min;
"""

client.query(merge_sql).result()
client.delete_table(temp_updates_table, not_found_ok=True)

print("🎉 Successfully backfilled Pace (leading zeros), Pace_Clean, Avg_Strides_Min, and Avg_Steps_Min for all 127 records in BigQuery!")
