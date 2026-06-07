import requests

params = {
    "latitude": 29.37,        # Brazos Bend State Park
    "longitude": -95.63,
    "hourly": [
        "cloud_cover",
        "cloud_cover_low",
        "cloud_cover_mid",
        "cloud_cover_high",
        "visibility",
        "relative_humidity_2m",
        "lifted_index",
        "cape",
        "is_day",
    ],
    "forecast_days": 3,
    "timezone": "America/Chicago",
}

resp = requests.get("https://api.open-meteo.com/v1/forecast", params=params)
data = resp.json()

import json
print(json.dumps(data, indent=2))