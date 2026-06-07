import requests

params = {
    "lon": -95.63,   # Brazos Bend
    "lat": 29.37,
    "product": "astro",
    "output": "json",
}

resp = requests.get("http://www.7timer.info/bin/api.pl", params=params)
data = resp.json()

# data["dataseries"] is a list of 3-hour intervals
for slot in data["dataseries"]:
    print(
        f"T+{slot['timepoint']:3}h | "
        f"Cloud: {slot['cloudcover']} | "
        f"Seeing: {slot['seeing']} | "
        f"Trans: {slot['transparency']} | "
        f"LI: {slot['lifted_index']} | "
        f"RH: {slot['rh2m']} | "
        f"Wind: {slot['wind10m']['speed']} {slot['wind10m']['direction']}"
    )