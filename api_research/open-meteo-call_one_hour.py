import requests

params = {
    "latitude": 29.37,        # Brazos Bend State Park
    "longitude": -95.63,
    "hourly": [
        "cloud_cover"
    ],
    "forecast_days": 1,
    "timezone": "America/Chicago",
}

resp = requests.get("https://api.open-meteo.com/v1/forecast", params=params)
data = resp.json()

import json
print(json.dumps(data, indent=2))