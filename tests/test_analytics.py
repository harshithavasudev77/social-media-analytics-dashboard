from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analytics import (
    DataValidationError, REQUIRED_COLUMNS, aggregate, csv_export, filter_posts,
    load_csv, metrics, previous_period, time_series, timing_data,
)

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "social_media_sample.csv"


@pytest.fixture
def posts():
    return load_csv(SAMPLE.read_bytes())


def encode(df):
    return df[REQUIRED_COLUMNS].to_csv(index=False).encode()


def test_sample_contract(posts):
    assert len(posts) == 720
    assert posts.post_id.is_unique
    assert posts.date.min().date() == date(2026, 7, 1)
    assert posts.date.max().date() == date(2026, 9, 30)
    assert posts.platform.nunique() == 5
    assert (posts["reach"] <= posts.impressions).all()
    assert (posts.conversions <= posts.clicks).all()
    assert posts.spend_usd.eq(0).equals(posts.traffic_type.eq("Organic"))


def test_weighted_rates_and_paid_denominators(posts):
    m = metrics(posts)
    assert m["engagement_rate_pct"] == pytest.approx(posts.engagements.sum() / posts.reach.sum() * 100)
    assert not np.isclose(m["engagement_rate_pct"], posts.engagement_rate_pct.mean())
    paid = posts[posts.traffic_type.eq("Paid")]
    assert m["cpc_usd"] == pytest.approx(paid.spend_usd.sum() / paid.clicks.sum())
    assert m["roas"] == pytest.approx(paid.revenue_usd.sum() / paid.spend_usd.sum())
    grouped = aggregate(posts, "platform")
    assert grouped.impressions.sum() == posts.impressions.sum()
    assert grouped.engagements.sum() == posts.engagements.sum()


def test_filter_includes_entire_end_day_and_literal_search(posts):
    result = filter_posts(posts, date(2026, 9, 30), date(2026, 9, 30), list(posts.platform.unique()), list(posts.content_type.unique()), list(posts.campaign.unique()), ["Paid", "Organic"])
    assert len(result) == posts.date.eq("2026-09-30").sum()
    assert result.published_at.dt.hour.max() > 0
    assert filter_posts(posts, date(2026, 7, 1), date(2026, 9, 30), [], list(posts.content_type.unique()), list(posts.campaign.unique()), ["Paid", "Organic"]).empty
    result = filter_posts(posts, date(2026, 7, 1), date(2026, 9, 30), list(posts.platform.unique()), list(posts.content_type.unique()), list(posts.campaign.unique()), ["Paid", "Organic"], ".*")
    assert result.empty  # Search is literal, not a user-provided regex.


def test_period_and_time_series_reconciliation(posts):
    assert previous_period(date(2026, 9, 1), date(2026, 9, 30)) == (date(2026, 8, 2), date(2026, 8, 31))
    for frequency in ["Daily", "Weekly", "Monthly"]:
        series = time_series(posts, date(2026, 7, 1), date(2026, 9, 30), frequency)
        assert series.impressions.sum() == posts.impressions.sum()
        assert series.engagements.sum() == posts.engagements.sum()
    single = posts.head(1)
    daily = time_series(single, date(2026, 7, 1), date(2026, 7, 3), "Daily")
    assert len(daily) == 3
    assert daily.loc[daily.impressions.eq(0), "engagement_rate_pct"].isna().all()


def test_zero_denominators_and_sparse_timing(posts):
    raw = posts.head(1).copy()
    raw.loc[:, ["impressions", "reach", "likes", "comments", "shares", "saves", "clicks", "conversions", "followers_gained", "spend_usd", "revenue_usd"]] = 0
    empty_metrics = metrics(load_csv(encode(raw)))
    assert np.isnan(empty_metrics["engagement_rate_pct"])
    assert np.isnan(empty_metrics["roas"])
    slots = timing_data(posts, 10)
    assert slots.loc[slots.posts.lt(10), "engagement_rate_pct"].isna().all()
    assert timing_data(posts.head(1), 3).engagement_rate_pct.isna().all()


@pytest.mark.parametrize("column,value", [("impressions", -1), ("likes", 1.5), ("reach", "broken"), ("revenue_usd", "inf"), ("clicks", ""), ("published_at", "not-a-date"), ("published_at", "2026-09-01T10:00:00Z"), ("traffic_type", "Boosted"), ("caption", " ")])
def test_invalid_values_are_rejected(posts, column, value):
    raw = posts.head(1)[REQUIRED_COLUMNS].astype(object).copy()
    raw.loc[0, column] = value
    with pytest.raises(DataValidationError):
        load_csv(encode(raw))


def test_duplicate_ids_and_columns_are_rejected(posts):
    with pytest.raises(DataValidationError, match="Duplicate post_id"):
        load_csv(encode(pd.concat([posts.head(1), posts.head(1)])))
    payload = SAMPLE.read_text().replace("post_id,", "post_id,POST ID,", 1).encode()
    with pytest.raises(DataValidationError, match="Column names must be unique"):
        load_csv(payload)


def test_missing_empty_and_organic_spend_are_rejected(posts):
    with pytest.raises(DataValidationError, match="Missing columns"):
        load_csv(b"post_id,platform\nP1,Instagram\n")
    with pytest.raises(DataValidationError, match="no posts"):
        load_csv((",".join(REQUIRED_COLUMNS) + "\n").encode())
    raw = posts.head(1).copy()
    raw.loc[0, "traffic_type"] = "Organic"
    raw.loc[0, "spend_usd"] = 1
    with pytest.raises(DataValidationError, match="Organic posts"):
        load_csv(encode(raw))


def test_export_round_trip_and_formula_escaping(posts):
    payload = csv_export(posts[REQUIRED_COLUMNS])
    assert len(load_csv(payload)) == len(posts)
    assert load_csv(payload).impressions.sum() == posts.impressions.sum()
    dangerous = pd.DataFrame({"caption": ["=HYPERLINK(\"bad\")", " +SUM(A1:A2)", "ordinary text"]})
    safe = pd.read_csv(__import__("io").BytesIO(csv_export(dangerous)))
    assert safe.caption.iloc[0].startswith("'=")
    assert safe.caption.iloc[1].startswith("' +")
    assert safe.caption.iloc[2] == "ordinary text"
