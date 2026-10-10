# Strava Fitness Analytics - Cloud Sync

Automated pipeline to fetch activity and telemetry data from Strava's API and ingest it into Google Cloud BigQuery.

---

## 🏗️ Architecture

```
                 ┌────────────────────┐
                 │    git push main   │
                 └─────────┬──────────┘
                           │ (GitHub Actions)
                           ▼
                 ┌────────────────────┐
                 │ Cloud Functions v2 │
                 │(strava-fitness-sync│
                 └─────────▲──────────┘
                           │ (Daily at 8:00 PM)
                 ┌─────────┴──────────┐
                 │  Cloud Scheduler   │
                 └────────────────────┘
                           │
                 ┌─────────▼──────────┐
                 │  Google BigQuery   │
                 │(strava_activities) │
                 └────────────────────┘
```

---

## 🚀 Setup & Deployment Guide

### 1. Initialize Git & Push to GitHub

Run the following commands in your project root:

```powershell
# Initialize git if not already initialized
git init

# Stage and commit files (.env and credentials.json are automatically ignored)
git add .
git commit -m "feat: initial commit with Cloud Functions entrypoint and CI/CD workflow"

# Rename branch to main
git branch -M main

# Link your GitHub repository (replace with your repo URL)
git remote add origin https://github.com/<YOUR-USERNAME>/strava-fitness-analytics.git

# Push to GitHub
git push -u origin main
```

---

### 2. Configure GitHub Secrets

Go to your repository on GitHub: **Settings** > **Secrets and variables** > **Actions** > **New repository secret**.

Add the following repository secrets:

| Secret Name | Value Description | Example / Source |
| :--- | :--- | :--- |
| `GCP_SA_KEY` | Entire JSON content of your GCP Service Account Key | Content of `credentials.json` |
| `GCP_PROJECT_ID` | Your GCP Project ID | `strava-sync-505308` |
| `GCP_REGION` | Desired Cloud Functions region | `asia-southeast1` (or `us-central1`) |
| `STRAVA_CLIENT_ID` | Your Strava API Client ID | From your `.env` |
| `STRAVA_CLIENT_SECRET` | Your Strava API Client Secret | From your `.env` |
| `STRAVA_REFRESH_TOKEN` | Your Strava OAuth Refresh Token | From your `.env` |

---

### 3. Google Cloud Permissions Required

Ensure the Service Account used in `GCP_SA_KEY` has the following roles assigned in **GCP Console > IAM & Admin**:

- **Cloud Functions Admin** (`roles/cloudfunctions.admin`)
- **Cloud Run Admin** (`roles/run.admin`) *(needed for Cloud Functions Gen 2)*
- **Service Account User** (`roles/iam.serviceAccountUser`)
- **Artifact Registry Writer** (`roles/artifactregistry.writer`)
- **BigQuery Data Editor** (`roles/bigquery.dataEditor`)
- **BigQuery Job User** (`roles/bigquery.jobUser`)

Also ensure the required GCP APIs are enabled:
```bash
gcloud services enable cloudfunctions.googleapis.com run.googleapis.com artifactregistry.googleapis.com cloudscheduler.googleapis.com bigquery.googleapis.com
```

---

### 4. Scheduling Automated Runs with Google Cloud Scheduler

To trigger the Cloud Function automatically every day at 8:00 PM (replacing the local Windows Task Scheduler):

1. Go to **Google Cloud Console** > **Cloud Scheduler** > **Create Job**.
2. Configure the job:
   - **Name:** `daily-strava-sync`
   - **Region:** Same region as your function (e.g. `asia-southeast1`)
   - **Frequency:** `0 20 * * *` *(Daily at 20:00 / 8:00 PM)*
   - **Timezone:** Select your local timezone (e.g., `Asia/Kuala_Lumpur` / `Asia/Singapore` / `Asia/Manila`)
   - **Target type:** `HTTP`
   - **URL:** Your deployed Cloud Function Trigger URL (found in Cloud Functions console)
   - **HTTP method:** `POST` or `GET`
   - **Auth header:** `Add OIDC token`
   - **Service account:** `strava-bigquery-loader@strava-sync-505308.iam.gserviceaccount.com`
3. Click **Create**.

---

### 5. Local Execution

You can still run the script locally at any time:
```powershell
python sync.py
```
It will automatically detect `credentials.json` and `.env` when run locally.
