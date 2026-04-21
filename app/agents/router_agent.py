from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def route_query(question: str, model: str = "gpt-4.1-mini") -> dict:
    prompt = f"""
You are a routing assistant for a multi-agent customer support system.

Classify the user's question into one of these routes:
- "document" -> if the question is about policy documents, refund policy, terms, rules, uploaded PDFs
- "sql" -> if the question is about customer profiles, tickets, account status, plans, support history
- "both" -> if the question needs both policy documents and customer/ticket data

Return JSON only in this format:
{{"route":"document"}}
or
{{"route":"sql"}}
or
{{"route":"both"}}

User question:
{question}
"""

    response = client.responses.create(
        model=model,
        input=prompt,
    )

    text = response.output_text.strip()
    text = text.replace("```json", "").replace("```", "").strip()

    # very simple fallback parsing
    if '"both"' in text:
        return {"route": "both"}
    if '"document"' in text:
        return {"route": "document"}
    return {"route": "sql"}