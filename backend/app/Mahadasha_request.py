import json
import urllib.request
import urllib.error

import time



LAMBDA_URL="https://bivrov2febq5ued37psv2hcxyi0wlxet.lambda-url.ap-south-1.on.aws/"
BEARER_TOKEN= "f83c6105-1731-4cd9-9d94-9543ff01bfe1"



candidates = [
    "Dasha",
    "MahaDasha",
    "Mahadasha",
    "VimshottariDasha",
    "Vimshottari",
    "CurrentDasha",
    "CurrentMahadasha",
    "Antardasha",
    "Pratyantardasha",
    "DashaTree",
    "PlanetaryDasha",
    "AllDasha",
    "all_dasha",
]


for req_value in candidates:

    payload = {
        "requirements": [req_value],
        "date": "19/09/2006",
        "time": "07:30",
        "latitude": "15.1613581",
        "longitude": "77.3769363",
        "timezone_name": "Asia/Kolkata",
        "language": "English",
    }

    print(f"\nTrying requirement: {req_value}")

    success = False

    for attempt in range(1, 4):

        print(f"Attempt {attempt}/3")

        req = urllib.request.Request(
            LAMBDA_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {BEARER_TOKEN}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                response = json.loads(resp.read().decode("utf-8"))

            print(f"SUCCESS: '{req_value}' worked")
            print(json.dumps(response, indent=2)[:1000])

            success = True
            break

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            print(f"HTTP Error {e.code}: {body}")

        except Exception as e:
            print(f"Error: {e}")

        time.sleep(2)

print(f"\nRequirement: {req_value}")
print(json.dumps(response, indent=2))