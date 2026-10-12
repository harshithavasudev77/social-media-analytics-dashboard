import copy
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import ai_assistant
import ai_ui
from ai_assistant import AIError, ANALYSIS_TOOL, analyze_posts, ask_ai, context_for, request_response
from analytics import load_csv

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def posts():
    return load_csv((ROOT / "data/social_media_sample.csv").read_bytes())


def query(**overrides):
    args = {"view": "groups", "group_by": ["platform"], "metric": "engagement_rate_pct", "direction": "highest", "limit": 30, "minimum_posts": 1, "platforms": [], "content_types": [], "campaigns": [], "traffic_types": [], "start_date": None, "end_date": None, "search": None}
    args.update(overrides)
    return args


def tool_response(args, name="analyze_posts"):
    return {"status": "completed", "output": [{"type": "function_call", "name": name, "arguments": json.dumps(args), "call_id": "call-1"}]}


def answer_response(text="TikTok has the highest engagement rate in this sample."):
    return {"status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}]}


def test_full_dataset_weighted_groups_and_minimum(posts):
    result = analyze_posts(posts, query(limit=2))
    assert result["matched_posts"] == 720
    assert result["eligible_rows"] == 5
    assert result["rows_shown"] == 2
    assert result["truncated"]
    assert result["totals"]["impressions"] == 16_634_393
    assert result["totals"]["saves_per_post"] == pytest.approx(76_965 / 720, abs=1e-6)
    winner = result["rows"][0]
    source = posts[posts.platform.eq(winner["platform"])]
    assert winner["engagement_rate_pct"] == pytest.approx(source.engagements.sum() / source.reach.sum() * 100, abs=1e-6)
    assert analyze_posts(posts, query(minimum_posts=500))["rows"] == []


def test_paid_efficiency_excludes_organic(posts):
    result = analyze_posts(posts, query(group_by=["campaign"], metric="roas"))
    assert result["paid_only"]
    assert result["matched_posts"] == 233
    for row in result["rows"]:
        paid = posts[posts.campaign.eq(row["campaign"]) & posts.traffic_type.eq("Paid")]
        assert row["roas"] == pytest.approx(paid.revenue_usd.sum() / paid.spend_usd.sum(), abs=1e-6)
    assert analyze_posts(posts, query(metric="roas", traffic_types=["Organic"]))["matched_posts"] == 0


def test_extra_filters_can_only_narrow_and_dates_are_inclusive(posts):
    scope = posts[posts.date.between("2026-09-01", "2026-09-30")]
    result = analyze_posts(scope, query(view="totals", group_by=[], start_date="2026-07-01"))
    assert result["matched_posts"] == 225  # Earlier dates do not widen the active dashboard scope.
    result = analyze_posts(posts, query(view="totals", group_by=[], start_date="2026-09-30", end_date="2026-09-30", platforms=["instagram"]))
    expected = posts[posts.date.eq("2026-09-30") & posts.platform.eq("Instagram")]
    assert result["matched_posts"] == len(expected)
    assert result["totals"]["impressions"] == expected.impressions.sum()
    assert analyze_posts(posts, query(search=".*"))["matched_posts"] == 0


def test_post_ranking_caption_opt_in_and_per_post_metrics(posts):
    args = query(view="posts", group_by=[], metric="followers_gained", limit=5)
    result = analyze_posts(posts, args)
    assert result["rows"][0]["followers_gained"] == posts.followers_gained.max()
    assert all("caption" not in row for row in result["rows"])
    included = analyze_posts(posts, args, include_captions=True)
    assert all(0 < len(row["caption"]) <= 280 for row in included["rows"])
    result = analyze_posts(posts, query(group_by=["content_type"], metric="saves_per_post"))
    assert result["rows"][0]["saves_per_post"] == pytest.approx(result["rows"][0]["saves"] / result["rows"][0]["posts"], abs=1e-6)


@pytest.mark.parametrize("overrides", [{"metric": "__import__('os')"}, {"group_by": ["caption"]}, {"limit": 999999}, {"limit": True}, {"start_date": "2026-99-99"}, {"start_date": "2026-09-30", "end_date": "2026-09-01"}, {"group_by": []}, {"group_by": ["platform", "platform"]}, {"view": "execute_code"}])
def test_invalid_tool_parameters_are_rejected(posts, overrides):
    with pytest.raises(AIError):
        analyze_posts(posts, query(**overrides))


def test_json_context_undefined_rates_and_caption_exclusion(posts):
    raw = posts.head(1).copy()
    for column in ["impressions", "reach", "engagements", "clicks", "conversions", "spend_usd", "revenue_usd"]:
        raw[column] = 0
    context = context_for(raw, {"synthetic_sample": True})
    assert context["totals"]["roas"] is None
    assert context["totals"]["engagement_rate_pct"] is None
    assert "caption" not in context["categories"]
    json.dumps(context, allow_nan=False)


def test_responses_loop_uses_local_tool_evidence_and_recent_history(posts):
    requests = []
    responses = [tool_response(query()), answer_response()]
    def transport(key, body):
        assert key == "test-key"
        requests.append(copy.deepcopy(body))
        return responses.pop(0)
    history = [{"role": "user", "content": "Compare the platforms."}, {"role": "assistant", "content": "Here is the comparison."}]
    result = ask_ai(posts, "Which one is best?", "test-key", history=history, transport=transport)
    assert result["evidence"][0]["result"]["matched_posts"] == 720
    assert requests[0]["tool_choice"] == "required"
    assert all(body["store"] is False for body in requests)
    assert all("test-key" not in json.dumps(body) for body in requests)
    assert {"role": "user", "content": "Compare the platforms."} in requests[0]["input"]
    output = next(item for item in requests[1]["input"] if item.get("type") == "function_call_output")
    assert json.loads(output["output"])["totals"]["impressions"] == 16_634_393
    assert ANALYSIS_TOOL["parameters"]["additionalProperties"] is False


def test_tool_errors_can_be_corrected_but_unsupported_answers_are_rejected(posts):
    responses = [tool_response(query(), "execute_code"), tool_response(query()), answer_response()]
    result = ask_ai(posts, "Compare platforms", "test-key", transport=lambda *_: responses.pop(0))
    assert "error" in result["evidence"][0]["result"]
    assert "error" not in result["evidence"][1]["result"]
    with pytest.raises(AIError, match="supported by a calculation"):
        ask_ai(posts, "Compare platforms", "test-key", transport=lambda *_: answer_response("I guessed the answer."))
    with pytest.raises(AIError, match="did not finish"):
        ask_ai(posts, "Compare platforms", "test-key", transport=lambda *_: {"status": "incomplete", "output": []})


def test_loop_is_bounded_and_missing_keys_do_not_call_network(posts):
    calls = []
    def repeats(*args):
        calls.append(1)
        return tool_response(query())
    with pytest.raises(AIError, match="too many analysis steps"):
        ask_ai(posts, "Keep analyzing", "test-key", transport=repeats)
    assert len(calls) == 4
    with pytest.raises(AIError, match="API key"):
        ask_ai(posts, "Compare platforms", "", transport=lambda *_: pytest.fail("Must not call API"))


@pytest.mark.parametrize("status,match", [(401, "rejected the API key"), (429, "quota limit"), (500, "temporarily unavailable")])
def test_http_errors_do_not_expose_secrets(monkeypatch, status, match):
    def failed(*args, **kwargs):
        raise HTTPError("https://api.openai.com/v1/responses", status, "test-key secret details", {}, None)
    monkeypatch.setattr(ai_assistant, "urlopen", failed)
    with pytest.raises(AIError, match=match) as error:
        request_response("test-key", {})
    assert "test-key" not in str(error.value)


def test_network_failure_is_actionable(monkeypatch):
    def failed(*args, **kwargs):
        raise URLError("connection failed with test-key")
    monkeypatch.setattr(ai_assistant, "urlopen", failed)
    with pytest.raises(AIError, match="network"):
        request_response("test-key", {})


def widget(elements, label):
    return next(item for item in elements if item.label == label)


def test_ai_ui_disabled_without_key(monkeypatch):
    monkeypatch.setattr(ai_ui, "server_setting", lambda name, fallback="": fallback)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert widget(app.button, "Generate AI summary").disabled
    assert widget(app.button, "Ask AI").disabled
    assert any("Add an OpenAI API key" in message.value for message in app.info)


def test_ai_ui_summary_follow_up_filter_reset_and_error(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_ui, "server_setting", lambda name, fallback="": fallback)
    def fake_ai(df, question, key, model, scope, history=None, include_captions=False):
        calls.append({"rows": len(df), "question": question, "history": history or []})
        if question == "Fail please":
            raise AIError("Test API error. Retry later.")
        return {"answer": "Test answer with $100 and \\$50.", "model": model, "evidence": [{"result": analyze_posts(df, query(limit=2))}]}
    monkeypatch.setattr(ai_ui, "ask_ai", fake_ai)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    widget(app.text_input, "OpenAI API key").set_value("test-key").run()
    assert not calls  # Entering a key does not incur an API request.
    widget(app.button, "Generate AI summary").click().run()
    assert not app.exception
    assert len(calls) == 1
    assert app.session_state["ai_summary"] is not None
    for index, question in enumerate(["Compare platforms", "Show its top five posts"]):
        widget(app.text_input, "Your question about the CSV").set_value(question)
        widget(app.button, "Ask AI").click().run()
        assert not app.exception
        assert len(app.session_state["ai_messages"]) == 2 * (index + 1), {"calls": calls, "errors": [e.value for e in app.error], "text_inputs": [(v.label, v.value) for v in app.text_input]}
    assert len(app.session_state["ai_messages"]) == 4
    assert len(calls[-1]["history"]) == 2
    widget(app.selectbox, "Date range").select("All data").run()
    assert not app.exception
    assert app.session_state["ai_messages"] == []
    assert app.session_state["ai_summary"] is None
    assert len(calls) == 3  # Filter changes never automatically call OpenAI.
    widget(app.text_input, "Your question about the CSV").set_value("Fail please")
    widget(app.button, "Ask AI").click().run()
    assert not app.exception
    assert any("Test API error" in error.value for error in app.error)


def test_currency_escape_is_idempotent():
    text = "Revenue $100 and \\$50."
    assert ai_ui.markdown_answer(text) == "Revenue \\$100 and \\$50."
    assert ai_ui.markdown_answer(ai_ui.markdown_answer(text)) == ai_ui.markdown_answer(text)
