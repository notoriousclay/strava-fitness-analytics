import os
import sys
import time
import requests
import math
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google.cloud import bigquery
from google.oauth2 import service_account

import sync

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
credentials = service_account.Credentials.from_service_account_file('credentials.json')
bq_client = bigquery.Client(credentials=credentials, project=credentials.project_id)
TABLE_ID = f"{credentials.project_id}.strava_data.strava_activities"
TEMP_TABLE_ID = f"{credentials.project_id}.strava_data.strava_activities_temp"

def safe_strava_request(url, headers, params=None):
    """
    Makes a request to Strava API with automatic retry on 429 Rate Limit.
    """
    while True:
        res = requests.get(url, headers=headers, params=params)
        if res.status_code == 429:
            print("⏳ Strava API rate limit (429) hit. Waiting 60 seconds for window reset...", flush=True)
            time.sleep(60)
            continue
        res.raise_for_status()
        return res.json()

def backfill():
    # Pre-populate location cache
    print("📍 Pre-loading location cache from BigQuery...", flush=True)
    cache_query = f"SELECT Start_Lat, Start_Lng, City_District, Village, Town, City, Municipality, State, Country FROM `{TABLE_ID}` WHERE Start_Lat IS NOT NULL AND Start_Lng IS NOT NULL"
    try:
        results = bq_client.query(cache_query).result()
        for r in results:
            key = (round(float(r.Start_Lat), 3), round(float(r.Start_Lng), 3))
            sync.GEO_CACHE[key] = {
                "City_District": r.City_District,
                "Village": r.Village,
                "Town": r.Town,
                "City": r.City,
                "Municipality": r.Municipality,
                "State": r.State,
                "Country": r.Country
            }
        print(f"✅ Cached {len(sync.GEO_CACHE)} location coordinates.", flush=True)
    except Exception as e:
        print(f"⚠️ Could not pre-load location cache: {e}", flush=True)

    token = sync.get_strava_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    print("🔄 Fetching historical Strava activities with rate limit safety...", flush=True)
    
    # Paginated fetch with rate-limit safety
    url = "https://www.strava.com/api/v3/athlete/activities"
    all_activities = []
    page = 1
    per_page = 200
    
    while True:
        params = {"after": 0, "per_page": per_page, "page": page}
        try:
            data = safe_strava_request(url, headers=headers, params=params)
            if not data:
                break
            all_activities.extend(data)
            if len(data) < per_page:
                break
            page += 1
        except Exception as e:
            print(f"❌ Error fetching activities page {page}: {e}", flush=True)
            break

    print(f"📊 Total activities fetched from Strava: {len(all_activities)}", flush=True)

    rows_to_insert = []

    for idx, activity in enumerate(all_activities, 1):
        act_id = activity.get("id")

        # Gear (Shoes/Equipment)
        gear_name = None
        if isinstance(activity.get("gear"), dict):
            gear_name = activity.get("gear", {}).get("name")
        gear_id = activity.get("gear_id")
        if not gear_name and gear_id:
            gear_name = sync.get_gear_name(gear_id, token)

        # Start & End Time & Date Breakdown
        start_date_local = activity.get("start_date_local", "")
        start_time_str = "N/A"
        end_time_str = "N/A"
        year_name = "N/A"
        day_name = "N/A"
        day_num = "N/A"
        month_name = "N/A"
        month_num = "N/A"
        week_num = "N/A"
        
        date_str = start_date_local.split("T")[0] if start_date_local else ""
        if date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                year_name = dt.strftime("%Y")
                day_name = dt.strftime("%A")
                day_num = f"{dt.isoweekday():02d}"
                month_name = dt.strftime("%B")
                month_num = dt.strftime("%m")
                week_num = dt.strftime("%V")
            except Exception:
                pass

        if start_date_local:
            try:
                clean_iso = start_date_local.replace("Z", "").split("+")[0]
                start_dt = datetime.strptime(clean_iso, "%Y-%m-%dT%H:%M:%S")
                start_time_str = start_dt.strftime("%H:%M:%S")
                
                elapsed_secs = int(activity.get("elapsed_time", 0) or 0)
                end_dt = start_dt + timedelta(seconds=elapsed_secs)
                end_time_str = end_dt.strftime("%H:%M:%S")
            except Exception as e:
                print(f"  ⚠️ Warning parsing timestamps: {e}", flush=True)

        raw_distance_m = float(activity.get("distance", 0) or 0.0)
        raw_distance_km = raw_distance_m / 1000.0
        distance_km = round(raw_distance_km, 2)
        
        duration_min = activity.get("moving_time", 0) / 60.0
        elapsed_min = activity.get("elapsed_time", 0) / 60.0
        
        pace_str = "N/A"
        pace_clean_str = "N/A"
        if distance_km > 0 and activity.get("type") == "Run":
            pace_dec = duration_min / distance_km
            mins = int(pace_dec)
            secs = int((pace_dec - mins) * 60)
            pace_str = f"{mins:02d}:{secs:02d}/km"
            pace_clean_str = f"{mins:02d}:{secs:02d}"
            
        activity_type = activity.get("type", "Workout")
        cadence_raw = activity.get("average_cadence")

        if cadence_raw and float(cadence_raw) > 0:
            cadence = float(cadence_raw)
            total_steps = int((cadence * 2) * duration_min)
        elif activity_type in ["Run", "Walk", "Hike"] and raw_distance_km > 0 and duration_min > 0:
            speed_kmh = raw_distance_km / (duration_min / 60.0)
            if activity_type in ["Walk", "Hike"]:
                total_steps = int(raw_distance_km * 1300)
            else:
                est_spm = max(145.0, min(180.0, 140.0 + 2.3 * speed_kmh))
                total_steps = int(est_spm * duration_min)
            cadence = round((total_steps / duration_min) / 2.0, 1)
        else:
            cadence = 0.0
            total_steps = 0

        avg_strides_min = int(math.ceil(cadence)) if cadence else 0
        avg_steps_min = int(math.ceil(total_steps / duration_min)) if (total_steps > 0 and duration_min > 0) else 0

        start_latlng = activity.get("start_latlng", []) or []
        start_lat = start_latlng[0] if len(start_latlng) > 0 else None
        start_lng = start_latlng[1] if len(start_latlng) > 1 else None
        loc_info = sync.get_location_info(start_lat, start_lng) if (start_lat and start_lng) else {}
        
        row = {
            "Strava_ID": act_id,
            "Name": activity.get("name", "Workout"),
            "Date": date_str,
            "Year_Name": str(year_name),
            "Day_Name": str(day_name),
            "Day_Num": str(day_num),
            "Month_Name": str(month_name),
            "Month_Num": str(month_num),
            "Week_Num": str(week_num),
            "Type": activity.get("type", "Workout"),
            "Distance_km": distance_km,
            "Duration_min": round(duration_min, 1),
            "Elapsed_Time_min": round(elapsed_min, 1),
            "Elevation_m": round(activity.get("total_elevation_gain", 0), 1),
            "Pace": pace_str,
            "Pace_Clean": pace_clean_str,
            "Gear": gear_name,
            "Start_Time": start_time_str,
            "End_Time": end_time_str,
            "Calories": float(activity.get("calories") or 0.0),
            "Avg_HR": float(activity.get("average_heartrate") or 0.0),
            "Cadence": cadence,
            "Total_Steps": total_steps,
            "Avg_Strides_Min": avg_strides_min,
            "Avg_Steps_Min": avg_steps_min,
            "Start_Lat": start_lat,
            "Start_Lng": start_lng,
            "City_District": loc_info.get("City_District"),
            "Village": loc_info.get("Village"),
            "Town": loc_info.get("Town"),
            "City": loc_info.get("City"),
            "Municipality": loc_info.get("Municipality"),
            "State": loc_info.get("State"),
            "Country": loc_info.get("Country")
        }
        rows_to_insert.append(row)

    print(f"\n🚀 Prepared {len(rows_to_insert)} updated rows. Merging into BigQuery table `{TABLE_ID}`...", flush=True)

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        autodetect=True
    )
    
    load_job = bq_client.load_table_from_json(rows_to_insert, TEMP_TABLE_ID, job_config=job_config)
    load_job.result()
    print(f"✅ Loaded rows into temporary table `{TEMP_TABLE_ID}`.", flush=True)

    merge_query = f"""
    MERGE `{TABLE_ID}` T
    USING `{TEMP_TABLE_ID}` S
    ON T.Strava_ID = S.Strava_ID
    WHEN MATCHED THEN
      UPDATE SET
        T.Pace = S.Pace,
        T.Pace_Clean = S.Pace_Clean,
        T.Day_Num = CAST(S.Day_Num AS STRING),
        T.Gear = S.Gear,
        T.Start_Time = S.Start_Time,
        T.End_Time = S.End_Time,
        T.Avg_Strides_Min = S.Avg_Strides_Min,
        T.Avg_Steps_Min = S.Avg_Steps_Min,
        T.Total_Steps = S.Total_Steps,
        T.Cadence = S.Cadence,
        T.City_District = S.City_District,
        T.Village = S.Village,
        T.Town = S.Town,
        T.City = S.City,
        T.Municipality = S.Municipality,
        T.State = S.State,
        T.Country = S.Country
    WHEN NOT MATCHED THEN
      INSERT ROW;
    """

    merge_job = bq_client.query(merge_query)
    merge_job.result()
    print("🎉 BigQuery MERGE completed successfully! All historical records updated.", flush=True)

    bq_client.delete_table(TEMP_TABLE_ID, not_found_ok=True)
    print("🧹 Temporary table cleaned up.", flush=True)

if __name__ == "__main__":
    backfill()
