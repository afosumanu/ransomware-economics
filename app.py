"""Ransomware Economics Dashboard."""
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Ransomware Economics", layout="wide")


@st.cache_data
def load():
    p = "data/processed/"
    return (
        pd.read_csv(p + "monthly_by_sector.csv"),
        pd.read_csv(p + "monthly_by_group.csv"),
        pd.read_csv(p + "country_summary.csv"),
        pd.read_csv("data/manual/payments_annual.csv"),
        pd.read_csv("data/manual/payments_quarterly.csv"),
    )


@st.cache_data
def add_iso3(df):
    """Make sure the country table has a three-letter code column for the map.

    Uses countryiso3code if it is already there (e.g. from the World Bank GDP
    merge). Otherwise converts the country column (name or 2-letter code) with
    pycountry. Rows it can't match, like "Unknown", get no code and drop off
    the map.
    """
    df = df.copy()
    if "countryiso3code" in df.columns:
        return df
    import pycountry

    def to_iso3(value):
        try:
            return pycountry.countries.lookup(str(value)).alpha_3
        except LookupError:
            return None

    df["countryiso3code"] = df["country"].apply(to_iso3)
    return df


sector, group, country, pay_yr, pay_q = load()
country = add_iso3(country)

st.title("Ransomware Economics Dashboard")
st.caption("Who gets hit, who pays, and is it rising? Victim counts are attacker "
           "claims from public leak-site trackers, not confirmed incidents.")

# ---- Sidebar filters ----
months = sorted(sector["month"].unique())
start, end = st.sidebar.select_slider(
    "Months", options=months, value=(months[0], months[-2]))  # -2 skips the unfinished month
top = sector.groupby("sector")["victims"].sum().nlargest(12).index.tolist()
picked = st.sidebar.multiselect("Sectors to compare", top, default=top[:5])

s = sector[(sector["month"] >= start) & (sector["month"] <= end)]
g = group[(group["month"] >= start) & (group["month"] <= end)]

# ---- Headline numbers ----
latest = pay_yr.sort_values("year").iloc[-1]
c1, c2, c3 = st.columns(3)
c1.metric("Claimed victims (selected months)", f"{int(s['victims'].sum()):,}")
c2.metric(f"Ransom paid on-chain, {int(latest['year'])}",
          f"${latest['total_paid_usd'] / 1e6:,.0f}M")
c3.metric(f"Median payment, {int(latest['year'])}",
          f"${latest['median_payment_usd']:,.0f}")

trend, sectors, countries, payments, analysis = st.tabs(
    ["Trend", "Sectors", "Countries", "Payments", "Analysis"])

with trend:
    monthly = s.groupby("month")["victims"].sum().reset_index()
    st.plotly_chart(px.line(monthly, x="month", y="victims",
                            title="Claimed victims per month"))
    top_groups = g.groupby("group")["victims"].sum().nlargest(10).reset_index()
    st.plotly_chart(px.bar(top_groups, x="victims", y="group", orientation="h",
                           title="Most active groups (selected months)"))

with sectors:
    totals = s.groupby("sector")["victims"].sum().nlargest(12).reset_index()
    st.plotly_chart(px.bar(totals, x="victims", y="sector", orientation="h",
                           title="Victims by sector"))
    over_time = s[s["sector"].isin(picked)]
    st.plotly_chart(px.line(over_time, x="month", y="victims", color="sector",
                            title="Selected sectors over time"))

with countries:
    st.write("Last 12 months. 'Per $100bn GDP' adjusts for economy size. "
             "Small victim counts make the per-GDP rate noisy, so use the "
             "minimum-victims filter to hide countries with too few cases.")

    # ---- Map filters ----
    f1, f2 = st.columns(2)
    measure = f1.radio(
        "Color the map by",
        ["Victims (raw count)", "Victims per $100bn GDP"],
        horizontal=True,
    )
    min_victims = f2.slider(
        "Minimum victims to include", min_value=1, max_value=100, value=20,
        help="Countries below this count are left off the map and the per-GDP ranking.",
    )

    metric = "victims_12m" if measure.startswith("Victims (raw") else "victims_per_100bn_gdp"
    mapped = country[
        (country["victims_12m"] >= min_victims)
        & country["countryiso3code"].notna()
    ].dropna(subset=[metric])

    # ---- World map ----
    fig_map = px.choropleth(
        mapped,
        locations="countryiso3code",
        locationmode="ISO-3",
        color=metric,
        hover_name="country",
        hover_data={"countryiso3code": False,
                    "victims_12m": ":,",
                    "victims_per_100bn_gdp": ":.2f"},
        labels={"victims_12m": "Victims (12m)",
                "victims_per_100bn_gdp": "Per $100bn GDP"},
        color_continuous_scale="Reds",
        title=f"{measure} by country (countries with {min_victims}+ victims)",
    )
    fig_map.update_geos(showframe=False, showcoastlines=False,
                        projection_type="natural earth")
    fig_map.update_layout(margin=dict(l=0, r=0, t=40, b=0), height=500)
    st.plotly_chart(fig_map, use_container_width=True)

    # ---- Top-10 bars (now follow the same minimum-victims filter) ----
    left, right = st.columns(2)
    raw = country[country["victims_12m"] >= min_victims].nlargest(10, "victims_12m")
    left.plotly_chart(px.bar(raw, x="victims_12m", y="country", orientation="h",
                             title="Most victims"))
    sized = country[country["victims_12m"] >= min_victims].nlargest(10, "victims_per_100bn_gdp")
    right.plotly_chart(px.bar(sized, x="victims_per_100bn_gdp", y="country",
                              orientation="h", title="Most victims per $100bn GDP"))

with payments:
    st.plotly_chart(px.bar(pay_yr, x="year", y="total_paid_usd",
                           title="Total ransom paid on-chain per year (Chainalysis)"))
    st.plotly_chart(px.line(pay_q, x="quarter", y="payment_rate_pct", markers=True,
                            title="Share of victims who paid, by quarter (Coveware)"))

with analysis:
    st.markdown("### Which sectors and countries are most targeted by ransomware, how often do victims pay, and is the threat rising?")

    st.markdown("#### BLUF")
    st.markdown("Ransomware is rising in volume and earning less per attack. Claimed victims rose about 66% from 2023 to 2025, while on-chain payments fell by a third and the share of victims who pay dropped to a record-low 23%.")
    st.markdown("Professional services, manufacturing and technology are hit hardest. The United States has by far the most victims, but adjusted for economy size, mid-sized economies such as Thailand, Malaysia and Argentina are hit harder. A handful of groups, led by Qilin, account for most of the activity.")

    st.markdown("**Is the number of claimed victims rising?**")
    st.markdown("""
    - **2023:** 4,904 victims
    - **2024:** 5,979 victims 
    - **2025:** 8,136 victims""")

    st.markdown("**Which Top 3 sectors are hit most?**")
    st.markdown("""Top Industries by Number of Victims

- **Professional Services:** 5,198
- **Manufacturing:** 4,653
- **Technology:** 3,476
""")

    st.markdown("**Which countries are hit most, raw and for their size?**")
    st.markdown("""Countries with the Most Reported Victims

- **United States (US):** 4,051 victims | $29.30T GDP | 13.83 victims
- **Unknown:** 618 victims | GDP data unavailable
- **Germany (DE):** 479 victims | $4.69T GDP | 10.22 victims
- **United Kingdom (GB):** 405 victims | $3.70T GDP | 10.96 victims 
- **Canada (CA):** 356 victims | $2.27T GDP | 15.68 victims
- **Italy (IT):** 280 victims | $2.38T GDP | 11.75 victims
- **France (FR):** 271 victims | $3.16T GDP | 8.57 victims
- **Brazil (BR):** 229 victims | $2.19T GDP | 10.48 victims
- **Spain (ES):** 212 victims | $1.73T GDP | 12.29 victims
- **India (IN):** 204 victims | $3.76T GDP | 5.42 victims
""")

    st.markdown("**How the two top-10 lists differ when sorted by 100 Bn GDP?**")
    st.markdown("""Countries Ranked by Victims per $100B GDP

- **Thailand (TH):** 114 victims | $529.39B GDP | 21.53 victims 
- **Malaysia (MY):** 81 victims | $422.23B GDP | 19.18 victims 
- **Argentina (AR):** 108 victims | $638.37B GDP | 16.92 victims
- **Canada (CA):** 356 victims | $2.27T GDP | 15.68 victims
- **Colombia (CO):** 63 victims | $420.50B GDP | 14.98 victims
- **Peru (PE):** 43 victims | $291.75B GDP | 14.74 victims
- **Czechia (CZ):** 51 victims | $347.08B GDP | 14.69 victims
- **United Arab Emirates (AE):** 81 victims | $552.32B GDP | 14.67 victims
- **Singapore (SG):** 84 victims | $572.88B GDP | 14.66 victims
- **United States (US):** 4,051 victims | $29.30T GDP | 13.83 victims""")
    
    st.markdown("**Which groups drive the activity?**")
    st.markdown("""
- Qilin: 2336
- Akira: 1632
- LockBit 3: 1598
- Play: 1288
- Clop: 1174
""")
    
    st.markdown("**Are victims rising while payments fall?**")
    st.markdown("""
- **2023:** 4,904 victims | Total paid: $1.23 billion
- **2024:** 5,979 victims | Total paid: $892 million
- **2025:** 8,136 victims | Total paid: $820 million
""")
    st.markdown("The number of claimed victims rose by 22% from 2023 to 2024 and by 36% from 2024 to 2025, while on-chain payments declined by approximately 28% and 8% over the same periods, respectively.")


st.divider()
st.caption("Sources: Ransomware.live (victim claims), Chainalysis (on-chain payments), "
           "Coveware (payment rates), World Bank (GDP). Public data only. "
           "Built by Augustine Fosu Manu.")