"""Download ransomware victim claims (Ransomware.live) and GDP (World Bank)."""
import json
import time
from datetime import date
from pathlib import Path

import requests

RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

START_YEAR = 2023          # how far back to go
HEADERS = {"User-Agent": "ransomware-economics (personal research)"}


def months_to_fetch():
    """Yield every (year, month) from START_YEAR up to this month."""
    today = date.today()
    for year in range(START_YEAR, today.year + 1):
        for month in range(1, 13):
            if (year, month) > (today.year, today.month):
                return
            yield year, month


def fetch_victims(year, month):
    """Save one month of victim claims to data/raw/."""
    out_file = RAW_DIR / f"victims_{year}_{month:02d}.json"
    this_month = (year, month) == (date.today().year, date.today().month)
    if out_file.exists() and not this_month:
        print(f"  {year}-{month:02d}: already have it, skipping")
        return
    url = f"https://api.ransomware.live/v2/victims/{year}/{month}"
    response = requests.get(url, headers=HEADERS, timeout=60)
    if response.status_code != 200:
        print(f"  {year}-{month:02d}: error {response.status_code}")
        return
    data = response.json()
    out_file.write_text(json.dumps(data))
    print(f"  {year}-{month:02d}: saved {len(data)} records")


def fetch_gdp(year=2024):
    """Save GDP (current US$) for every country from the World Bank."""
    url = ("https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD"
           f"?format=json&date={year}&per_page=400")
    response = requests.get(url, timeout=60)
    rows = response.json()[1]          # item 0 is page info, item 1 is the data
    (RAW_DIR / "gdp.json").write_text(json.dumps(rows))
    print(f"  GDP: saved {len(rows)} countries")


if __name__ == "__main__":
    print("Downloading victim claims...")
    for year, month in months_to_fetch():
        fetch_victims(year, month)
        time.sleep(2)              # be polite: one request every 2 seconds
    print("Downloading GDP...")
    fetch_gdp()
    print("Done.")