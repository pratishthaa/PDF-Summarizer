import datetime
import logging
import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI
import inngest
import inngest.fast_api
from inngest.experimental import ai

from .custom_types import RAGChunkAndSrc, RAGSearchResult, RAGUpsertResult
from .data_loader import embed_texts, load_and_chunk_source
from .vector_db import QdrantStorage

load_dotenv()

inngest_client = inngest.Inngest(
    app_id="document_summarizer",
    logger=logging.getLogger("uvicorn"),
    is_production=False,
    serializer=inngest.PydanticSerializer(),
)


@inngest_client.create_function(
    fn_id="Document Summarizer: Ingest Source",
    trigger=inngest.TriggerEvent(event="documentsummarizer/ingest_source"),
    throttle=inngest.Throttle(
        limit=2,
        period=datetime.timedelta(minutes=1),
    ),
    rate_limit=inngest.RateLimit(
        limit=5,
        period=datetime.timedelta(minutes=10),
        key="event.data.source_id",
    ),
)
async def documentsummarizer_ingest_source(ctx: inngest.Context):
    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
        source_type = ctx.event.data["source_type"]
        source_value = ctx.event.data["source_value"]
        source_id = ctx.event.data["source_id"]

        print(f"[INGEST] Starting load for source_type={source_type}, source_id={source_id}")
        chunks = load_and_chunk_source(source_type, source_value)
        print(f"[INGEST] Loaded and chunked {len(chunks)} chunks for {source_id}")

        return RAGChunkAndSrc(
            chunks=chunks,
            source_id=source_id,
            source_type=source_type,
        )

    def _upsert(chunks_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
        chunks = chunks_and_src.chunks
        source_id = chunks_and_src.source_id
        source_type = chunks_and_src.source_type

        print(f"[INGEST] Embedding {len(chunks)} chunks for {source_id}")
        vecs = embed_texts(chunks)

        ids = [
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}:{i}"))
            for i in range(len(chunks))
        ]

        payloads = [
            {
                "source": source_id,
                "source_type": source_type,
                "text": chunks[i],
            }
            for i in range(len(chunks))
        ]

        QdrantStorage().upsert(ids, vecs, payloads)
        print(f"[INGEST] Upsert complete for {source_id}")

        return RAGUpsertResult(
            ingested=len(chunks),
            source_id=source_id,
            source_type=source_type,
        )

    chunks_and_src = await ctx.step.run(
        "load-and-chunk-source",
        lambda: _load(ctx),
        output_type=RAGChunkAndSrc,
    )

    ingested = await ctx.step.run(
        "embed-and-upsert",
        lambda: _upsert(chunks_and_src),
        output_type=RAGUpsertResult,
    )

    return ingested.model_dump()


@inngest_client.create_function(
    fn_id="Document Summarizer: Query Source",
    trigger=inngest.TriggerEvent(event="documentsummarizer/query_source_ai"),
)
async def documentsummarizer_query_source_ai(ctx: inngest.Context):
    def _search(question: str, top_k: int = 5, source_id: str | None = None) -> RAGSearchResult:
        query_vec = embed_texts([question])[0]
        store = QdrantStorage()
        found = store.search(query_vec, top_k=top_k, source_id=source_id)
        return RAGSearchResult(contexts=found["contexts"], sources=found["sources"])

    question = ctx.event.data["question"]
    top_k = int(ctx.event.data.get("top_k", 5))
    source_id = ctx.event.data.get("source_id")
    chat_history = ctx.event.data.get("chat_history", [])

    print(f"[QUERY] Question received. source_id={source_id}, top_k={top_k}")

    found = await ctx.step.run(
        "embed-and-search",
        lambda: _search(question, top_k, source_id),
        output_type=RAGSearchResult,
    )

    print(f"[QUERY] Retrieved {len(found.contexts)} contexts from {len(found.sources)} source(s)")

    if not found.contexts:
        return {
            "answer": "I could not find relevant context in the indexed source(s).",
            "sources": [],
            "num_contexts": 0,
        }

    history_text = ""
    if chat_history:
        history_parts = []
        for item in chat_history[-5:]:
            q = item.get("question", "").strip()
            a = item.get("answer", "").strip()
            if q or a:
                history_parts.append(f"User: {q}\nAssistant: {a}")
        history_text = "\n\n".join(history_parts)

    context_block = "\n\n".join(f"- {c}" for c in found.contexts)

    user_content = (
        "Use the retrieved context to answer the user's question.\n\n"
        f"Previous conversation:\n{history_text if history_text else 'None'}\n\n"
        f"Retrieved context:\n{context_block}\n\n"
        f"Question: {question}\n\n"
        "Instructions:\n"
        "- Answer using the retrieved context.\n"
        "- Use the previous conversation only to understand follow-up references like 'that', 'this', or 'explain more'.\n"
        "- If the answer is not supported by the retrieved context, say that clearly.\n"
        "- Be concise but helpful."
    )

    adapter = ai.openai.Adapter(
        auth_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini",
    )

    res = await ctx.step.ai.infer(
        "llm-answer",
        adapter=adapter,
        body={
            "max_tokens": 1024,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": "You answer questions using only the provided retrieved context.",
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
        },
    )

    answer = res["choices"][0]["message"]["content"].strip()
    print("[QUERY] Answer generated successfully")

    return {
        "answer": answer,
        "sources": found.sources,
        "num_contexts": len(found.contexts),
    }


app = FastAPI()

inngest.fast_api.serve(
    app,
    inngest_client,
    functions=[documentsummarizer_ingest_source, documentsummarizer_query_source_ai],
)