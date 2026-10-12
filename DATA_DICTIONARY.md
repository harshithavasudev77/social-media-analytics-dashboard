# CSV schema and metric definitions

The CSV is UTF-8, comma-separated, with one unique row per post. All 18 fields below are required; extra fields are ignored. Headers are normalized to lowercase, with spaces/hyphens replaced by underscores. Files may contain at most 50,000 rows and 10 MB. Missing values are rejected rather than changed to zero.

| Column | Type / unit | Meaning |
| --- | --- | --- |
| post_id | Nonempty text | Unique post identifier; duplicate IDs are rejected |
| published_at | Local timestamp | Timezone-free timestamp in America/Los_Angeles, such as `2026-09-30 14:30:00`; convert other timezones before upload |
| platform | Nonempty text | Social network name; custom network labels are supported |
| content_type | Nonempty text | Format such as Reel, Carousel, Image, Story, Video, Short video, or Text |
| campaign | Nonempty text | Campaign or content series; use a label such as Unassigned when needed |
| traffic_type | Paid / Organic | Paid includes advertising or boosting; case is normalized |
| caption | Nonempty text | Post caption, used in search and the post explorer |
| impressions | Whole-number count | Total displays of a post, including repeat displays |
| reach | Whole-number count | Distinct accounts reached by this post; must not exceed impressions |
| likes | Whole-number count | Like actions |
| comments | Whole-number count | Comment actions |
| shares | Whole-number count | Share actions |
| saves | Whole-number count | Save actions |
| clicks | Whole-number count | Clicks attributed to this post; must not exceed impressions in this schema |
| conversions | Whole-number count | Attributed conversion events; must not exceed clicks in this schema |
| followers_gained | Whole-number count | New followers attributed to this post, not the account's follower balance |
| spend_usd | Numeric USD | Advertising/boosting spend; Organic posts must have zero spend |
| revenue_usd | Numeric USD | Attributed revenue; may be nonzero for Organic posts |

All numeric values must be finite and nonnegative. Counts must be integers no larger than 10^12. Numeric CSV cells must not contain dollar signs or percentage signs. Quoted CSV fields can contain commas. Schema definitions need to match your source export; do not substitute view-through conversions or total link clicks without adapting the calculation and validation rules.

## Derived metrics

| Metric | Calculation |
| --- | --- |
| Engagement actions | likes + comments + shares + saves |
| Engagement rate (%) | sum(engagement actions) / sum(reach) × 100 |
| Click-through rate (%) | sum(clicks) / sum(impressions) × 100 |
| Conversion rate (%) | sum(conversions) / sum(clicks) × 100 |
| Attributed new followers | sum(followers_gained) |
| Paid CPC (USD) | sum(paid spend) / sum(paid clicks) |
| Paid CPA (USD) | sum(paid spend) / sum(paid conversions) |
| Paid ROAS (x) | sum(paid attributed revenue) / sum(paid spend) |
| Count delta (%) | (current / previous − 1) × 100, if previous > 0 |
| Engagement-rate delta (pp) | Current rate − previous rate, in percentage points |

Rates are ratios of sums, not arithmetic averages of post percentages. A zero denominator produces N/A. Multiple engagement actions can come from the same person; engagement rate may exceed 100% in an uploaded dataset.

**Reach is distinct per post.** Summing it across posts counts repeat viewers, so the app labels it “post reach (summed)” and does not claim a unique total audience. Attributed followers are not net growth: the dataset has no unfollows or account-level snapshots.

Metrics are grouped by publishing date, not the date on which views or interactions occurred. An older post may have had more time to accumulate metrics. Compare posts with comparable observation windows when using real data.

The preceding window has the same number of calendar days and ends the day before the selected range. For September 1–30, it is August 2–31. It uses the same category and search filters. Changes are hidden when the file's date coverage does not span the preceding window or no preceding posts match. Date coverage alone cannot establish that an export is complete. Daily trends fill dates with no posts with zero counts, while their rates remain undefined. Weekly buckets start Monday; first/last weekly or monthly buckets can be partial.

Heatmap slots use weighted engagement rates, and slots below the chosen minimum post count are blank. Time-of-post associations are hypotheses for experiments, not proof that a posting time causes higher engagement. Paid ROAS measures attributed revenue per advertising dollar and does not include product costs, labor, taxes, or other expenses.
