import logging
import os
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI
from mcp.server.fastmcp import FastMCP

from app.agents.router_agent import route_query
from app.agents.sql_agent import handle_sql_query
from app.agents.response_synthesizer import synthesize_response
from app.data_loader import embed_texts
from app.vector_db import QdrantStorage

load_dotenv()

logger = logging.getLogger("mcp_server")
logging.basicConfig(level=logging.INFO)

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

mcp = FastMCP("DocuMind MCP Server", json_response=True)

mcp.settings.host = "127.0.0.1"
mcp.settings.port = 8001


def query_document_source(
    question: str,
    top_k: int = 5,
    source_id: Optional[str] = None,
) -> dict:
    query_vec = embed_texts([question])[0]
    store = QdrantStorage()
    found = store.search(query_vec, top_k=top_k, source_id=source_id)

    contexts = found["contexts"]
    sources = found["sources"]

    if not contexts:
        return {
            "answer": "I could not find relevant context in the indexed source(s).",
            "sources": [],
            "num_contexts": 0,
        }

    context_block = "\n\n".join(f"- {c}" for c in contexts)

    prompt = (
        "You answer questions using only the provided retrieved context.\n\n"
        f"Retrieved context:\n{context_block}\n\n"
        f"Question: {question}\n\n"
        "Instructions:\n"
        "- Answer using the retrieved context only.\n"
        "- If the answer is not supported by the retrieved context, say that clearly.\n"
        "- Be concise but helpful."
    )

    response = openai_client.responses.create(
        model="gpt-4.1-mini",
        input=prompt,
    )

    answer = response.output_text.strip()

    return {
        "answer": answer,
        "sources": sources,
        "num_contexts": len(contexts),
    }


@mcp.tool()
def query_customer_data(question: str) -> dict:
    """
    Query structured customer and support-ticket data from the SQLite database.
    Use this for customer profiles, account status, plans, ticket history, and support summaries.
    """
    logger.info("MCP tool called: query_customer_data")
    return handle_sql_query(question)


@mcp.tool()
def query_policy_documents(
    question: str,
    source_id: Optional[str] = None,
    top_k: int = 5,
) -> dict:
    """
    Query uploaded policy or support documents indexed in the vector database.
    Use this for refund policy, cancellation policy, terms, support guidelines, or uploaded PDF questions.
    """
    logger.info("MCP tool called: query_policy_documents")
    return query_document_source(question=question, source_id=source_id, top_k=top_k)


@mcp.tool()
def route_support_question(
    question: str,
    source_id: Optional[str] = None,
    top_k: int = 5,
) -> dict:
    """
    Route a support question to the SQL agent, document agent, or both,
    then return a single final answer.
    """
    logger.info("MCP tool called: route_support_question")

    route = route_query(question)

    if route["route"] == "sql":
        sql_result = handle_sql_query(question)
        return {
            "route": "sql",
            "answer": sql_result["answer"],
            "sql_query": sql_result["sql_query"],
            "rows": sql_result["rows"],
        }

    if route["route"] == "document":
        doc_result = query_document_source(
            question=question,
            source_id=source_id,
            top_k=top_k,
        )
        return {
            "route": "document",
            "answer": doc_result["answer"],
            "sources": doc_result["sources"],
            "num_contexts": doc_result["num_contexts"],
        }

    sql_result = handle_sql_query(question)
    doc_result = query_document_source(
        question=question,
        source_id=source_id,
        top_k=top_k,
    )

    final_answer = synthesize_response(
        question=question,
        sql_answer=sql_result["answer"],
        document_answer=doc_result["answer"],
    )

    return {
        "route": "both",
        "answer": final_answer,
        "sql_query": sql_result["sql_query"],
        "rows": sql_result["rows"],
        "sources": doc_result["sources"],
        "num_contexts": doc_result["num_contexts"],
        "sql_answer": sql_result["answer"],
        "document_answer": doc_result["answer"],
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")