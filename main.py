import functions_framework
from sync import sync_strava, run_sync
from sync_google_fit import run_fit_sync

@functions_framework.http
def main(request):
    """Entry point for Google Cloud Functions."""
    strava_result = sync_strava(request)
    try:
        run_fit_sync(days=7)
    except Exception as e:
        print(f"⚠️ Google Fit sync notice: {e}")
    return strava_result

if __name__ == "__main__":
    run_sync()
    try:
        run_fit_sync(days=7)
    except Exception as e:
        print(f"⚠️ Google Fit sync notice: {e}")

