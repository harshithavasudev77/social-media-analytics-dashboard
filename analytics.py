"""CSV validation and shared calculations for Social Pulse."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, timedelta

import numpy as np
import pandas as pd

TEXT_COLUMNS = ["post_id", "published_at", "platform", "content_type", "campaign", "traffic_type", "caption"]
COUNT_COLUMNS = ["impressions", "reach", "likes", "comments", "shares", "saves", "clicks", "conversions", "followers_gained"]
MONEY_COLUMNS = ["spend_usd", "revenue_usd"]
REQUIRED_COLUMNS = TEXT_COLUMNS + COUNT_COLUMNS + MONEY_COLUMNS
ENGAGEMENT_COLUMNS = ["likes", "comments", "shares", "saves"]
SUM_COLUMNS = COUNT_COLUMNS + MONEY_COLUMNS + ["engagements"]
MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50_000
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class DataValidationError(ValueError):
    """An actionable message for an invalid input file."""


def _column_name(value: str) -> str:
    return re.sub(r"[\s-]+", "_", value.strip().lower())


def load_csv(payload: bytes) -> pd.DataFrame:
    """Reject invalid rows rather than silently dropping or filling them."""
    if len(payload) > MAX_BYTES:
        raise DataValidationError("The CSV exceeds 10 MB. Upload a smaller export.")
    try:
        text = payload.decode("utf-8-sig")
        header = next(csv.reader(io.StringIO(text)))
    except (UnicodeDecodeError, StopIteration, csv.Error) as exc:
        raise DataValidationError("Upload a nonempty, UTF-8, comma-separated CSV.") from exc
    columns = [_column_name(c) for c in header]
    if len(set(columns)) != len(columns):
        raise DataValidationError("Column names must be unique, including after removing spaces and changing case.")
    missing = sorted(set(REQUIRED_COLUMNS) - set(columns))
    if missing:
        raise DataValidationError("Missing columns: " + ", ".join(missing) + ". Use the sample CSV as a template.")
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, nrows=MAX_ROWS + 1)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise DataValidationError("The CSV could not be parsed. Check separators, quotes, and row lengths.") from exc
    df.columns = columns
    if df.empty:
        raise DataValidationError("The CSV has headers but no posts.")
    if len(df) > MAX_ROWS:
        raise DataValidationError("The CSV exceeds 50,000 posts. Upload a smaller export.")
    df = df[REQUIRED_COLUMNS].copy()
    for column in TEXT_COLUMNS:
        df[column] = df[column].str.strip()
        if df[column].isna().any() or df[column].eq("").any():
            raise DataValidationError(f"'{column}' contains blank values. Every post needs a value.")
    if df.post_id.duplicated().any():
        raise DataValidationError("Duplicate post_id values found. Use one row per post and unique IDs.")

    # Naive timestamps are explicitly local reporting time, never silently UTC.
    timestamps = []
    for value in df.published_at:
        try:
            stamp = pd.Timestamp(value)
            if pd.isna(stamp) or stamp.tzinfo is not None:
                raise ValueError
            timestamps.append(stamp)
        except (ValueError, TypeError, OverflowError) as exc:
            raise DataValidationError("Use valid timezone-free timestamps in published_at, e.g. 2026-09-30 14:30:00. All times represent America/Los_Angeles.") from exc
    try:
        df["published_at"] = pd.to_datetime(timestamps)
    except (ValueError, OverflowError) as exc:
        raise DataValidationError("published_at contains a date outside the supported range.") from exc
    for column in COUNT_COLUMNS + MONEY_COLUMNS:
        values = pd.to_numeric(df[column], errors="coerce")
        if values.isna().any() or not np.isfinite(values).all() or values.lt(0).any():
            raise DataValidationError(f"'{column}' must contain finite, nonnegative numbers with no blanks or currency symbols.")
        if column in COUNT_COLUMNS:
            if values.mod(1).ne(0).any() or values.gt(10**12).any():
                raise DataValidationError(f"'{column}' must contain whole-number counts from 0 to 1,000,000,000,000.")
            values = values.astype("int64")
        df[column] = values
    df["traffic_type"] = df.traffic_type.str.title()
    if not df.traffic_type.isin(["Paid", "Organic"]).all():
        raise DataValidationError("traffic_type must be Paid or Organic.")
    for numerator, denominator in [("reach", "impressions"), ("clicks", "impressions"), ("conversions", "clicks")]:
        if df[numerator].gt(df[denominator]).any():
            raise DataValidationError(f"'{numerator}' exceeds '{denominator}' in one or more posts. Check the export's definitions.")
    if df.loc[df.traffic_type.eq("Organic"), "spend_usd"].ne(0).any():
        raise DataValidationError("Organic posts must have spend_usd = 0. Classify boosted posts as Paid.")
    df["engagements"] = df[ENGAGEMENT_COLUMNS].sum(axis=1)
    # Engagements count actions, so they can exceed distinct post reach.
    df["engagement_rate_pct"] = safe_ratio(df.engagements, df.reach, 100)
    df["ctr_pct"] = safe_ratio(df.clicks, df.impressions, 100)
    df["conversion_rate_pct"] = safe_ratio(df.conversions, df.clicks, 100)
    df["date"] = df.published_at.dt.normalize()
    df["weekday"] = df.published_at.dt.day_name()
    df["hour"] = df.published_at.dt.hour
    return df.sort_values(["published_at", "post_id"]).reset_index(drop=True)


def safe_ratio(numerator, denominator, scale=1):
    """A zero denominator is undefined, not a zero rate."""
    if isinstance(denominator, pd.Series):
        return numerator.div(denominator.where(denominator.ne(0))) * scale
    return float(numerator) / float(denominator) * scale if denominator else float("nan")


def filter_posts(df: pd.DataFrame, start: date, end: date, platforms: list[str], content_types: list[str], campaigns: list[str], traffic_types: list[str], search: str = "") -> pd.DataFrame:
    mask = (
        df.date.between(pd.Timestamp(start), pd.Timestamp(end))
        & df.platform.isin(platforms)
        & df.content_type.isin(content_types)
        & df.campaign.isin(campaigns)
        & df.traffic_type.isin(traffic_types)
    )
    if search.strip():
        terms = df[["post_id", "caption", "campaign"]].agg(" ".join, axis=1)
        mask &= terms.str.contains(search.strip(), case=False, regex=False)
    return df.loc[mask].copy()


def previous_period(start: date, end: date) -> tuple[date, date]:
    days = (end - start).days + 1
    return start - timedelta(days=days), start - timedelta(days=1)


def metrics(df: pd.DataFrame) -> dict:
    totals = df[SUM_COLUMNS].sum()
    paid = df.loc[df.traffic_type.eq("Paid")]
    return {
        "posts": len(df),
        **totals.to_dict(),
        "engagement_rate_pct": safe_ratio(totals.engagements, totals.reach, 100),
        "ctr_pct": safe_ratio(totals.clicks, totals.impressions, 100),
        "conversion_rate_pct": safe_ratio(totals.conversions, totals.clicks, 100),
        "cpc_usd": safe_ratio(paid.spend_usd.sum(), paid.clicks.sum()),
        "cpa_usd": safe_ratio(paid.spend_usd.sum(), paid.conversions.sum()),
        "roas": safe_ratio(paid.revenue_usd.sum(), paid.spend_usd.sum()),
        "paid_revenue_usd": paid.revenue_usd.sum(),
    }


def aggregate(df: pd.DataFrame, by: str | list[str]) -> pd.DataFrame:
    """Rates use the ratio of summed counts, never an average of post rates."""
    result = df.groupby(by, observed=True, dropna=False)[SUM_COLUMNS].sum()
    result["posts"] = df.groupby(by, observed=True, dropna=False).size()
    result["engagement_rate_pct"] = safe_ratio(result.engagements, result.reach, 100)
    result["ctr_pct"] = safe_ratio(result.clicks, result.impressions, 100)
    result["conversion_rate_pct"] = safe_ratio(result.conversions, result.clicks, 100)
    result["cpc_usd"] = safe_ratio(result.spend_usd, result.clicks)
    result["cpa_usd"] = safe_ratio(result.spend_usd, result.conversions)
    result["roas"] = safe_ratio(result.revenue_usd, result.spend_usd)
    return result.reset_index()


def time_series(df: pd.DataFrame, start: date, end: date, frequency: str) -> pd.DataFrame:
    frequencies = {"Daily": "D", "Weekly": "W-MON", "Monthly": "MS"}
    daily = df.groupby("date")[SUM_COLUMNS].sum().reindex(pd.date_range(start, end, freq="D"), fill_value=0)
    daily.index.name = "date"
    if frequency != "Daily":
        daily = daily.resample(frequencies[frequency], closed="left", label="left").sum()
    daily["engagement_rate_pct"] = safe_ratio(daily.engagements, daily.reach, 100)
    daily["ctr_pct"] = safe_ratio(daily.clicks, daily.impressions, 100)
    return daily.reset_index()


def timing_data(df: pd.DataFrame, minimum_posts: int) -> pd.DataFrame:
    result = aggregate(df, ["weekday", "hour"])
    result.loc[result.posts.lt(minimum_posts), "engagement_rate_pct"] = np.nan
    return result


def summary_lines(df: pd.DataFrame, minimum_posts: int = 3) -> list[str]:
    if df.empty:
        return ["No posts match these filters."]
    m = metrics(df)
    lines = [f"{m['posts']:,} posts generated {int(m['impressions']):,} impressions and {int(m['engagements']):,} engagement actions."]
    platforms = aggregate(df, "platform").query("posts >= @minimum_posts").dropna(subset=["engagement_rate_pct"])
    if not platforms.empty:
        winner = platforms.sort_values("engagement_rate_pct", ascending=False).iloc[0]
        lines.append(f"{winner.platform} has the highest engagement rate among platforms with at least {minimum_posts} posts: {winner.engagement_rate_pct:.2f}% across {int(winner.posts)} posts.")
    top = df.sort_values("engagements", ascending=False).iloc[0]
    lines.append(f"{top.post_id} ({top.platform}, {top.content_type}) has the most engagement actions: {int(top.engagements):,}.")
    if m["spend_usd"] > 0:
        lines.append(f"Paid posts used ${m['spend_usd']:,.2f} in spend and recorded ${m['paid_revenue_usd']:,.2f} in attributed revenue, giving {m['roas']:.2f}x ROAS.")
    return lines


def csv_export(df: pd.DataFrame) -> bytes:
    """Keep exports safe to open in spreadsheet applications."""
    exported = df.copy()
    for column in exported.select_dtypes(include=["object", "string"]):
        exported[column] = exported[column].map(lambda v: "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v)
    return exported.to_csv(index=False).encode("utf-8")
