-- SQL definitions for Google Fit 10k Steps Integration in BigQuery

-- 1. Create Dedicated Table for Daily Step Snapshots
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

-- 2. Create Master Reconciliation View (Workout Steps vs Incidental Daily Steps)
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
    h.Total_Steps AS total_daily_steps,
    COALESCE(s.workout_steps, 0) AS workout_steps,
    -- Incidental steps: Steps accumulated outside your recorded runs/walks
    GREATEST(0, h.Total_Steps - COALESCE(s.workout_steps, 0)) AS incidental_steps,
    COALESCE(s.workout_distance_km, 0.0) AS workout_distance_km,
    COALESCE(s.workout_sessions, 0) AS workout_sessions,
    -- Target evaluation
    CASE 
        WHEN h.Total_Steps >= 10000 THEN TRUE 
        ELSE FALSE 
    END AS is_10k_goal_met,
    ROUND((h.Total_Steps / 10000.0) * 100, 1) AS goal_achievement_pct
FROM `strava_data.daily_steps` h
LEFT JOIN daily_strava s 
    ON h.Date = s.Date
ORDER BY h.Date DESC;
