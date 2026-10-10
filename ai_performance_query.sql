WITH stats AS (
  SELECT
    COUNT(*) AS total_activities,
    COUNTIF(Type = 'Run') AS total_runs,
    ROUND(SUM(Distance_km), 2) AS total_distance_km,
    ROUND(SUM(Duration_min) / 60.0, 1) AS total_hours,
    ROUND(AVG(CASE WHEN Type = 'Run' AND Distance_km > 0 THEN Duration_min / Distance_km END), 2) AS avg_run_pace_dec,
    ROUND(AVG(CASE WHEN Avg_HR > 0 THEN Avg_HR END), 1) AS overall_avg_hr,
    ROUND(AVG(CASE WHEN Avg_Steps_Min > 0 THEN Avg_Steps_Min END), 1) AS avg_spm,
    ROUND(SUM(Elevation_m), 1) AS total_elevation_m,
    CAST(MIN(Date) AS STRING) AS start_date,
    CAST(MAX(Date) AS STRING) AS end_date
  FROM
    `strava_data.strava_activities`
),
gear_summary AS (
  SELECT
    STRING_AGG(CONCAT(IFNULL(Gear, 'Unspecified'), ': ', CAST(cnt AS STRING), ' workouts (', CAST(ROUND(total_dist, 1) AS STRING), ' km)'), ' | ') AS gear_details
  FROM (
    SELECT Gear, COUNT(*) AS cnt, SUM(Distance_km) AS total_dist FROM `strava_data.strava_activities` GROUP BY Gear
  )
),
tod_summary AS (
  SELECT
    STRING_AGG(CONCAT(time_of_day, ': ', CAST(cnt AS STRING), ' workouts'), ' | ') AS tod_details
  FROM (
    SELECT
      CASE 
        WHEN CAST(SUBSTR(Start_Time, 1, 2) AS INT64) BETWEEN 5 AND 11 THEN 'Morning'
        WHEN CAST(SUBSTR(Start_Time, 1, 2) AS INT64) BETWEEN 12 AND 16 THEN 'Afternoon'
        WHEN CAST(SUBSTR(Start_Time, 1, 2) AS INT64) BETWEEN 17 AND 22 THEN 'Evening'
        ELSE 'Night'
      END AS time_of_day,
      COUNT(*) AS cnt
    FROM `strava_data.strava_activities`
    WHERE Start_Time IS NOT NULL AND Start_Time != 'N/A'
    GROUP BY 1
  )
)
SELECT
  ml_generate_text_result AS overall_performance_analysis
FROM
  ML.GENERATE_TEXT(
    MODEL `strava_data.gemini_remote_model`,
    (
      SELECT
        CONCAT(
          'You are an elite sports scientist and running coach. Analyze the athlete entire database history and generate a comprehensive performance analysis report.\n\n',
          '=== ATHLETE DATABASE OVERVIEW ===\n',
          'Date Range: ', s.start_date, ' to ', s.end_date, '\n',
          'Total Workouts: ', CAST(s.total_activities AS STRING), ' (Runs: ', CAST(s.total_runs AS STRING), ')\n',
          'Total Mileage: ', CAST(s.total_distance_km AS STRING), ' km across ', CAST(s.total_hours AS STRING), ' hours\n',
          'Average Run Pace (Decimal Mins): ', CAST(s.avg_run_pace_dec AS STRING), ' min/km\n',
          'Average HR: ', IFNULL(CAST(s.overall_avg_hr AS STRING), 'N/A'), ' bpm\n',
          'Average Steps/Min: ', IFNULL(CAST(s.avg_spm AS STRING), 'N/A'), ' spm\n',
          'Total Elevation Gain: ', CAST(s.total_elevation_m AS STRING), ' m\n\n',
          '=== GEAR & SHOE USAGE ===\n',
          IFNULL(g.gear_details, 'None'), '\n\n',
          '=== TIME OF DAY DISTRIBUTION ===\n',
          IFNULL(t.tod_details, 'None'), '\n\n',
          'Please provide a detailed, structured analysis with: Executive Summary, Pace & HR Efficiency, Shoe Performance, Consistency Patterns, and 3 Coaching Recommendations.'
        ) AS prompt
      FROM stats s
      CROSS JOIN gear_summary g
      CROSS JOIN tod_summary t
    ),
    STRUCT(0.2 AS temperature, 1000 AS max_output_tokens, TRUE AS flatten_json_output)
  );
