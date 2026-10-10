import json
import sys
from datetime import datetime
from google.cloud import bigquery
from google.oauth2 import service_account

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DAY_NUM_MAP = {
    "Monday": "01",
    "Tuesday": "02",
    "Wednesday": "03",
    "Thursday": "04",
    "Friday": "05",
    "Saturday": "06",
    "Sunday": "07"
}

def backfill_bigquery():
    print("🔄 Connecting to BigQuery...")
    credentials = service_account.Credentials.from_service_account_file('credentials.json')
    client = bigquery.Client(credentials=credentials, project=credentials.project_id)
    table_id = f"{credentials.project_id}.strava_data.strava_activities"

    print(f"🛠️ Ensuring Day_Num column exists in `{table_id}`...")
    alter_query = f"ALTER TABLE `{table_id}` ADD COLUMN IF NOT EXISTS Day_Num STRING;"
    client.query(alter_query).result()
    print("✅ Schema update verified.")

    print(f"📊 Updating Day_Num for all records in `{table_id}` based on Day_Name...")
    update_query = f"""
    UPDATE `{table_id}`
    SET Day_Num = CASE Day_Name
      WHEN 'Monday' THEN '01'
      WHEN 'Tuesday' THEN '02'
      WHEN 'Wednesday' THEN '03'
      WHEN 'Thursday' THEN '04'
      WHEN 'Friday' THEN '05'
      WHEN 'Saturday' THEN '06'
      WHEN 'Sunday' THEN '07'
      ELSE 'N/A'
    END
    WHERE TRUE;
    """
    query_job = client.query(update_query)
    query_job.result()
    print(f"🎉 Successfully updated {query_job.num_dml_affected_rows} rows in BigQuery table!")

    # Verify BigQuery sample
    sample_query = f"""
    SELECT Strava_ID, Date, Day_Name, Day_Num 
    FROM `{table_id}` 
    ORDER BY Date DESC 
    LIMIT 10;
    """
    rows = list(client.query(sample_query).result())
    print("\n🔍 Sample verification of BigQuery records:")
    for r in rows:
        print(f"  Strava_ID: {r.Strava_ID} | Date: {r.Date} | Day_Name: {r.Day_Name} -> Day_Num: {r.Day_Num}")

def backfill_local_json():
    json_path = "dashboard_data.json"
    print(f"\n🔄 Backfilling local JSON cache (`{json_path}`)...")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        updated_count = 0
        for item in data:
            day_name = item.get("Day_Name")
            if day_name in DAY_NUM_MAP:
                item["Day_Num"] = DAY_NUM_MAP[day_name]
                updated_count += 1
            elif item.get("Date"):
                try:
                    dt = datetime.strptime(item["Date"], "%Y-%m-%d")
                    item["Day_Num"] = f"{dt.isoweekday():02d}"
                    updated_count += 1
                except Exception:
                    item["Day_Num"] = "N/A"
            else:
                item["Day_Num"] = "N/A"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"✅ Successfully updated {updated_count} records in `{json_path}`.")
    except Exception as e:
        print(f"⚠️ Warning: Could not update `{json_path}`: {e}")

if __name__ == "__main__":
    backfill_bigquery()
    backfill_local_json()
