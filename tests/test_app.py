from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def select_by_label(app, label):
    return next(widget for widget in app.selectbox if widget.label == label)


def test_app_views_and_filters():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Overview", "Content performance", "Campaigns", "Analysis lab", "AI assistant"]
    select_by_label(app, "Date range").select("All data").run()
    assert not app.exception
    assert any("720 of 720 posts" in caption.value for caption in app.caption)
    platforms = next(widget for widget in app.multiselect if widget.label == "Platforms")
    platforms.set_value(["Instagram"]).run()
    assert not app.exception
    assert not any("720 of 720 posts" in caption.value for caption in app.caption)
    platforms.set_value([]).run()
    assert not app.exception
    assert any("No posts match" in message.value for message in app.info)
    next(button for button in app.button if button.label == "Reset filters").click().run()
    assert not app.exception
    assert len(next(widget for widget in app.multiselect if widget.label == "Platforms").value) == 5
    for question in select_by_label(app, "Choose an analysis question").options:
        select_by_label(app, "Choose an analysis question").select(question).run()
        assert not app.exception
    traffic = next(widget for widget in app.multiselect if widget.label == "Traffic type")
    traffic.set_value(["Organic"]).run()
    assert not app.exception
    assert any("No paid posts" in message.value for message in app.info)


def test_upload_pending_and_custom_date_states():
    app = AppTest.from_file(str(APP), default_timeout=30).run()
    select_by_label(app, "Date range").select("Custom").run()
    assert not app.exception
    next(widget for widget in app.date_input if widget.label == "Start and end").set_value((__import__("datetime").date(2026, 9, 30),)).run()
    assert not app.exception
    assert any("Choose both" in message.value for message in app.info)
    app.radio[0].set_value("Upload CSV").run()
    assert not app.exception
    assert any("Upload your CSV" in message.value for message in app.info)
