# Social Pulse

A Streamlit social media analytics dashboard for **Week 1, Path 3: Build your own app with vibe-coding**. Load a CSV, compare content and platforms, examine paid campaigns, and explore publishing-time hypotheses.

## Run the app

Use Python 3.10 or later. From a terminal:

```bash
cd /Users/arun/Documents/Mastering_Agentic_AI/Week_1/social_media_dashboard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the local URL printed in the terminal (usually http://localhost:8501). The included sample loads automatically. Charts and local analysis work without credentials; the AI assistant requires an OpenAI API key.

On this workstation, Streamlit is already installed in Anaconda. You can also run:

```bash
cd /Users/arun/Documents/Mastering_Agentic_AI/Week_1/social_media_dashboard
/opt/anaconda3/bin/python3 -m streamlit run app.py --server.fileWatcherType none
```

The second command avoids macOS file-watcher restrictions. Refresh the browser after editing code when file watching is disabled.

## What to explore

| View | Questions and tools |
| --- | --- |
| Overview | Five headline metrics, preceding-period comparisons, daily/weekly/monthly trends, platform comparisons, computed summaries |
| Content performance | Format engagement rates, reach-versus-engagement bubbles, searchable and sortable post table |
| Campaigns | Campaign totals, paid spend and revenue, paid CPC/CPA/ROAS, conversion efficiency |
| Analysis lab | Weekday/hour heatmap, minimum sample size, four preset analysis questions, downloadable summary |
| AI assistant | AI-generated summary, natural-language questions and follow-ups, supporting calculation tables, downloadable answers |

All views share date, platform, content format, campaign, traffic, and literal keyword filters. The default shows the last 30 days relative to the file's latest date. **All data** shows the complete dataset. A cleared multiselect means no matching posts; **Reset filters** restores the defaults. CSV export always includes every matching post, even when the post table shows only the top 25.

Choose **Upload CSV** to use your own export. Validation errors appear in the sidebar with instructions. The CSV is processed locally. Only submitted AI requests send context and selected calculation results to OpenAI; the full file is not uploaded.

## Sample dataset

`data/social_media_sample.csv` contains **720 fictional posts and 18 source columns**, dated **July 1–September 30, 2026**. Platforms: Instagram, TikTok, LinkedIn, Facebook, YouTube. It includes five campaigns, seven content formats, and 233 paid / 487 organic posts.

Each row is one post. Counts represent cumulative post metrics at a fictional export time. Platform differences, format effects, publishing-time effects, and attributed revenue are generated assumptions for learning. They are not real platform benchmarks or evidence of causation. The generator uses random seed 42 and needs only the Python standard library.

```bash
python generate_sample_data.py
# Optional: generate another sample with the same schema.
python generate_sample_data.py --posts 1000 --seed 7 --output data/another_sample.csv
```

See [the data dictionary](DATA_DICTIONARY.md) for every field and calculation.

### Alternative outdoor retailer dataset

`data/social_media_outdoor_sample.csv` contains **1,080 fictional posts** for **Cedar & Summit**, an outdoor retailer, dated **January 1–June 30, 2026**. It uses the same 18 columns, with new post IDs, captions, six campaigns, and generated performance values. Platforms are Pinterest, Reddit, Instagram, YouTube, and TikTok. The scenario includes seasonal product launches, repair education, community cleanups, and camping bundles. Conversions represent attributed purchases. All data is synthetic.

Select **Upload CSV** and choose this file, then select **All data** to explore all six months. Useful AI questions include “Which paid campaign has the lowest ROAS?”, “How do Pinterest and Reddit compare?”, and “Which content formats get the most saves per post?” The original generator above produces the original scenario; this alternative uses different generation assumptions.

Reconciliation values for the **original sample dataset**, with **All data** and every filter selected:

| Metric | Expected value |
| --- | ---: |
| Posts | 720 |
| Impressions | 16,634,393 |
| Engagement actions | 746,268 |
| Summed post reach | 12,191,258 |
| Engagement rate | 6.121337% |
| Clicks | 299,189 |
| Paid spend (USD) | 53,550.38 |
| Paid attributed revenue (USD) | 283,997.39 |
| Paid ROAS | 5.303368x |

## Development and validation

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover CSV validation, weighted rates, paid-only efficiency denominators, date inclusivity, literal search, preceding-period boundaries, missing-day handling, sparse heatmap slots, zero denominators, safe CSV exports, all dashboard tabs, filter resets, empty results, and analysis questions. Tests use Streamlit's [AppTest API](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest); charts use [Streamlit's Plotly integration](https://docs.streamlit.io/develop/api-reference/charts/st.plotly_chart) and [Plotly heatmaps](https://plotly.com/python/heatmaps/).

## Enable AI summaries and natural-language questions

Open the **AI assistant** tab. Expand **AI connection settings** and enter your OpenAI API key in the masked field. This key stays in the current Streamlit session. Alternatively, configure a server-side key:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml` locally and replace the placeholder key. This file is ignored by Git. The app also accepts `OPENAI_API_KEY` and `OPENAI_MODEL` environment variables; environment settings take precedence over the secrets file, and an entered session key takes precedence over a server-side key. Never put an actual key in project documentation or source code. No additional Python packages are needed for AI: the app calls the HTTPS Responses endpoint with the standard library.

The default model is `gpt-4.1-mini`, which supports the [Responses API and function calling](https://developers.openai.com/api/docs/models/gpt-4.1-mini). You can change the model ID in the AI tab to another model your API project can access.

Click **Generate AI summary** for an overview with numerical evidence and suggested experiments. Type a question and click **Ask AI**, then ask follow-up questions. Examples:

- “Compare Instagram and TikTok engagement rates.”
- “Which content format earned the most saves per post?”
- “Rank the top five posts by attributed new followers.”
- “Which paid campaign has the best ROAS?”
- “Compare engagement rates for September 1–15 and September 16–30.” (Choose All data or a date range that includes both periods.)

Every answer uses the current dashboard filters. Questions can narrow those filters but cannot retrieve excluded posts; change the sidebar to ask about a different scope. Answers are cleared when the dataset, filters, model, or caption setting changes. Up to six recent messages are sent for follow-up context; up to six question/answer pairs remain visible in the session. Use **Clear AI history** to reset them. Summary and conversation downloads record the model and filter scope.

**What gets shared:** questions, recent conversation, aggregate metrics, category labels, and selected post IDs/metrics. Captions are excluded by default; enabling the caption option allows up to 280 characters of each returned caption to be sent. An initial-context preview is shown in the tab. Numerical analysis uses the full filtered DataFrame locally, with evidence tables limited to 30 displayed rows and explicit truncation metadata.

The integration uses [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling) with a validated read-only analysis tool. Model-generated Python and SQL are not executed. Rates retain their weighted denominators, and paid cost/ROAS calculations restrict to paid posts. API response storage is disabled with `store=false`. Requests happen only when you click a summary or question submit button; API usage is charged to your API account. Authentication, model-access, quota, timeout, and incomplete-response errors are displayed without exposing keys or raw API error bodies. The local analysis views remain available when AI is unconfigured or unavailable.

AI interpretations can still contain mistakes; review **View supporting calculations** beneath each answer. The tool supports totals, category/date/time-slot comparisons, additional date/category/search filters, top/bottom posts, and common per-post averages. It does not infer missing sentiment, demographics, follower balances, or causal effects.

AI transport and UI tests use mock responses; a live model response must be checked using your configured API key.

## Week 1 submission preparation

Use [PROJECT_NOTES.md](PROJECT_NOTES.md) as a starting point for your Google Doc, and [DEMO_GUIDE.md](DEMO_GUIDE.md) for a walkthrough under five minutes. The handout also asks for screenshots of the development workflow, a working screen recording, and a GitHub code link. Capture your actual follow-up prompting and edits, add those screenshots to your document, record the demo, and publish the code to your chosen GitHub repository before submitting.

The reference is the original [Week 1 Project Handout](../Week%201%20Project%20Handout.pdf), especially pages 2–5. This project does not use the separate solution kits.
