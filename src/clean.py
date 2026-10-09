"""Clean raw downloads, save a local database, export summary tables."""
import json
import sqlite3
from pathlib import Path

import pandas as pd

RAW = Path("data/raw")
OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)

# Ransomware.live field name  ->  our name. Fix the left side if 4a showed different names.
COLUMN_MAP = {
    "victim": "victim",
    "group": "group",
    "discovered": "discovered",
    "country": "country",
    "activity": "sector",
}


def load_victims():
    frames = []
    for f in sorted(RAW.glob("victims_*.json")):
        data = json.loads(f.read_text())
        if isinstance(data, dict):                 # some responses wrap the list
            data = data.get("victims", data.get("data", []))
        frames.append(pd.json_normalize(data))
    df = pd.concat(frames, ignore_index=True)
    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing columns {missing}. Available: {list(df.columns)}")
    return df[list(COLUMN_MAP)].rename(columns=COLUMN_MAP)


def clean(df):
    df["discovered"] = pd.to_datetime(df["discovered"], errors="coerce")
    df = df.dropna(subset=["discovered"]).copy()
    df["month"] = df["discovered"].dt.to_period("M").astype(str)
    df["country"] = df["country"].fillna("").str.upper().str.strip().replace("", "Unknown")
    df["sector"] = df["sector"].fillna("").str.strip().replace(
        {"": "Unknown", "Not Found": "Unknown"})
    df["group"] = df["group"].fillna("unknown").str.lower().str.strip()
    # The same victim re-posted by the same group counts once
    return df.drop_duplicates(subset=["victim", "group"])


def load_gdp():
    rows = json.loads((RAW / "gdp.json").read_text())
    gdp = pd.DataFrame(
        {"country": r["country"]["id"], "gdp_usd": r["value"]} for r in rows if r["value"])
    return gdp


if __name__ == "__main__":
    victims = clean(load_victims())
    print(f"Clean victim claims: {len(victims):,}")

    # 1. Full table -> local database only (ignored by Git; contains names)
    with sqlite3.connect("data/ransomware.db") as con:
        victims.to_sql("victims", con, if_exists="replace", index=False)

    # 2. Summary tables -> data/processed/ (no victim names; these go public)
    for col in ["sector", "country", "group"]:
        summary = victims.groupby(["month", col]).size().reset_index(name="victims")
        summary.to_csv(OUT / f"monthly_by_{col}.csv", index=False)

    last_12 = victims[victims["discovered"] >= victims["discovered"].max() - pd.DateOffset(months=12)]
    by_country = last_12.groupby("country").size().reset_index(name="victims_12m")
    by_country = by_country.merge(load_gdp(), on="country", how="left")
    by_country["victims_per_100bn_gdp"] = by_country["victims_12m"] / (by_country["gdp_usd"] / 1e11)
    by_country.to_csv(OUT / "country_summary.csv", index=False)
    print("Saved summary tables to data/processed/")