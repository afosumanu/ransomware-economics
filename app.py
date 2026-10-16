"""Ransomware Economics Dashboard."""
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Ransomware Economics", layout="wide")


# =============================================================================
# Data
# =============================================================================
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
pay_yr["year"] = pay_yr["year"].astype(int)

months = sorted(sector["month"].unique())

# Yearly victim totals, full calendar years only (12 months of data)
_yr = sector.assign(year=sector["month"].astype(str).str[:4].astype(int))
_months_per_year = _yr.groupby("year")["month"].nunique()
full_years = _months_per_year[_months_per_year == 12].index
yearly = (_yr[_yr["year"].isin(full_years)]
          .groupby("year")["victims"].sum().rename("victims"))

# Victims and payments side by side, for the years both sources cover
vp = (yearly.reset_index()
      .merge(pay_yr[["year", "total_paid_usd"]], on="year", how="inner")
      .sort_values("year"))
vp["paid_per_victim"] = vp["total_paid_usd"] / vp["victims"]


# =============================================================================
# Chart helpers
# =============================================================================
def hbar(df, x, y, title, fmt=",", **kwargs):
    """Horizontal bar with the largest bar on top and clean hover text."""
    fig = px.bar(df, x=x, y=y, orientation="h", title=title, **kwargs)
    fig.update_yaxes(categoryorder="total ascending", title=None)
    fig.update_traces(hovertemplate="%{y}: %{x:" + fmt + "}<extra></extra>")
    return fig


def show(fig, **kwargs):
    st.plotly_chart(fig, width="stretch", **kwargs)


def pct(a, b):
    """Change from b to a as a fraction, or None if b is zero/missing."""
    return (a / b - 1) if b else None


# =============================================================================
# Header
# =============================================================================
st.title("Ransomware Economics Dashboard")
st.caption("Who gets hit, who pays, and is it rising? Victim counts are attacker "
           "claims from public leak-site trackers, not confirmed incidents.")
st.caption(f"Victim data through **{months[-1]}** (the latest month may still "
           "be filling in, so it's excluded by default).")

with st.expander("About the data and its limits"):
    st.markdown("""
- **Claimed victims** are organizations that ransomware groups post on their
  leak sites. Victims who pay quickly are often never posted, so these counts
  under-represent paying victims and over-represent those who refused.
- Groups sometimes exaggerate, re-post old victims, or claim attacks they
  didn't carry out. Treat counts as a signal of activity, not ground truth.
- **"Unknown" country** means the leak post didn't identify a location. Those
  victims are counted in totals but don't appear on the map.
- **On-chain payments** (Chainalysis) only cover ransoms traced on the
  blockchain, so they're a lower bound and are revised upward over time.
- **Payment rate** (Coveware) comes from Coveware's own incident-response
  caseload, not from all victims worldwide.
- **Per $100bn GDP** adjusts for economy size. It gets noisy for countries with
  only a few victims, so use the minimum-victims filter on the Countries tab.
""")

# =============================================================================
# Sidebar filters
# =============================================================================
st.sidebar.header("Filters")
start, end = st.sidebar.select_slider(
    "Months", options=months, value=(months[0], months[-2]),  # -2 skips the unfinished month
    help="Applies to the headline count, Trend, Sectors and Groups tabs.")

top = sector.groupby("sector")["victims"].sum().nlargest(12).index.tolist()
picked = st.sidebar.multiselect(
    "Sectors to compare", top, default=top[:5],
    help="Highlighted in the sector bar chart and plotted over time.")

s = sector[(sector["month"] >= start) & (sector["month"] <= end)]
g = group[(group["month"] >= start) & (group["month"] <= end)]

st.sidebar.divider()
st.sidebar.subheader("Download filtered data")
st.sidebar.download_button("Victims by sector (CSV)", s.to_csv(index=False),
                           file_name=f"ransomware_sectors_{start}_{end}.csv",
                           mime="text/csv")
st.sidebar.download_button("Victims by group (CSV)", g.to_csv(index=False),
                           file_name=f"ransomware_groups_{start}_{end}.csv",
                           mime="text/csv")

# =============================================================================
# Headline numbers
# =============================================================================
i0, i1 = months.index(start), months.index(end)
n = i1 - i0 + 1
prev_months = months[i0 - n:i0] if i0 - n >= 0 else []
cur_total = int(s["victims"].sum())
prev_total = int(sector[sector["month"].isin(prev_months)]["victims"].sum())
delta = pct(cur_total, prev_total) if prev_months else None

latest = pay_yr.sort_values("year").iloc[-1]
latest_q = pay_q.iloc[-1]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Claimed victims (selected months)", f"{cur_total:,}",
          delta=f"{delta:+.0%} vs previous {n} months" if delta is not None else None,
          delta_color="inverse",
          help="Leak-site claims in the selected months. The arrow compares with "
               "the same number of months just before (red = more victims).")
c2.metric(f"Ransom paid on-chain, {int(latest['year'])}",
          f"${latest['total_paid_usd'] / 1e6:,.0f}M",
          help="Ransom payments traced on the blockchain by Chainalysis. A lower bound.")
c3.metric(f"Median payment, {int(latest['year'])}",
          f"${latest['median_payment_usd']:,.0f}",
          help="Half of payments were smaller than this, half larger.")
c4.metric(f"Share who paid, {latest_q['quarter']}",
          f"{latest_q['payment_rate_pct']:.0f}%",
          help="Share of Coveware's ransomware cases where the victim paid.")

trend, sectors, groups, countries, payments, analysis = st.tabs(
    ["Trend", "Sectors", "Groups", "Countries", "Payments", "Analysis"])

# =============================================================================
# Trend
# =============================================================================
with trend:
    monthly = s.groupby("month")["victims"].sum().reset_index()
    fig = px.line(monthly, x="month", y="victims", markers=True,
                  title="Claimed victims per month")
    fig.update_traces(hovertemplate="%{x}: %{y:,} victims<extra></extra>")
    fig.update_yaxes(title="Victims", tickformat=",")
    fig.update_xaxes(title=None)
    show(fig)
    if not monthly.empty:
        peak = monthly.loc[monthly["victims"].idxmax()]
        avg = monthly["victims"].mean()
        st.caption(f"Busiest month in this range: **{peak['month']}** with "
                   f"{int(peak['victims']):,} claims, against an average of "
                   f"{avg:,.0f} per month.")

# =============================================================================
# Sectors
# =============================================================================
with sectors:
    totals = s.groupby("sector")["victims"].sum().nlargest(12).reset_index()
    totals["status"] = totals["sector"].isin(picked).map(
        {True: "Selected", False: "Other"})
    fig = hbar(totals, "victims", "sector", "Victims by sector (selected months)",
               color="status",
               color_discrete_map={"Selected": "#d62728", "Other": "#bbbbbb"})
    fig.update_layout(legend_title=None)
    show(fig)
    if not totals.empty and s["victims"].sum():
        lead = totals.iloc[0]
        st.caption(f"**{lead['sector']}** accounts for "
                   f"{lead['victims'] / s['victims'].sum():.0%} of all claims "
                   "in the selected months.")

    over_time = s[s["sector"].isin(picked)]
    if over_time.empty:
        st.info("Pick at least one sector in the sidebar to see it over time.")
    else:
        fig = px.line(over_time, x="month", y="victims", color="sector",
                      title="Selected sectors over time")
        fig.update_traces(hovertemplate="%{x}: %{y:,}<extra></extra>")
        fig.update_xaxes(title=None)
        fig.update_layout(legend_title=None)
        show(fig)

# =============================================================================
# Groups
# =============================================================================
with groups:
    by_group = g.groupby("group")["victims"].sum().sort_values(ascending=False)
    top_groups = by_group.head(10).reset_index()
    show(hbar(top_groups, "victims", "group", "Most active groups (selected months)"))
    if len(by_group) and by_group.sum():
        st.caption(f"The top 5 groups account for "
                   f"{by_group.head(5).sum() / by_group.sum():.0%} of claims "
                   f"in the selected months, out of {len(by_group):,} active groups.")

    st.subheader("Look up a group")
    if by_group.empty:
        st.info("No group activity in the selected months.")
    else:
        pick_group = st.selectbox("Group", by_group.index.tolist(),
                                  help="Ordered from most to least active.")
        one = g[g["group"] == pick_group].sort_values("month")
        m1, m2, m3 = st.columns(3)
        m1.metric("Claimed victims", f"{int(one['victims'].sum()):,}")
        m2.metric("Share of all claims", f"{one['victims'].sum() / by_group.sum():.1%}")
        m3.metric("Rank", f"#{by_group.index.get_loc(pick_group) + 1} of {len(by_group)}")
        fig = px.bar(one, x="month", y="victims",
                     title=f"{pick_group}: claimed victims per month")
        fig.update_traces(hovertemplate="%{x}: %{y:,}<extra></extra>",
                          marker_color="#d62728")
        fig.update_xaxes(title=None)
        show(fig)

# =============================================================================
# Countries
# =============================================================================
with countries:
    st.write("Last 12 months. 'Per $100bn GDP' adjusts for economy size. "
             "Small victim counts make the per-GDP rate noisy, so use the "
             "minimum-victims filter to hide countries with too few cases.")

    f1, f2 = st.columns(2)
    measure = f1.radio("Color the map by",
                       ["Victims (raw count)", "Victims per $100bn GDP"],
                       horizontal=True)
    min_victims = f2.slider(
        "Minimum victims to include", min_value=1, max_value=100, value=20,
        help="Countries below this count are left off the map and the rankings.")

    metric = "victims_12m" if measure.startswith("Victims (raw") else "victims_per_100bn_gdp"
    eligible = country[country["victims_12m"] >= min_victims]
    mapped = eligible[eligible["countryiso3code"].notna()].dropna(subset=[metric])

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
    show(fig_map)

    left, right = st.columns(2)
    with left:
        show(hbar(eligible.nlargest(10, "victims_12m"), "victims_12m", "country",
                  "Most victims"))
    with right:
        show(hbar(eligible.dropna(subset=["victims_per_100bn_gdp"])
                  .nlargest(10, "victims_per_100bn_gdp"),
                  "victims_per_100bn_gdp", "country",
                  "Most victims per $100bn GDP", fmt=",.2f"))

    st.download_button("Download country data (CSV)",
                       country.drop(columns="countryiso3code").to_csv(index=False),
                       file_name="ransomware_countries_12m.csv", mime="text/csv")

# =============================================================================
# Payments
# =============================================================================
with payments:
    fig = px.bar(pay_yr, x="year", y="total_paid_usd",
                 title="Total ransom paid on-chain per year (Chainalysis)")
    fig.update_traces(hovertemplate="%{x}: $%{y:,.0f}<extra></extra>")
    fig.update_yaxes(title=None, tickprefix="$", tickformat="~s")
    fig.update_xaxes(title=None, dtick=1)
    show(fig)

    fig = px.line(pay_q, x="quarter", y="payment_rate_pct", markers=True,
                  title="Share of victims who paid, by quarter (Coveware)")
    fig.update_traces(hovertemplate="%{x}: %{y:.0f}%<extra></extra>")
    fig.update_yaxes(title=None, ticksuffix="%")
    fig.update_xaxes(title=None)
    show(fig)

    if len(vp) >= 2:
        st.subheader("More victims, less money")
        base = vp.iloc[0]
        idx = pd.DataFrame({
            "year": vp["year"],
            "Claimed victims": vp["victims"] / base["victims"] * 100,
            "On-chain payments": vp["total_paid_usd"] / base["total_paid_usd"] * 100,
        }).melt(id_vars="year", var_name="series", value_name="index")
        fig = px.line(idx, x="year", y="index", color="series", markers=True,
                      title=f"Victims vs payments, indexed ({int(base['year'])} = 100)",
                      color_discrete_map={"Claimed victims": "#d62728",
                                          "On-chain payments": "#1f77b4"})
        fig.add_hline(y=100, line_dash="dot", line_color="grey")
        fig.update_traces(hovertemplate="%{x}: %{y:.0f}<extra></extra>")
        fig.update_yaxes(title=None)
        fig.update_xaxes(title=None, dtick=1)
        fig.update_layout(legend_title=None)
        show(fig)
        st.caption("Both lines start at 100. A gap opening between them means "
                   "attackers are claiming more victims but collecting less in total.")

        fig = px.bar(vp, x="year", y="paid_per_victim",
                     title="On-chain payments per claimed victim")
        fig.update_traces(hovertemplate="%{x}: $%{y:,.0f}<extra></extra>",
                          marker_color="#1f77b4")
        fig.update_yaxes(title=None, tickprefix="$", tickformat=",")
        fig.update_xaxes(title=None, dtick=1)
        show(fig)
        st.caption("Total payments divided by claimed victims. This isn't the "
                   "average ransom (most posted victims didn't pay); it's a rough "
                   "measure of how much each claimed attack earns the ecosystem.")

# =============================================================================
# Analysis (computed from the data, so it updates when the data does)
# =============================================================================
with analysis:
    st.markdown("### Which sectors and countries are most targeted by ransomware, "
                "how often do victims pay, and is the threat rising?")
    st.caption(f"Year-over-year figures use full calendar years. Sector and group "
               f"rankings follow the selected months ({start} to {end}). "
               "Country figures cover the last 12 months.")

    # ---- Inputs for the narrative ----
    top_sectors = s.groupby("sector")["victims"].sum().nlargest(3)
    top5_groups = g.groupby("group")["victims"].sum().nlargest(5)
    known = country[country["country"].str.lower() != "unknown"]
    top_raw = known.nlargest(1, "victims_12m")["country"].tolist()
    top_sized = (country[country["victims_12m"] >= 20]
                 .nlargest(3, "victims_per_100bn_gdp")["country"].tolist())
    rate = latest_q["payment_rate_pct"]
    record_low = rate <= pay_q["payment_rate_pct"].min()

    # ---- BLUF ----
    st.markdown("#### BLUF")
    if len(vp) >= 2:
        y0, y1 = int(vp["year"].iloc[0]), int(vp["year"].iloc[-1])
        v_chg = pct(vp["victims"].iloc[-1], vp["victims"].iloc[0])
        p_chg = pct(vp["total_paid_usd"].iloc[-1], vp["total_paid_usd"].iloc[0])
        rate_text = (f"dropped to a record-low {rate:.0f}%" if record_low
                     else f"stood at {rate:.0f}% in {latest_q['quarter']}")
        st.markdown(
            f"Ransomware is {'rising' if v_chg > 0 else 'falling'} in volume and "
            f"{'earning less' if p_chg < 0 else 'earning more'} in total. Claimed "
            f"victims {'rose' if v_chg > 0 else 'fell'} about {abs(v_chg):.0%} from "
            f"{y0} to {y1}, while on-chain payments "
            f"{'fell' if p_chg < 0 else 'rose'} {abs(p_chg):.0%} and the share of "
            f"victims who pay {rate_text}.")
    st.markdown(
        f"{', '.join(top_sectors.index[:-1])} and {top_sectors.index[-1]} are hit "
        f"hardest. {top_raw[0] if top_raw else 'The leading country'} has by far the "
        f"most victims, but adjusted for economy size, "
        f"{', '.join(top_sized[:-1])} and {top_sized[-1]} are hit harder. "
        f"A handful of groups, led by {top5_groups.index[0]}, account for most of "
        f"the activity."
        if len(top_sectors) >= 2 and len(top_sized) >= 2 and len(top5_groups)
        else "Not enough data in the selected range for a sector/country summary.")

    # ---- Year over year ----
    st.markdown("**Is the threat rising, and are payments falling?**")
    yoy = vp.copy()
    yoy["victims_change"] = yoy["victims"].pct_change() * 100
    yoy["paid_change"] = yoy["total_paid_usd"].pct_change() * 100
    st.dataframe(
        yoy[["year", "victims", "victims_change", "total_paid_usd",
             "paid_change", "paid_per_victim"]],
        hide_index=True, width="stretch",
        column_config={
            "year": st.column_config.NumberColumn("Year", format="%d"),
            "victims": st.column_config.NumberColumn("Claimed victims", format="%,d"),
            "victims_change": st.column_config.NumberColumn("Victims vs prior year",
                                                            format="%+.0f%%"),
            "total_paid_usd": st.column_config.NumberColumn("Paid on-chain",
                                                            format="$%,.0f"),
            "paid_change": st.column_config.NumberColumn("Payments vs prior year",
                                                         format="%+.0f%%"),
            "paid_per_victim": st.column_config.NumberColumn("Paid per claimed victim",
                                                             format="$%,.0f"),
        })

    # ---- Sectors and groups ----
    a, b = st.columns(2)
    with a:
        st.markdown("**Top 3 sectors (selected months)**")
        for name, val in top_sectors.items():
            st.markdown(f"- **{name}:** {int(val):,}")
    with b:
        st.markdown("**Top 5 groups (selected months)**")
        for name, val in top5_groups.items():
            st.markdown(f"- **{name}:** {int(val):,}")

    # ---- Countries ----
    st.markdown("**Which countries are hit most, raw and for their size?**")
    st.caption("Click a column header to sort. Per-GDP ranking only includes "
               "countries with 20+ victims.")
    cols = ["country", "victims_12m", "victims_per_100bn_gdp"]
    cfg = {
        "country": "Country",
        "victims_12m": st.column_config.NumberColumn("Victims (12m)", format="%,d"),
        "victims_per_100bn_gdp": st.column_config.NumberColumn("Per $100bn GDP",
                                                               format="%.2f"),
    }
    a, b = st.columns(2)
    with a:
        st.markdown("Most victims")
        st.dataframe(country.nlargest(10, "victims_12m")[cols], hide_index=True,
                     width="stretch", column_config=cfg)
    with b:
        st.markdown("Most victims per $100bn GDP")
        st.dataframe(country[country["victims_12m"] >= 20]
                     .nlargest(10, "victims_per_100bn_gdp")[cols],
                     hide_index=True, width="stretch", column_config=cfg)


st.divider()
st.caption("Sources: Ransomware.live (victim claims), Chainalysis (on-chain payments), "
           "Coveware (payment rates), World Bank (GDP). Public data only. "
           "Built by Augustine Fosu Manu.")