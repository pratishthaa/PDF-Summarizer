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

FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://127.0.0.1:8000")


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
            max-width: 960px;
            padding-top: 4.8rem;
            padding-bottom: 2rem;
        }}

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

        .small-pill {{
            display: inline-block;
            padding: 0.25rem 0.6rem;
            border-radius: 999px;
            border: 1px solid rgba(128,128,128,0.18);
            margin-right: 0.4rem;
            margin-bottom: 0.4rem;
            font-size: 0.85rem;
        }}

        @media (prefers-color-scheme: dark) {{
            .section-card {{
                background: rgba(17, 25, 40, 0.42);
            }}

            .helper-text {{
                color: #d1d5db;
            }}

            [data-testid="stHeader"] {{
                background: rgba(14,17,23,0.90) !important;
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }}

            [data-testid="stHeader"]::after {{
                color: #f9fafb !important;
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


def save_uploaded_sqlite(file) -> Path:
    sql_dir = Path("app/sql")
    sql_dir.mkdir(parents=True, exist_ok=True)
    db_path = sql_dir / "customer_support.db"
    db_path.write_bytes(file.getbuffer())
    return db_path


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
                return output if isinstance(output, dict) else {}

            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Function run {status}: {run}")

        if time.time() - start > timeout_s:
            raise TimeoutError(
                f"Timed out waiting for run output (last status: {last_status})"
            )

        time.sleep(poll_interval_s)


def ask_backend_chat(question: str, source_id: str | None, top_k: int) -> dict:
    payload = {
        "question": question,
        "source_id": source_id,
        "top_k": top_k,
    }
    resp = requests.post(f"{FASTAPI_BASE_URL}/chat", json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


if "indexed_sources" not in st.session_state:
    st.session_state.indexed_sources = []

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "active_source" not in st.session_state:
    st.session_state.active_source = "All documents"

if "last_added_source" not in st.session_state:
    st.session_state.last_added_source = None

if "db_loaded" not in st.session_state:
    st.session_state.db_loaded = False


st.markdown("<div class='section-card'>", unsafe_allow_html=True)
st.subheader("Add data sources")
st.markdown(
    "<div class='helper-text'>Upload one or more PDFs for policy/document knowledge, and optionally upload a SQLite database file for structured customer data.</div>",
    unsafe_allow_html=True,
)

tab1, tab2, tab3 = st.tabs(["PDFs", "SQLite DB", "URL"])

with tab1:
    uploaded_pdfs = st.file_uploader(
        "Upload one or more PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
    )

    if uploaded_pdfs:
        st.caption("Selected PDFs:")
        for f in uploaded_pdfs:
            st.markdown(f"- {f.name}")

    if uploaded_pdfs and st.button("Learn from PDFs", use_container_width=True):
        try:
            with st.spinner("Reading and indexing uploaded PDFs..."):
                added_sources = []

                for uploaded in uploaded_pdfs:
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

                    added_sources.append(source_id)

                if added_sources:
                    st.session_state.active_source = "All documents"
                    st.session_state.last_added_source = ", ".join(added_sources)

                st.success("PDFs indexed and ready for questions.")
        except Exception as e:
            st.error(str(e))

with tab2:
    uploaded_db = st.file_uploader(
        "Upload SQLite database file",
        type=["db", "sqlite", "sqlite3"],
        accept_multiple_files=False,
        key="db_uploader",
    )

    if uploaded_db is not None:
        st.caption(f"Selected database: {uploaded_db.name}")

    if uploaded_db is not None and st.button("Use this database", use_container_width=True):
        try:
            with st.spinner("Saving SQLite database..."):
                save_uploaded_sqlite(uploaded_db)
                st.session_state.db_loaded = True
                st.success("SQLite database loaded for customer-data questions.")
        except Exception as e:
            st.error(str(e))

with tab3:
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

                    st.session_state.active_source = source_id
                    st.session_state.last_added_source = source_id

                    st.success("URL indexed and ready for questions.")
            except Exception as e:
                st.error(str(e))

if st.session_state.last_added_source:
    st.markdown(
        f"<div class='source-ready'><strong>Latest document source(s):</strong> {st.session_state.last_added_source}</div>",
        unsafe_allow_html=True,
    )

status_parts = []
if st.session_state.indexed_sources:
    status_parts.append(f"{len(st.session_state.indexed_sources)} document source(s) ready")
if st.session_state.db_loaded:
    status_parts.append("SQLite database loaded")

if status_parts:
    st.markdown(
        "<div class='source-ready'><strong>Status:</strong> "
        + " | ".join(status_parts)
        + "</div>",
        unsafe_allow_html=True,
    )

st.markdown("</div>", unsafe_allow_html=True)


st.markdown("<div class='section-card'>", unsafe_allow_html=True)
st.subheader("Ask questions")
st.markdown(
    "<div class='helper-text'>Ask about documents, customer data, or questions that need both. The backend router will choose the right path.</div>",
    unsafe_allow_html=True,
)

source_options = ["All documents"] + st.session_state.indexed_sources

default_index = 0
if st.session_state.active_source in source_options:
    default_index = source_options.index(st.session_state.active_source)

selected_source = st.selectbox("Document scope", source_options, index=default_index)
st.session_state.active_source = selected_source

if st.session_state.indexed_sources:
    st.markdown("**Indexed documents**")
    pills = "".join(
        [f"<span class='small-pill'>{src}</span>" for src in st.session_state.indexed_sources]
    )
    st.markdown(pills, unsafe_allow_html=True)

col1, col2 = st.columns([1, 1])

with col1:
    if st.session_state.chat_history and st.button("Clear chat", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

with col2:
    if (st.session_state.indexed_sources or st.session_state.db_loaded) and st.button("Reset app", use_container_width=True):
        st.session_state.indexed_sources = []
        st.session_state.chat_history = []
        st.session_state.active_source = "All documents"
        st.session_state.last_added_source = None
        st.session_state.db_loaded = False
        st.rerun()

with st.form("query_form"):
    question = st.text_input(
        "Type your question",
        placeholder="Example: Based on the refund policy and Ema Carter's latest ticket, is she likely eligible for a refund?",
    )
    top_k = st.slider("Depth of document search", min_value=1, max_value=10, value=5)
    submitted = st.form_submit_button("Ask", use_container_width=True)

if submitted:
    if not question.strip():
        st.error("Please enter a question.")
    else:
        try:
            with st.spinner("Thinking..."):
                source_id = None if selected_source == "All documents" else selected_source
                result = ask_backend_chat(
                    question=question.strip(),
                    source_id=source_id,
                    top_k=int(top_k),
                )

                st.session_state.chat_history.append(
                    {
                        "question": question.strip(),
                        "route": result.get("route", "unknown"),
                        "answer": result.get("answer", "(No answer)"),
                        "sql_query": result.get("sql_query"),
                        "rows": result.get("rows"),
                        "sources": result.get("sources"),
                        "num_contexts": result.get("num_contexts"),
                        "sql_answer": result.get("sql_answer"),
                        "document_answer": result.get("document_answer"),
                    }
                )

                st.rerun()
        except Exception as e:
            st.error(str(e))

st.markdown("</div>", unsafe_allow_html=True)


if st.session_state.chat_history:
    st.subheader("Conversation")

    for i, item in enumerate(st.session_state.chat_history, start=1):
        with st.expander(f"{i}. {item['question']}", expanded=(i == len(st.session_state.chat_history))):
            st.markdown(f"**Question**  \n{item['question']}")
            st.markdown(f"**Route used:** `{item.get('route', 'unknown')}`")

            st.markdown(
                f"<div class='answer-box'><strong>Answer</strong><br><br>{item['answer']}</div>",
                unsafe_allow_html=True,
            )

            if item.get("sources"):
                st.markdown("**Document sources**")
                for src in item["sources"]:
                    st.markdown(f"- {src}")

            if item.get("sql_query"):
                with st.expander("Generated SQL"):
                    st.code(item["sql_query"], language="sql")

            if item.get("rows"):
                with st.expander("SQL rows returned"):
                    st.json(item["rows"])

            if item.get("sql_answer") or item.get("document_answer"):
                with st.expander("Agent details"):
                    if item.get("sql_answer"):
                        st.markdown("**SQL agent answer**")
                        st.write(item["sql_answer"])
                    if item.get("document_answer"):
                        st.markdown("**Document agent answer**")
                        st.write(item["document_answer"])