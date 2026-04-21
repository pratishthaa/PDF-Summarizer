from app.sql.text_to_sql import generate_sql
from app.sql.query_executor import run_safe_query
from app.sql.customer_summary import summarize_sql_result


def handle_sql_query(user_question: str) -> dict:
    sql_query = generate_sql(user_question)
    rows = run_safe_query(sql_query)
    answer = summarize_sql_result(user_question, rows)

    return {
        "agent": "sql",
        "question": user_question,
        "sql_query": sql_query,
        "rows": rows,
        "answer": answer,
    }