"""
One-Time Google Fit OAuth2 Token Generator
------------------------------------------
Run this script to authenticate your Pixel 8a's Google account
and generate your permanent GOOGLE_FIT_REFRESH_TOKEN.
"""

import os
import urllib.parse
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("GOOGLE_FIT_CLIENT_ID") or input("Enter your GCP OAuth Client ID: ").strip()
client_secret = os.getenv("GOOGLE_FIT_CLIENT_SECRET") or input("Enter your GCP OAuth Client Secret: ").strip()
redirect_uri = "http://localhost"
scope = "https://www.googleapis.com/auth/fitness.activity.read"

auth_url = (
    f"https://accounts.google.com/o/oauth2/v2/auth?"
    f"client_id={client_id}&"
    f"redirect_uri={redirect_uri}&"
    f"response_type=code&"
    f"scope={urllib.parse.quote(scope)}&"
    f"access_type=offline&prompt=consent"
)

print("\n" + "="*70)
print("👉 STEP 1: Copy and paste this authorization URL into your browser:")
print("="*70)
print(auth_url)
print("="*70 + "\n")

print("👉 STEP 2: Sign in with the Google Account that is linked to your Pixel 8a.")
print("   When prompted with 'Google hasn't verified this app', click 'Advanced' -> 'Go to app (unsafe)' and accept.")
print("   Your browser will redirect to a blank or 'Unable to connect' page starting with 'http://localhost/?code=...'.\n")

callback_url = input("👉 STEP 3: Paste the full redirected URL (or just the code) here: ").strip()

# Extract code from URL if full URL is pasted
if "code=" in callback_url:
    query_params = urllib.parse.parse_qs(urllib.parse.urlparse(callback_url).query)
    code = query_params.get("code", [None])[0]
else:
    code = callback_url

if not code:
    print("❌ Error: No authorization code provided.")
    exit(1)

print("\n🔄 Exchanging authorization code for permanent Refresh Token...")
token_url = "https://oauth2.googleapis.com/token"
payload = {
    "client_id": client_id,
    "client_secret": client_secret,
    "code": code,
    "grant_type": "authorization_code",
    "redirect_uri": redirect_uri,
}

response = requests.post(token_url, data=payload)
if response.status_code != 200:
    print(f"❌ Error exchanging code: {response.text}")
    exit(1)

tokens = response.json()
refresh_token = tokens.get("refresh_token")

print("\n" + "="*70)
print("🎉 SUCCESS! HERE ARE YOUR GOOGLE FIT CREDENTIALS:")
print("="*70)
print(f"GOOGLE_FIT_CLIENT_ID={client_id}")
print(f"GOOGLE_FIT_CLIENT_SECRET={client_secret}")
print(f"GOOGLE_FIT_REFRESH_TOKEN={refresh_token}")
print("="*70)
print("\nAdd these 3 lines to your '.env' file in 'C:\\Users\\My PC\\strava-fitness-analytics\\.env'.")
