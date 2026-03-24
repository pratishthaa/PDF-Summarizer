import asyncio
import base64
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import inngest
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="DocuMind",
    page_icon="📘",
    layout="centered",
)


def get_base64_image(path: Path) -> str | None:
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("utf-8")


logo_path = Path(__file__).parent / "logo_.png"
logo_base64 = get_base64_image(logo_path)

watermark_css = ""
if logo_base64:
    watermark_css = f"""
    .stApp::before {{
        content: "";
        position: fixed;
        inset: 0;
        background-image: url("data:image/png;base64,{logo_base64}");
        background-repeat: no-repeat;
        background-position: center center;
        background-size: 420px auto;
        opacity: 0.03;
        pointer-events: none;
        z-index: 0;
    }}
    """

st.markdown(
    f"""
    <style>
        {watermark_css}

        .stApp {{
            scroll-behavior: smooth;
        }}

        .main .block-container {{
            position: relative;
            z-index: 1;
            max-width: 860px;
            padding-top: 4.8rem;
            padding-bottom: 2rem;
        }}

        /* Built-in Streamlit header */
        [data-testid="stHeader"] {{
            background: rgba(255,255,255,0.90) !important;
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border-bottom: 1px solid rgba(0,0,0,0.08);
        }}

        [data-testid="stHeader"]::after {{
            content: "DocuMind";
            display: block;
            position: absolute;
            left: 50%;
            transform: translateX(-50%);
            top: 0.75rem;
            font-size: 2rem;
            font-weight: 700;
            line-height: 1;
            color: #111827 !important;
            font-family: sans-serif;
            letter-spacing: 0.01em;
            pointer-events: none;
        }}

        @media (prefers-color-scheme: dark) {{
            [data-testid="stHeader"] {{
                background: rgba(14,17,23,0.90) !important;
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }}

            [data-testid="stHeader"]::after {{
                color: #f9fafb !important;
            }}
        }}

        .section-card {{
            padding: 1rem 1rem 0.8rem 1rem;
            border: 1px solid rgba(128,128,128,0.18);
            border-radius: 16px;
            margin-bottom: 1rem;
            background: rgba(255,255,255,0.62);
            backdrop-filter: blur(4px);
            -webkit-backdrop-filter: blur(4px);
        }}

        .helper-text {{
            color: #6b7280;
            font-size: 0.95rem;
            margin-top: -0.2rem;
            margin-bottom: 0.6rem;
        }}

        .answer-box {{
            padding: 1rem;
            border-radius: 14px;
            border: 1px solid rgba(128,128,128,0.18);
            background: rgba(255,255,255,0.04);
            margin-top: 0.7rem;
        }}

        .source-ready {{
            padding: 0.85rem 1rem;
            border-radius: 12px;
            border: 1px solid rgba(128,128,128,0.18);
            background: rgba(255,255,255,0.04);
            margin-top: 0.5rem;
            margin-bottom: 0.25rem;
        }}

        @media (prefers-color-scheme: dark) {{
            .section-card {{
                background: rgba(17, 25, 40, 0.42);
            }}

            .helper-text {{
                color: #d1d5db;
            }}
        }}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    return inngest.Inngest(app_id="document_summarizer", is_production=False)


def save_uploaded_pdf(file) -> Path:
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.name
    file_path.write_bytes(file.getbuffer())
    return file_path


def normalize_url_source_id(url: str) -> str:
    parsed = urlparse(url)
    base = parsed.netloc + parsed.path
    cleaned = base.strip("/").replace("/", "_")
    return cleaned or "url_source"


async def send_ingest_event(source_type: str, source_value: str, source_id: str):
    client = get_inngest_client()
    result = await client.send(
        inngest.Event(
            name="documentsummarizer/ingest_source",
            data={
                "source_type": source_type,
                "source_value": source_value,
                "source_id": source_id,
            },
        )
    )
    return result[0]


async def send_query_event(
    question: str,
    top_k: int,
    source_id: str | None,
    chat_history: list[dict],
):
    client = get_inngest_client()
    result = await client.send(
        inngest.Event(
            name="documentsummarizer/query_source_ai",
            data={
                "question": question,
                "top_k": top_k,
                "source_id": source_id,
                "chat_history": chat_history,
            },
        )
    )
    return result[0]


def _inngest_api_base() -> str:
    return os.getenv("INNGEST_API_BASE", "http://127.0.0.1:8288/v1")


def fetch_runs(event_id: str) -> list[dict]:
    url = f"{_inngest_api_base()}/events/{event_id}/runs"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])


def wait_for_run_output(
    event_id: str,
    timeout_s: float = 300.0,
    poll_interval_s: float = 1.0,
) -> dict:
    start = time.time()
    last_status = None

    while True:
        runs = fetch_runs(event_id)
        if runs:
            run = runs[0]
            status = run.get("status")
            last_status = status or last_status

            if status in ("Completed", "Succeeded", "Success", "Finished"):
                output = run.get("output") or {}
                if isinstance(output, dict):
                    return output
                return {}

            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Function run {status}: {run}")

        if time.time() - start > timeout_s:
            raise TimeoutError(
                f"Timed out waiting for run output (last status: {last_status})"
            )

        time.sleep(poll_interval_s)


if "indexed_sources" not in st.session_state:
    st.session_state.indexed_sources = []

if "chat_history" not in st.session_state:
    st.session_state.chat_history = {}

if "active_source" not in st.session_state:
    st.session_state.active_source = "All sources"

if "last_added_source" not in st.session_state:
    st.session_state.last_added_source = None


st.markdown("<div class='section-card'>", unsafe_allow_html=True)
st.subheader("Add something to learn from")
st.markdown(
    "<div class='helper-text'>Upload a PDF or paste a public webpage or PDF link.</div>",
    unsafe_allow_html=True,
)

input_type = st.radio("Choose input", ["PDF", "URL"], horizontal=True)

if input_type == "PDF":
    uploaded = st.file_uploader("Upload a PDF", type=["pdf"], accept_multiple_files=False)

    if uploaded is not None:
        st.caption(f"Selected file: {uploaded.name}")

    if uploaded is not None and st.button("Learn from PDF", use_container_width=True):
        try:
            with st.spinner("Reading and indexing your PDF..."):
                path = save_uploaded_pdf(uploaded)
                source_id = path.name

                event_id = asyncio.run(
                    send_ingest_event(
                        source_type="pdf",
                        source_value=str(path.resolve()),
                        source_id=source_id,
                    )
                )

                wait_for_run_output(event_id)

                if source_id not in st.session_state.indexed_sources:
                    st.session_state.indexed_sources.append(source_id)

                if source_id not in st.session_state.chat_history:
                    st.session_state.chat_history[source_id] = []

                st.session_state.active_source = source_id
                st.session_state.last_added_source = source_id

                st.success("Ready for questions.")
        except Exception as e:
            st.error(str(e))
else:
    url = st.text_input("Paste a webpage or PDF URL")

    if st.button("Learn from URL", use_container_width=True):
        if not url.strip():
            st.error("Please enter a URL.")
        else:
            try:
                with st.spinner("Fetching and indexing your URL..."):
                    clean_url = url.strip()
                    source_id = normalize_url_source_id(clean_url)

                    event_id = asyncio.run(
                        send_ingest_event(
                            source_type="url",
                            source_value=clean_url,
                            source_id=source_id,
                        )
                    )

                    wait_for_run_output(event_id)

                    if source_id not in st.session_state.indexed_sources:
                        st.session_state.indexed_sources.append(source_id)

                    if source_id not in st.session_state.chat_history:
                        st.session_state.chat_history[source_id] = []

                    st.session_state.active_source = source_id
                    st.session_state.last_added_source = source_id

                    st.success("Ready for questions.")
            except Exception as e:
                st.error(str(e))

if st.session_state.last_added_source:
    st.markdown(
        f"<div class='source-ready'><strong>Current source:</strong> {st.session_state.last_added_source}</div>",
        unsafe_allow_html=True,
    )

st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div class='section-card'>", unsafe_allow_html=True)
st.subheader("Ask questions")
st.markdown(
    "<div class='helper-text'>Ask about the current source or search across everything you’ve added.</div>",
    unsafe_allow_html=True,
)

source_options = ["All sources"] + st.session_state.indexed_sources

default_index = 0
if st.session_state.active_source in source_options:
    default_index = source_options.index(st.session_state.active_source)

selected_source = st.selectbox("Ask about", source_options, index=default_index)
st.session_state.active_source = selected_source

history_key = selected_source
history = st.session_state.chat_history.get(history_key, [])

col1, col2 = st.columns([1, 1])

with col1:
    if history and st.button("Clear chat", use_container_width=True):
        st.session_state.chat_history[history_key] = []
        st.rerun()

with col2:
    if st.session_state.indexed_sources and st.button("Reset app", use_container_width=True):
        st.session_state.indexed_sources = []
        st.session_state.chat_history = {}
        st.session_state.active_source = "All sources"
        st.session_state.last_added_source = None
        st.rerun()

with st.form("query_form"):
    question = st.text_input(
        "Type your question",
        placeholder="Example: What are the main takeaways?",
    )
    top_k = st.slider("Depth of search", min_value=1, max_value=10, value=5)
    submitted = st.form_submit_button("Ask", use_container_width=True)

if submitted:
    if not question.strip():
        st.error("Please enter a question.")
    else:
        try:
            with st.spinner("Searching and drafting an answer..."):
                source_id = None if selected_source == "All sources" else selected_source
                recent_history = st.session_state.chat_history.get(history_key, [])[-5:]

                event_id = asyncio.run(
                    send_query_event(
                        question=question.strip(),
                        top_k=int(top_k),
                        source_id=source_id,
                        chat_history=recent_history,
                    )
                )

                output = wait_for_run_output(event_id)
                answer = output.get("answer", "")

                if history_key not in st.session_state.chat_history:
                    st.session_state.chat_history[history_key] = []

                st.session_state.chat_history[history_key].append(
                    {
                        "question": question.strip(),
                        "answer": answer or "(No answer)",
                    }
                )

                st.rerun()
        except Exception as e:
            st.error(str(e))

st.markdown("</div>", unsafe_allow_html=True)

if history:
    st.subheader("Conversation")

    for i, item in enumerate(history, start=1):
        with st.expander(f"{i}. {item['question']}", expanded=(i == len(history))):
            st.markdown(f"**Question**  \n{item['question']}")
            st.markdown(
                f"<div class='answer-box'><strong>Answer</strong><br><br>{item['answer']}</div>",
                unsafe_allow_html=True,
            )