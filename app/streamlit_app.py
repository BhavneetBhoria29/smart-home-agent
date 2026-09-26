"""Minimal Streamlit chat UI over the ADK agent.

The brief allows adk web or Streamlit; we ship both. adk web is best for inspecting
tool traces; this is a clean product-style chat.

How a UI talks to an ADK agent: the agent (logic) is separate from the Runner
(execution) and the SessionService (conversation state). We create one session per
browser session, send each turn as a genai Content, and read back the final response
event. Session state gives multi-turn memory (e.g. remembering the user's ecosystem).

Run:  streamlit run app/streamlit_app.py
"""
import asyncio

import streamlit as st
from google.adk.runners import InMemoryRunner
from google.genai import types

from smart_home_agent.agent import root_agent

APP_NAME = "smart_home_ui"
USER_ID = "web-user"


@st.cache_resource
def get_runner() -> InMemoryRunner:
    return InMemoryRunner(agent=root_agent, app_name=APP_NAME)


def ensure_session(runner: InMemoryRunner) -> str:
    if "session_id" not in st.session_state:
        sess = asyncio.run(
            runner.session_service.create_session(app_name=APP_NAME, user_id=USER_ID)
        )
        st.session_state.session_id = sess.id
        st.session_state.history = []
    return st.session_state.session_id


def ask(runner: InMemoryRunner, session_id: str, message: str) -> str:
    content = types.Content(role="user", parts=[types.Part(text=message)])
    reply = ""
    for event in runner.run(user_id=USER_ID, session_id=session_id, new_message=content):
        if event.is_final_response() and event.content and event.content.parts:
            reply = " ".join((p.text or "") for p in event.content.parts)
    return reply or "(no response)"


st.set_page_config(page_title="Smart Home Assistant", page_icon="H")
st.title("Smart Home Assistant")
st.caption("Ask for a recommendation, compare products, or check compatibility - in English or German.")

runner = get_runner()
session_id = ensure_session(runner)

for role, text in st.session_state.get("history", []):
    with st.chat_message(role):
        st.markdown(text)

if prompt := st.chat_input("e.g. I use Google Home - recommend a thermostat"):
    st.session_state.history.append(("user", prompt))
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer = ask(runner, session_id, prompt)
        st.markdown(answer)
    st.session_state.history.append(("assistant", answer))
