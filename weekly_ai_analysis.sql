SELECT
  Week_Start,
  Week_Number,
  Weekly_Distance_km,
  Total_Workouts,
  Avg_Weekly_Pace,
  Avg_Weekly_HR,
  Avg_Weekly_Steps,
  Avg_Weekly_Strides,
  Weekly_Elevation_m,
  Shoes_Used,
  ml_generate_text_llm_result AS AI_Weekly_Analysis
FROM ML.GENERATE_TEXT(
  MODEL `strava_data.gemini_remote_model`,
  (
    SELECT
      Week_Start,
      Week_Number,
      Weekly_Distance_km,
      Total_Workouts,
      Avg_Weekly_Pace,
      Avg_Weekly_HR,
      Avg_Weekly_Steps,
      Avg_Weekly_Strides,
      Weekly_Elevation_m,
      Shoes_Used,
      'Act as a running coach. Analyze my weekly training performance for ' || Week_Number || ' (Starting ' || CAST(Week_Start AS STRING) || ')' ||
      ' and give me a 2-3 sentence summary of my weekly volume, pace consistency, elevation gain, running form (steps/strides per min), heart rate efficiency, and recovery advice: ' ||
      'Week: ' || Week_Number ||
      ', Week Starting: ' || CAST(Week_Start AS STRING) ||
      ', Weekly Distance: ' || Weekly_Distance_km || 'km' ||
      ', Total Workouts: ' || Total_Workouts ||
      ', Avg Weekly Pace: ' || Avg_Weekly_Pace ||
      ', Total Elevation: ' || Weekly_Elevation_m || 'm' ||
      ', Avg Weekly HR: ' || IFNULL(CAST(Avg_Weekly_HR AS STRING), 'N/A') || ' bpm' ||
      ', Avg Steps/Min: ' || IFNULL(CAST(Avg_Weekly_Steps AS STRING), 'N/A') || ' spm' ||
      ', Avg Strides/Min: ' || IFNULL(CAST(Avg_Weekly_Strides AS STRING), 'N/A') ||
      ', Shoes Used: ' || IFNULL(Shoes_Used, 'None') ||
      ', Workouts Summary: ' || Workout_Summary AS prompt
    FROM (
      SELECT
        DATE_TRUNC(Date, WEEK(MONDAY)) AS Week_Start,
        CONCAT('Week ', LPAD(CAST(MAX(Week_Num) AS STRING), 2, '0')) AS Week_Number,
        COUNT(*) AS Total_Workouts,
        ROUND(SUM(Distance_km), 2) AS Weekly_Distance_km,
        ROUND(SUM(Duration_min), 1) AS Weekly_Duration_min,
        ROUND(SUM(Elevation_m), 1) AS Weekly_Elevation_m,
        FORMAT('%02d:%02d/km',
          CAST(FLOOR(AVG(CASE WHEN Type = 'Run' AND Distance_km > 0 THEN Duration_min / Distance_km END)) AS INT64),
          CAST(ROUND((AVG(CASE WHEN Type = 'Run' AND Distance_km > 0 THEN Duration_min / Distance_km END) - FLOOR(AVG(CASE WHEN Type = 'Run' AND Distance_km > 0 THEN Duration_min / Distance_km END))) * 60) AS INT64)
        ) AS Avg_Weekly_Pace,
        ROUND(AVG(CASE WHEN Avg_HR > 0 THEN Avg_HR END), 1) AS Avg_Weekly_HR,
        ROUND(AVG(CASE WHEN Avg_Strides_Min > 0 THEN Avg_Strides_Min END)) AS Avg_Weekly_Strides,
        ROUND(AVG(CASE WHEN Avg_Steps_Min > 0 THEN Avg_Steps_Min END)) AS Avg_Weekly_Steps,
        STRING_AGG(DISTINCT Gear, ', ') AS Shoes_Used,
        STRING_AGG(CONCAT(Name, ' (', Distance_km, 'km @ ', Pace, ')'), '; ') AS Workout_Summary
      FROM `strava_data.strava_activities`
      GROUP BY Week_Start
    )
  ),
  STRUCT(
    TRUE AS flatten_json_output,
    200 AS max_output_tokens,
    0.25 AS temperature
  )
)
ORDER BY Week_Start DESC;
