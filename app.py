"""Social Pulse: a CSV-first social media analytics dashboard."""

from datetime import timedelta
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analytics import (
    DataValidationError, REQUIRED_COLUMNS, WEEKDAYS, aggregate, csv_export,
    filter_posts, load_csv, metrics, previous_period, summary_lines, time_series,
    timing_data,
)
from ai_ui import render_ai_panel

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "social_media_sample.csv"
COLORS = {"Instagram": "#9D58CB", "TikTok": "#087F8C", "LinkedIn": "#3479C0", "Facebook": "#5B68BB", "YouTube": "#E98060"}
METRIC_LABELS = {
    "impressions": "Impressions", "reach": "Post reach (summed)",
    "engagements": "Engagement actions", "engagement_rate_pct": "Engagement rate (%)",
    "clicks": "Clicks", "ctr_pct": "Click-through rate (%)",
    "conversions": "Conversions", "followers_gained": "Attributed new followers",
    "spend_usd": "Spend (USD)", "revenue_usd": "Attributed revenue (USD)",
    "posts": "Posts", "cpc_usd": "CPC (USD)", "cpa_usd": "CPA (USD)", "roas": "ROAS (x)",
    "platform": "Platform", "content_type": "Format", "campaign": "Campaign",
    "traffic_type": "Traffic", "post_id": "Post ID", "published_at": "Published (PT)",
    "caption": "Caption", "conversion_rate_pct": "Conversion rate (%)",
}

st.set_page_config(page_title="Social Pulse | Social media analytics", page_icon="📊", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 3rem; padding-bottom: 2rem; max-width: 1550px;}
  h1 {letter-spacing: -1.4px; font-weight: 750 !important;}
  h2, h3 {letter-spacing: -.4px;}
  div[data-testid="stMetric"] {background: white; border: 1px solid #E0E8F0; border-radius: 12px; padding: 18px 18px 12px; min-height: 132px;}
  div[data-testid="stMetricValue"] {font-size: 1.9rem; color: #152E45;}
  div[data-testid="stMetricLabel"] {color: #617489;}
  div[data-testid="stTabs"] button {font-weight: 600;}
  .eyebrow {color: #087F8C; font-size: .78rem; font-weight: 700; letter-spacing: .15em; margin-bottom: 4px;}
  .hero-copy {color: #617489; font-size: 1rem; margin-top: -8px; margin-bottom: 24px;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False, max_entries=4)
def cached_load(payload):
    return load_csv(payload)


def number(value, kind="count"):
    if pd.isna(value) or not np.isfinite(value):
        return "N/A"
    if kind == "percent":
        return f"{value:.2f}%"
    if kind == "money":
        return f"${value:,.2f}"
    if kind == "multiple":
        return f"{value:.2f}x"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if value >= 10_000:
        return f"{value / 1000:.1f}K"
    return f"{value:,.0f}"


def change(value, old, kind="count", comparable=False):
    if not comparable or pd.isna(value) or pd.isna(old):
        return None
    if kind == "percent":
        delta = round(value - old, 2)
        return "0.00 pp" if delta == 0 else f"{delta:+.2f} pp"
    return f"{(value / old - 1) * 100:+.1f}%" if old > 0 else None


def chart(fig, key, height=330):
    fig.update_layout(
        height=height, margin=dict(l=12, r=12, t=30, b=25),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Arial, sans-serif", color="#41576D", size=12),
        legend_title_text="", legend=dict(orientation="h", y=1.12, x=0),
        hoverlabel=dict(bgcolor="white"),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#E4EBF2", zeroline=False)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key=key)


def table(df, columns=None, height="auto"):
    view = df[columns].copy() if columns else df.copy()
    config = {}
    for column in view:
        label = METRIC_LABELS.get(column, column.replace("_", " ").title())
        if column.endswith("_pct"):
            config[column] = st.column_config.NumberColumn(label, format="%.2f%%")
        elif column.endswith("_usd"):
            config[column] = st.column_config.NumberColumn(label, format="$%.2f")
        elif column == "roas":
            config[column] = st.column_config.NumberColumn(label, format="%.2fx")
        elif column == "published_at":
            config[column] = st.column_config.DatetimeColumn(label, format="MMM D, YYYY, h:mm a")
        elif pd.api.types.is_numeric_dtype(view[column]):
            config[column] = st.column_config.NumberColumn(label, format="localized")
        else:
            config[column] = st.column_config.TextColumn(label)
    st.dataframe(view, hide_index=True, use_container_width=True, column_config=config, height=height)


with st.sidebar:
    st.markdown("### Social Pulse")
    st.caption("Your content, in focus.")
    source = st.radio("Dataset", ["Sample dataset", "Upload CSV"], horizontal=True)
    uploaded = st.file_uploader("Choose a CSV", type=["csv"], disabled=source == "Sample dataset")
    if not SAMPLE.exists():
        st.error("Sample CSV is missing. Run python generate_sample_data.py to create it.")
        st.stop()
    sample_bytes = SAMPLE.read_bytes()
    st.download_button("Download sample CSV", sample_bytes, "social_media_sample.csv", "text/csv", use_container_width=True)
    if source == "Upload CSV" and uploaded is None:
        st.info("Upload your CSV to start. The sample download shows the required columns.")
        st.stop()
    payload = uploaded.getvalue() if source == "Upload CSV" else sample_bytes
    source_name = uploaded.name if source == "Upload CSV" else "Synthetic sample data"
    try:
        df = cached_load(payload)
    except DataValidationError as exc:
        st.error(str(exc))
        with st.expander("Required CSV columns", expanded=True):
            st.code(", ".join(REQUIRED_COLUMNS), language=None)
        st.stop()
    fingerprint = sha256(payload).hexdigest()[:12]
    st.divider()
    st.markdown("#### Filter posts")
    first_day, last_day = df.date.min().date(), df.date.max().date()
    preset_key = f"period_{fingerprint}"
    filter_keys = [preset_key, f"dates_{fingerprint}"] + [f"{c}_{fingerprint}" for c in ["platform", "content_type", "campaign", "traffic_type", "search"]]
    if st.button("Reset filters", use_container_width=True):
        for key in filter_keys:
            st.session_state.pop(key, None)
        st.rerun()
    preset = st.selectbox("Date range", ["Last 30 days", "Last 7 days", "All data", "Custom"], key=preset_key)
    if preset == "Custom":
        selected_dates = st.date_input("Start and end", (first_day, last_day), min_value=first_day, max_value=last_day, key=f"dates_{fingerprint}")
        if len(selected_dates) != 2:
            st.info("Choose both a start date and an end date.")
            st.stop()
        start, end = selected_dates
    else:
        end = last_day
        start = first_day if preset == "All data" else max(first_day, last_day - timedelta(days=29 if preset == "Last 30 days" else 6))
    choices = {}
    for column, label in [("platform", "Platforms"), ("content_type", "Content formats"), ("campaign", "Campaigns"), ("traffic_type", "Traffic type")]:
        options = sorted(df[column].unique())
        choices[column] = st.multiselect(label, options, default=options, key=f"{column}_{fingerprint}")
    search = st.text_input("Search captions, IDs, or campaigns", placeholder="Try product or POST-0042", key=f"search_{fingerprint}")
    st.caption(f"{len(df):,} posts loaded. Dates and publishing times use Pacific time.")

filtered = filter_posts(df, start, end, choices["platform"], choices["content_type"], choices["campaign"], choices["traffic_type"], search)
prior_start, prior_end = previous_period(start, end)
prior = filter_posts(df, prior_start, prior_end, choices["platform"], choices["content_type"], choices["campaign"], choices["traffic_type"], search)
# A partial date range in an uploaded file is not a complete comparison window.
comparable = first_day <= prior_start and last_day >= prior_end and not prior.empty

st.markdown('<div class="eyebrow">SOCIAL MEDIA ANALYTICS</div>', unsafe_allow_html=True)
title_col, export_col = st.columns([4, 1])
with title_col:
    st.title("Social Pulse")
    st.markdown('<div class="hero-copy">See what connects. Find your next content experiment.</div>', unsafe_allow_html=True)
with export_col:
    st.download_button("Export filtered posts", csv_export(filtered.drop(columns=["date", "weekday", "hour"])), "filtered_posts.csv", "text/csv", disabled=filtered.empty, use_container_width=True)
st.caption(f"{source_name}  ·  {start:%b %d, %Y} – {end:%b %d, %Y}  ·  {len(filtered):,} of {len(df):,} posts")
if source == "Sample dataset":
    st.caption("Fictional posts and metrics for learning. Patterns in this dataset are generated assumptions.")
if filtered.empty:
    st.info("No posts match these filters. Select at least one value in every filter, widen the date range, or clear your search.")
    st.stop()

current, previous = metrics(filtered), metrics(prior)
cards = st.columns(5)
for card, (field, label, kind) in zip(cards, [("impressions", "Impressions", "count"), ("engagements", "Engagement actions", "count"), ("engagement_rate_pct", "Engagement rate", "percent"), ("clicks", "Clicks", "count"), ("followers_gained", "New followers attributed", "count")]):
    card.metric(label, number(current[field], kind), change(current[field], previous[field], kind, comparable), help=f"{METRIC_LABELS[field]}. Exact value: {current[field]:,.2f}. See metric definitions below.")
if comparable:
    st.caption(f"Changes compare with {prior_start:%b %d} – {prior_end:%b %d, %Y}, using the same filters. Engagement-rate changes are percentage points (pp). File date coverage does not prove a complete export.")
else:
    st.caption("Previous-period changes are unavailable: the file lacks a full preceding window or matching posts.")

overview, content, campaigns, lab, ai = st.tabs(["Overview", "Content performance", "Campaigns", "Analysis lab", "AI assistant"])

with overview:
    left, right = st.columns([1.7, 1])
    with left:
        st.subheader("Performance over time")
        controls = st.columns(2)
        trend_metric = controls[0].selectbox("Trend metric", ["impressions", "engagements", "engagement_rate_pct", "clicks", "followers_gained"], format_func=METRIC_LABELS.get)
        frequency = controls[1].selectbox("Group dates", ["Daily", "Weekly", "Monthly"], index=1)
        trend = time_series(filtered, start, end, frequency)
        fig = px.area(trend, x="date", y=trend_metric, labels={"date": "Publishing date", trend_metric: METRIC_LABELS[trend_metric]}, color_discrete_sequence=["#087F8C"])
        fig.update_traces(line=dict(width=2), fillcolor="rgba(8,127,140,.13)", hovertemplate="%{x|%b %d, %Y}<br>%{y:,.2f}<extra></extra>")
        chart(fig, "trend")
        st.caption("Metrics are attributed to each post's publishing date. Weekly buckets start Monday; edge weeks and months may be partial.")
    with right:
        st.subheader("Platform comparison")
        platform_metric = st.selectbox("Compare platforms by", ["engagement_rate_pct", "impressions", "engagements", "clicks"], format_func=METRIC_LABELS.get)
        platform_summary = aggregate(filtered, "platform").sort_values(platform_metric)
        fig = px.bar(platform_summary, x=platform_metric, y="platform", orientation="h", color="platform", color_discrete_map=COLORS, labels={platform_metric: METRIC_LABELS[platform_metric], "platform": ""}, custom_data=["posts", "reach"])
        fig.update_layout(showlegend=False)
        fig.update_traces(hovertemplate="%{y}<br>Value: %{x:,.2f}<br>Posts: %{customdata[0]}<br>Post reach (summed): %{customdata[1]:,}<extra></extra>")
        chart(fig, "platform_bar")
    st.subheader("What the data shows")
    for line in summary_lines(filtered):
        st.markdown("• " + line.replace("$", "\\$"))
    st.caption("These summaries are calculated from the current filters. They do not use a language model.")
    with st.expander("Platform details"):
        table(aggregate(filtered, "platform"), ["platform", "posts", "impressions", "reach", "engagements", "engagement_rate_pct", "clicks", "ctr_pct", "followers_gained"])

with content:
    left, right = st.columns([1.1, 1])
    with left:
        st.subheader("Which formats connect?")
        format_summary = aggregate(filtered, "content_type").sort_values("engagement_rate_pct")
        fig = px.bar(format_summary, x="engagement_rate_pct", y="content_type", orientation="h", color_discrete_sequence=["#3479C0"], labels={"engagement_rate_pct": "Engagement rate (%)", "content_type": ""}, custom_data=["posts"])
        fig.update_traces(hovertemplate="%{y}<br>Engagement rate: %{x:.2f}%<br>Posts: %{customdata[0]}<extra></extra>")
        chart(fig, "format_bar")
        st.caption("Format comparisons pool platforms and campaigns. Use filters to compare similar posts.")
    with right:
        st.subheader("Reach and engagement")
        plot_data = filtered.copy()
        # Bubble size is visual only; zero-click posts still get a visible dot.
        plot_data["bubble_size"] = plot_data.clicks.clip(lower=1)
        fig = px.scatter(plot_data, x="reach", y="engagement_rate_pct", color="platform", color_discrete_map=COLORS, size="bubble_size", size_max=24, hover_name="post_id", hover_data={"content_type": True, "clicks": True, "bubble_size": False}, labels={"reach": "Reach per post", "engagement_rate_pct": "Engagement rate (%)"})
        chart(fig, "reach_scatter")
        st.caption("Each dot is one post. Bubble size represents clicks; zero-click posts use the smallest marker.")
    st.subheader("Post explorer")
    controls = st.columns([2, 1])
    rank_by = controls[0].selectbox("Rank posts by", ["engagements", "engagement_rate_pct", "impressions", "clicks", "followers_gained"], format_func=METRIC_LABELS.get)
    limit = controls[1].selectbox("Posts to show", [10, 25, 50, "All"], index=1)
    ranked = filtered.sort_values(rank_by, ascending=False, na_position="last")
    if limit != "All":
        ranked = ranked.head(limit)
    table(ranked, ["post_id", "published_at", "platform", "content_type", "campaign", "traffic_type", "caption", "impressions", "reach", "engagements", "engagement_rate_pct", "clicks", "conversions", "followers_gained"], height=410)

with campaigns:
    st.subheader("Campaign performance")
    paid = filtered.loc[filtered.traffic_type.eq("Paid")]
    st.caption("Campaign totals below include all matching posts. Paid efficiency uses only paid-post clicks, conversions, revenue, and spend. All money is USD.")
    money_cards = st.columns(4)
    for card, field, label, kind in [(money_cards[0], "spend_usd", "Paid spend", "money"), (money_cards[1], "roas", "Paid ROAS", "multiple"), (money_cards[2], "cpc_usd", "Paid cost per click", "money"), (money_cards[3], "cpa_usd", "Paid cost per conversion", "money")]:
        card.metric(label, number(current[field], kind))
    campaign_summary = aggregate(filtered, "campaign")
    table(campaign_summary, ["campaign", "posts", "impressions", "engagement_rate_pct", "clicks", "conversions", "revenue_usd", "spend_usd"])
    if paid.empty:
        st.info("No paid posts match the filters. Include Paid traffic to explore campaign efficiency.")
    else:
        paid_summary = aggregate(paid, "campaign")
        left, right = st.columns(2)
        with left:
            st.subheader("Paid spend and attributed revenue")
            values = paid_summary.melt(id_vars="campaign", value_vars=["spend_usd", "revenue_usd"], var_name="measure", value_name="usd")
            values["measure"] = values.measure.map({"spend_usd": "Spend", "revenue_usd": "Attributed revenue"})
            fig = px.bar(values, x="campaign", y="usd", color="measure", barmode="group", color_discrete_map={"Spend": "#3479C0", "Attributed revenue": "#087F8C"}, labels={"campaign": "", "usd": "USD"})
            chart(fig, "campaign_money")
        with right:
            st.subheader("Paid conversion efficiency")
            fig = px.scatter(paid_summary, x="spend_usd", y="conversions", size="posts", color="campaign", hover_name="campaign", hover_data=["roas", "cpa_usd"], labels={"spend_usd": "Spend (USD)", "conversions": "Conversions"}, color_discrete_sequence=list(COLORS.values()))
            chart(fig, "paid_scatter")
        table(paid_summary, ["campaign", "posts", "clicks", "conversions", "spend_usd", "revenue_usd", "cpc_usd", "cpa_usd", "roas"])
        st.caption("ROAS is attributed revenue divided by spend. It does not measure profit or establish causal lift.")

with lab:
    st.subheader("Find a publishing-time hypothesis")
    st.caption("Compare engagement rates by weekday and hour, using Pacific time. Use one platform and format to reduce mixing effects.")
    minimum = st.slider("Minimum posts per time slot", 1, 10, 3, help="Slots below this count are blank. This is a sample-size filter, not a statistical significance test.")
    slots = timing_data(filtered, minimum)
    rates = slots.pivot(index="weekday", columns="hour", values="engagement_rate_pct").reindex(index=WEEKDAYS, columns=range(24))
    counts = slots.pivot(index="weekday", columns="hour", values="posts").reindex(index=WEEKDAYS, columns=range(24)).fillna(0)
    fig = go.Figure(go.Heatmap(z=rates.values, x=list(range(24)), y=WEEKDAYS, customdata=counts.values, colorscale=[[0, "#E8F4F5"], [1, "#087F8C"]], colorbar=dict(title="ER (%)"), hoverongaps=False, hovertemplate="%{y} at %{x}:00 PT<br>Engagement rate: %{z:.2f}%<br>Posts: %{customdata:.0f}<extra></extra>"))
    fig.update_xaxes(title="Publishing hour (PT)", tickmode="linear", dtick=2)
    fig.update_yaxes(autorange="reversed")
    chart(fig, "time_heatmap", 360)
    eligible = slots.dropna(subset=["engagement_rate_pct"]).sort_values("engagement_rate_pct", ascending=False)
    if eligible.empty:
        st.info("No time slot has enough posts. Lower the minimum or widen the filters.")
    else:
        best = eligible.iloc[0]
        st.write(f"Highest observed slot: **{best.weekday}, {int(best.hour):02d}:00 PT** at **{best.engagement_rate_pct:.2f}%** engagement rate across **{int(best.posts)} posts**.")
    st.caption("Posting time is an observed association. Test it with similar content before changing your schedule.")
    st.divider()
    st.subheader("Ask the data")
    question = st.selectbox("Choose an analysis question", ["Which platform has the strongest engagement rate?", "Which content format earns the most saves per post?", "Which paid campaign has the highest ROAS?", "Which post attracted the most followers?"])
    if question.startswith("Which platform"):
        candidates = aggregate(filtered, "platform").query("posts >= @minimum").dropna(subset=["engagement_rate_pct"])
        if candidates.empty:
            st.info("No platform has enough posts with a defined engagement rate.")
        else:
            winner = candidates.sort_values("engagement_rate_pct", ascending=False).iloc[0]
            st.write(f"**{winner.platform}** leads with **{winner.engagement_rate_pct:.2f}%**, calculated from {int(winner.engagements):,} actions / {int(winner.reach):,} summed post reach across {int(winner.posts)} posts.")
    elif question.startswith("Which content"):
        candidates = aggregate(filtered, "content_type").query("posts >= @minimum").copy()
        if candidates.empty:
            st.info("No format has enough posts for this comparison.")
        else:
            candidates["saves_per_post"] = candidates.saves / candidates.posts
            winner = candidates.sort_values("saves_per_post", ascending=False).iloc[0]
            st.write(f"**{winner.content_type}** averages **{winner.saves_per_post:,.1f} saves per post** across {int(winner.posts)} posts.")
    elif question.startswith("Which paid"):
        paid = filtered.loc[filtered.traffic_type.eq("Paid")]
        candidates = aggregate(paid, "campaign").query("posts >= @minimum and spend_usd > 0").dropna(subset=["roas"])
        if candidates.empty:
            st.info("No paid campaign has sufficient posts and positive spend.")
        else:
            winner = candidates.sort_values("roas", ascending=False).iloc[0]
            st.markdown(f"**{winner.campaign}** has **{winner.roas:.2f}x ROAS**: \\${winner.revenue_usd:,.2f} attributed revenue / \\${winner.spend_usd:,.2f} spend across {int(winner.posts)} paid posts.")
    else:
        winner = filtered.sort_values("followers_gained", ascending=False).iloc[0]
        st.write(f"**{winner.post_id}** on **{winner.platform}** recorded **{int(winner.followers_gained):,} attributed new followers**.")
        st.text(f"Caption: {winner.caption}")
    st.caption(f"Answers use the current filters. Group comparisons require at least {minimum} posts. Ties show the first result in label or date order. This is a preset analysis workflow.")
    report = "Social Pulse report\n" + f"Source: {source_name}\nDates: {start} through {end}\nPlatforms: {', '.join(choices['platform'])}\nFormats: {', '.join(choices['content_type'])}\nCampaigns: {', '.join(choices['campaign'])}\nTraffic: {', '.join(choices['traffic_type'])}\nSearch: {search or '(none)'}\n\n" + "\n".join(summary_lines(filtered, minimum)) + "\n\nEngagement rate = actions / summed post reach. All money is USD.\nSummaries are computed, not generated by AI.\n"
    st.download_button("Download summary report", report, "social_pulse_report.txt", "text/plain")

with ai:
    render_ai_panel(filtered, {
        "dataset_id": fingerprint, "synthetic_sample": payload == sample_bytes,
        "start_date": str(start), "end_date": str(end),
        "platforms": choices["platform"], "content_types": choices["content_type"],
        "campaigns": choices["campaign"], "traffic_types": choices["traffic_type"],
        "search": search,
    })

with st.expander("Metric definitions and CSV guide"):
    st.markdown("""
**One row represents one post.** Count fields are cumulative observations for that post at export time.
Comparisons group posts by their publishing date, rather than measuring when the engagement occurred.

- **Impressions:** total displays of posts. **Reach:** distinct accounts reached per post. Summing post reach counts repeat viewers across posts; it is not a unique audience total.
- **Engagement actions:** likes + comments + shares + saves. **Engagement rate:** total actions / summed post reach × 100. One person can perform multiple actions.
- **CTR:** clicks / impressions × 100. **Conversion rate:** conversions / clicks × 100.
- **New followers attributed:** sum of followers_gained attributed to posts. This is not net follower growth or current account followers.
- **Paid CPC / CPA:** paid spend / paid clicks or paid conversions. **Paid ROAS:** paid attributed revenue / paid spend. Organic revenue is excluded from paid efficiency.
- **N/A:** the denominator is zero. Rates aggregate counts before division.

Custom files need every column shown below, nonnegative numbers, unique post IDs, and Paid or Organic traffic.
Use timezone-free timestamps in Pacific reporting time. Organic posts have zero advertising spend.
Files must be UTF-8 CSV, at most 10 MB and 50,000 rows. Extra columns are ignored.
""")
    st.code(", ".join(REQUIRED_COLUMNS), language=None)
st.caption("Built for Week 1 · Path 3 · Streamlit + pandas + Plotly")
