from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def synthesize_response(
    question: str,
    sql_answer: str | None = None,
    document_answer: str | None = None,
    model: str = "gpt-4.1-mini",
) -> str:
    if not sql_answer and not document_answer:
        return "I could not find enough information to answer that."

    if sql_answer and not document_answer:
        return sql_answer

    if document_answer and not sql_answer:
        return document_answer

    prompt = f"""
You are a helpful customer-support assistant.

The user asked:
{question}

Information from structured customer/support SQL data:
{sql_answer}

Information from policy documents:
{document_answer}

Write one final answer that:
1. Combines both sources naturally
2. Clearly explains the result
3. Does not mention internal implementation details like agents, routes, SQL, or vector search
4. Says clearly if the policy answer is general and the final decision may depend on company review
5. Stays concise but helpful
"""

    response = client.responses.create(
        model=model,
        input=prompt,
    )

    return response.output_text.strip()