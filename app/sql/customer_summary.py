from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def summarize_sql_result(question: str, rows: list[dict], model: str = "gpt-4.1-mini") -> str:
    if not rows:
        return "I could not find matching customer or support-ticket information in the database."

    prompt = f"""
You are a helpful customer-support assistant.

User question:
{question}

SQL results:
{rows}

Write a concise, user-friendly answer.
If the results relate to one customer, summarize their profile and support history clearly.
If multiple customers or tickets are returned, summarize the key findings.
"""

    response = client.responses.create(
        model=model,
        input=prompt,
    )

    return response.output_text.strip()