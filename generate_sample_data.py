"""Create reproducible fictional post-level metrics; no accounts or APIs needed."""

import argparse
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

FIELDS = ["post_id", "published_at", "platform", "content_type", "campaign", "traffic_type", "caption", "impressions", "reach", "likes", "comments", "shares", "saves", "clicks", "conversions", "followers_gained", "spend_usd", "revenue_usd"]
PLATFORMS = {
    "Instagram": (15000, 0.052, ["Reel", "Carousel", "Image", "Story"]),
    "TikTok": (24000, 0.068, ["Short video"]),
    "LinkedIn": (7500, 0.034, ["Carousel", "Image", "Video", "Text"]),
    "Facebook": (11500, 0.027, ["Image", "Video", "Text"]),
    "YouTube": (18000, 0.040, ["Video", "Short video"]),
}
CAMPAIGNS = ["Summer launch", "Creator stories", "Product education", "Community spotlight", "September offer"]
CAPTIONS = ["A closer look at what we are building.", "Three tips to get more from your day.", "Meet the people behind the product.", "Your questions, answered by our team.", "Watch this quick product walkthrough.", "Share your favorite moment with us."]


def generate_rows(posts=720, seed=42):
    rng = random.Random(seed)
    rows = []
    for index in range(posts):
        stamp = datetime(2026, 7, 1) + timedelta(days=rng.randrange(92), hours=rng.choice([8, 9, 10, 12, 14, 16, 18, 19, 20]), minutes=rng.randrange(60))
        platform = rng.choice(list(PLATFORMS))
        base, engagement_base, formats = PLATFORMS[platform]
        content = rng.choice(formats)
        campaign = rng.choice(CAMPAIGNS[:-1] if stamp.month < 9 else CAMPAIGNS[1:])
        paid = rng.random() < 0.32
        spend = round(rng.uniform(50, 420), 2) if paid else 0.0
        growth = 1 + (stamp - datetime(2026, 7, 1)).days * 0.002
        impressions = int(base * rng.lognormvariate(0, 0.52) * growth + spend * rng.uniform(35, 65))
        reach = int(impressions * rng.uniform(0.58, 0.90))
        format_lift = 1.22 if content in ["Reel", "Short video", "Carousel"] else 1
        time_lift = 1.15 if stamp.hour in [12, 18, 19] else 1
        education_lift = 1.12 if campaign == "Product education" else 1
        engagements = int(reach * engagement_base * format_lift * time_lift * education_lift * rng.uniform(0.6, 1.5))
        likes = int(engagements * rng.uniform(0.64, 0.75))
        comments = int(engagements * rng.uniform(0.07, 0.12))
        shares = int(engagements * rng.uniform(0.08, 0.14))
        saves = engagements - likes - comments - shares
        click_rate = rng.uniform(0.005, 0.025) * (1.5 if platform == "LinkedIn" else 1) * (1.3 if paid else 1)
        clicks = int(impressions * click_rate)
        conversions = int(clicks * rng.uniform(0.015, 0.07) * (1.4 if campaign == "September offer" else 1))
        rows.append(dict(zip(FIELDS, [f"POST-{index+1:04d}", stamp.strftime("%Y-%m-%d %H:%M:%S"), platform, content, campaign, "Paid" if paid else "Organic", f"{CAPTIONS[index % len(CAPTIONS)]} #{campaign.replace(' ', '')}", impressions, reach, likes, comments, shares, saves, clicks, conversions, int(reach * rng.uniform(0.0005, 0.003)), spend, round(conversions * rng.uniform(18, 65), 2)])))
    return sorted(rows, key=lambda row: (row["published_at"], row["post_id"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--posts", type=int, default=720)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "data" / "social_media_sample.csv")
    parser.add_argument("--json", action="store_true", help="Write a JSON intermediate instead of CSV.")
    args = parser.parse_args()
    if not 1 <= args.posts <= 50_000:
        parser.error("--posts must be between 1 and 50,000")
    rows = generate_rows(args.posts, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.json:
        args.output.write_text(json.dumps({"columns": FIELDS, "rows": [[row[c] for c in FIELDS] for row in rows]}), encoding="utf-8")
    else:
        with args.output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    print(f"Generated {len(rows)} synthetic posts: {args.output}")
