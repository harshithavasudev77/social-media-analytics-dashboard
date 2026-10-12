"""Streamlit controls for AI summaries and questions; no calls on ordinary reruns."""

import hashlib
import json
import os
import re

import pandas as pd
import streamlit as st

from ai_assistant import AIError, DEFAULT_MODEL, ask_ai, context_for

SUMMARY_QUESTION = "Summarize the current filtered social media performance. Compare platforms and formats, identify a leading paid campaign if available, and suggest two content experiments. Cite exact metrics, include sample sizes, and state the important limitations. Use concise bullets."


def server_setting(name, fallback=""):
    if os.environ.get(name):
        return os.environ[name]
    try:
        return str(st.secrets.get(name, fallback))
    except (FileNotFoundError, KeyError):
        return fallback


def markdown_answer(answer):
    return re.sub(r"(?<!\\)\$", r"\\$", answer)


def render_evidence(evidence, prefix):
    with st.expander("View supporting calculations"):
        for index, item in enumerate(evidence, 1):
            result = item["result"]
            if "error" in result:
                st.caption(f"Analysis {index}: {result['error']}")
                continue
            st.caption(f"Analysis {index}: {result['matched_posts']:,} matching posts" + (" · Paid posts only" if result["paid_only"] else ""))
            st.json(result["query"], expanded=False)
            if result["rows"]:
                evidence_df = pd.DataFrame(result["rows"])
                st.dataframe(evidence_df, hide_index=True, use_container_width=True, key=f"{prefix}_evidence_{index}")
                if result["truncated"]:
                    st.caption(f"Showing {result['rows_shown']} of {result['eligible_rows']} eligible rows after calculating all matching posts.")
            else:
                st.json(result["totals"], expanded=False)


def render_ai_panel(df, scope):
    st.subheader("AI assistant")
    st.caption(f"Summarize or ask questions about the {len(df):,} posts in your current dashboard filters. For other dates or platforms, update the sidebar first.")
    with st.expander("AI connection settings", expanded=not bool(server_setting("OPENAI_API_KEY") or st.session_state.get("ai_api_key"))):
        st.text_input("OpenAI API key", type="password", key="ai_api_key", placeholder="Enter a key for this browser session", help="Stored only in this Streamlit session. You may instead configure OPENAI_API_KEY in the environment or .streamlit/secrets.toml.")
        model = st.text_input("OpenAI model", value=server_setting("OPENAI_MODEL", DEFAULT_MODEL), key="ai_model")
        include_captions = st.checkbox("Include post captions in AI results", key="ai_include_captions", help="Off by default. When enabled, at most 280 characters per returned caption are shared with OpenAI.")
        st.caption("AI requests send your questions, recent chat, aggregate metrics, category labels, and selected post IDs/metrics to OpenAI. Caption text is included only when enabled. API usage uses your OpenAI account.")
        if server_setting("OPENAI_API_KEY"):
            st.caption("A server-side API key is configured. The session key takes precedence when entered.")
    api_key = st.session_state.get("ai_api_key", "").strip() or server_setting("OPENAI_API_KEY")
    ready = bool(api_key and model.strip())
    # Keep one scope in memory: filter, dataset, model, and caption changes invalidate answers.
    signature = hashlib.sha256((json.dumps(scope, sort_keys=True) + model + str(include_captions)).encode()).hexdigest()
    if st.session_state.get("ai_scope") != signature:
        st.session_state["ai_scope"] = signature
        st.session_state["ai_summary"] = None
        st.session_state["ai_messages"] = []
    messages = st.session_state["ai_messages"]
    if not ready:
        st.info("Add an OpenAI API key above to enable AI summaries and natural-language questions. The other dashboard views continue to work without it.")
    with st.expander("Preview the initial data shared with AI"):
        st.json(context_for(df, scope, include_captions), expanded=False)
        st.caption("Additional calculation results are sent if needed to answer your question; you can review those beneath each answer. The full CSV is not uploaded.")

    summary_col, clear_col = st.columns([2, 1])
    generate = summary_col.button("Generate AI summary", disabled=not ready, use_container_width=True)
    if clear_col.button("Clear AI history", use_container_width=True):
        st.session_state["ai_messages"] = []
        st.session_state["ai_summary"] = None
        st.rerun()
    if generate:
        with st.spinner("Analyzing the filtered data and writing a summary..."):
            try:
                st.session_state["ai_summary"] = ask_ai(df, SUMMARY_QUESTION, api_key, model.strip(), scope, include_captions=include_captions)
            except AIError as exc:
                st.error(str(exc))
    summary = st.session_state["ai_summary"]
    if summary:
        st.markdown(markdown_answer(summary["answer"]))
        render_evidence(summary["evidence"], "summary")
        st.download_button("Download AI summary", f"AI-generated summary\nModel: {summary['model']}\nFilters: {json.dumps(scope)}\n\n{summary['answer']}", "social_pulse_ai_summary.txt", "text/plain")
    st.divider()
    st.markdown("#### Ask a question")
    st.caption('Try “Compare engagement rates for Instagram and TikTok” or “Which paid campaign has the best ROAS?” Follow up with “Show its top five posts.”')
    for index, message in enumerate(messages):
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.text(message["content"])
            else:
                st.markdown(markdown_answer(message["content"]))
                render_evidence(message["evidence"], f"chat_{index}")
    new_reply = st.container()
    with st.form("ai_question_form", clear_on_submit=True):
        question = st.text_input("Your question about the CSV", max_chars=2000, placeholder="Which formats earned the most saves per post?", disabled=not ready)
        submit = st.form_submit_button("Ask AI", disabled=not ready)
    if submit:
        history = [{"role": message["role"], "content": message["content"]} for message in messages]
        with st.spinner("Calculating an answer..."):
            try:
                result = ask_ai(df, question, api_key, model.strip(), scope, history, include_captions)
            except AIError as exc:
                st.error(str(exc))
            else:
                messages.extend([{"role": "user", "content": question}, {"role": "assistant", "content": result["answer"], "evidence": result["evidence"]}])
                st.session_state["ai_messages"] = messages[-12:]
                with new_reply:
                    with st.chat_message("user"):
                        st.text(question)
                    with st.chat_message("assistant"):
                        st.markdown(markdown_answer(result["answer"]))
                        render_evidence(result["evidence"], f"chat_{len(messages) - 1}")
    if messages:
        transcript = "AI conversation\nModel: " + model + "\nFilters: " + json.dumps(scope) + "\n\n" + "\n\n".join(f"{message['role'].title()}: {message['content']}" for message in messages)
        st.download_button("Download AI conversation", transcript, "social_pulse_ai_conversation.txt", "text/plain")
    st.caption("AI interpretations can make mistakes. Review the supporting calculations. Changes to the dataset, filters, model, or caption setting clear AI history.")
