import os
from io import BytesIO
from pathlib import Path

import requests
import trafilatura
from dotenv import load_dotenv
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import PDFReader
from openai import OpenAI

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError(f"OPENAI_API_KEY is missing. Looked for .env at: {ENV_PATH}")

client = OpenAI(api_key=api_key)

EMBED_MODEL = "text-embedding-3-large"
splitter = SentenceSplitter(chunk_size=1000, chunk_overlap=200)


def _chunk_texts(texts: list[str]) -> list[str]:
    chunks: list[str] = []
    for text in texts:
        if text and text.strip():
            chunks.extend(splitter.split_text(text))
    return chunks


def load_and_chunk_pdf(path: str) -> list[str]:
    docs = PDFReader().load_data(file=path)
    texts = [d.text for d in docs if getattr(d, "text", None)]
    return _chunk_texts(texts)


def load_and_chunk_pdf_bytes(pdf_bytes: bytes) -> list[str]:
    docs = PDFReader().load_data(file=BytesIO(pdf_bytes))
    texts = [d.text for d in docs if getattr(d, "text", None)]
    return _chunk_texts(texts)


def extract_text_from_webpage(url: str) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
        allow_redirects=True,
    )
    response.raise_for_status()

    html = response.text
    if not html or not html.strip():
        raise ValueError(f"Empty HTML returned for URL: {url}")

    text = trafilatura.extract(html)
    if not text or not text.strip():
        raise ValueError(f"Could not extract readable text from URL: {url}")

    return text


def load_and_chunk_url(url: str) -> list[str]:
    lowered = url.lower().strip()

    if "linkedin.com" in lowered:
        raise ValueError(
            "LinkedIn pages are not supported because their content is often login-protected or dynamically rendered."
        )

    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
        allow_redirects=True,
        stream=True,
    )
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()

    if "application/pdf" in content_type or lowered.endswith(".pdf"):
        pdf_bytes = response.content
        return load_and_chunk_pdf_bytes(pdf_bytes)

    html = response.text
    text = trafilatura.extract(html)

    if not text or not text.strip():
        raise ValueError(
            f"Could not extract readable text from URL: {url}. "
            "This site may block scraping or require JavaScript/login."
        )

    return _chunk_texts([text])


def load_and_chunk_source(source_type: str, source_value: str) -> list[str]:
    if source_type == "pdf":
        return load_and_chunk_pdf(source_value)
    if source_type == "url":
        return load_and_chunk_url(source_value)
    raise ValueError(f"Unsupported source_type: {source_type}")


def embed_texts(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]