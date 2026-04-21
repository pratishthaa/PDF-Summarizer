from openai import OpenAI
from dotenv import load_dotenv
import os

from app.utils.prompts import TEXT_TO_SQL_PROMPT

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_sql(question: str, model: str = "gpt-4.1-mini") -> str:
    prompt = TEXT_TO_SQL_PROMPT.format(question=question)

    response = client.responses.create(
        model=model,
        input=prompt,
    )

    sql_query = response.output_text.strip()
    sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
    return sql_query