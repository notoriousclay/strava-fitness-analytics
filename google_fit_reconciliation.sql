-- SQL definitions for Google Fit & Strava Steps Integration in BigQuery

-- 1. Create Dedicated Table for Daily Step Snapshots (Raw Ground Truth)
CREATE TABLE IF NOT EXISTS `strava_data.daily_steps` (
    Date DATE NOT NULL,
    Total_Steps INT64 NOT NULL,
    Source STRING DEFAULT 'Google Fit (Pixel 8a)',
    Ingested_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY Date
OPTIONS(
    description = "Passive 24-hour total daily step telemetry from Google Fit (Pixel 8a)"
);

-- 2. Daily Reconciliation View (With 1,000 Step Buffer for Device-Separation)
CREATE OR REPLACE VIEW `strava_data.v_daily_step_reconciliation` AS
WITH daily_strava AS (
    SELECT 
        Date,
        COUNT(Strava_ID) AS workout_sessions,
        ROUND(SUM(Distance_km), 2) AS workout_distance_km,
        SUM(Total_Steps) AS workout_steps
    FROM `strava_data.strava_activities`
    GROUP BY Date
)
SELECT 
    h.Date,
    -- Week Identifiers
    DATE_TRUNC(h.Date, WEEK(MONDAY)) AS week_start_date,
    DATE_ADD(DATE_TRUNC(h.Date, WEEK(MONDAY)), INTERVAL 6 DAY) AS week_end_date,
    EXTRACT(ISOWEEK FROM h.Date) AS week_num,
    FORMAT_DATE('%G-W%V', h.Date) AS year_week,
    FORMAT_DATE('%A', h.Date) AS day_name,
    
    -- Step Metrics & Compensation
    h.Total_Steps AS raw_fit_steps,
    1000 AS unrecorded_step_buffer,
    (h.Total_Steps + 1000) AS total_daily_steps,
    COALESCE(s.workout_steps, 0) AS workout_steps,
    
    -- Incidental steps: Movement accumulated outside dedicated Strava workouts
    GREATEST(0, (h.Total_Steps + 1000) - COALESCE(s.workout_steps, 0)) AS incidental_steps,
    
    -- Strava Sessions
    COALESCE(s.workout_distance_km, 0.0) AS workout_distance_km,
    COALESCE(s.workout_sessions, 0) AS workout_sessions
FROM `strava_data.daily_steps` h
LEFT JOIN daily_strava s 
    ON h.Date = s.Date
ORDER BY h.Date DESC;


-- 3. Dedicated Weekly Step Summary & ACWR Training Load View
CREATE OR REPLACE VIEW `strava_data.v_weekly_step_summary` AS
WITH weekly_aggregated AS (
    SELECT 
        week_start_date,
        week_end_date,
        year_week,
        week_num,
        CONCAT(FORMAT_DATE('%b %d', week_start_date), ' - ', FORMAT_DATE('%b %d', week_end_date)) AS week_label,
        
        -- Aggregated Weekly Volume (Includes 1,000/day buffer)
        SUM(total_daily_steps) AS total_weekly_steps,
        SUM(raw_fit_steps) AS total_raw_fit_steps,
        SUM(unrecorded_step_buffer) AS total_buffer_steps,
        SUM(workout_steps) AS total_workout_steps,
        SUM(incidental_steps) AS total_incidental_steps,
        ROUND(SUM(workout_distance_km), 2) AS total_workout_km,
        SUM(workout_sessions) AS total_sessions,
        COUNT(Date) AS logged_days,
        
        -- 70k Target Evaluation
        70000 AS weekly_step_target,
        CASE 
            WHEN SUM(total_daily_steps) >= 70000 THEN TRUE 
            ELSE FALSE 
        END AS is_70k_goal_met,
        ROUND((SUM(total_daily_steps) / 70000.0) * 100, 1) AS goal_achievement_pct,
        GREATEST(0, 70000 - SUM(total_daily_steps)) AS steps_remaining_to_70k
    FROM `strava_data.v_daily_step_reconciliation`
    GROUP BY week_start_date, week_end_date, year_week, week_num
)
SELECT 
    w.*,
    -- ACWR Metrics (Acute = Current Week km, Chronic = 4-Week Rolling Average km)
    w.total_workout_km AS acute_workout_km,
    ROUND(AVG(w.total_workout_km) OVER (
        ORDER BY w.week_start_date 
        ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
    ), 2) AS chronic_workout_km,
    CASE 
        WHEN AVG(w.total_workout_km) OVER (
            ORDER BY w.week_start_date 
            ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
        ) > 0 THEN
            ROUND(w.total_workout_km / AVG(w.total_workout_km) OVER (
                ORDER BY w.week_start_date 
                ROWS BETWEEN 3 PRECEDING AND CURRENT ROW
            ), 2)
        ELSE 1.0
    END AS acwr_ratio,
    -- Qualitative Training Stress Status
    CASE 
        WHEN w.total_workout_km = 0 THEN 'Rest / Zero'
        WHEN (w.total_workout_km / NULLIF(AVG(w.total_workout_km) OVER (ORDER BY w.week_start_date ROWS BETWEEN 3 PRECEDING AND CURRENT ROW), 0)) < 0.8 THEN 'Deload / Recovery (<0.8)'
        WHEN (w.total_workout_km / NULLIF(AVG(w.total_workout_km) OVER (ORDER BY w.week_start_date ROWS BETWEEN 3 PRECEDING AND CURRENT ROW), 0)) BETWEEN 0.8 AND 1.3 THEN 'Optimal Sweet Spot (0.8-1.3)'
        WHEN (w.total_workout_km / NULLIF(AVG(w.total_workout_km) OVER (ORDER BY w.week_start_date ROWS BETWEEN 3 PRECEDING AND CURRENT ROW), 0)) BETWEEN 1.3 AND 1.5 THEN 'Elevated Load (1.3-1.5)'
        ELSE 'Injury Danger Spike (>1.5)'
    END AS training_stress_status
FROM weekly_aggregated w
ORDER BY w.week_start_date DESC;
