import functions_framework
from sync import sync_strava, run_sync

@functions_framework.http
def main(request):
    """Entry point for Google Cloud Functions."""
    return sync_strava(request)

if __name__ == "__main__":
    run_sync()
