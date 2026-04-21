from app.agents.sql_agent import handle_sql_query

result = handle_sql_query(
    "Give me a quick overview of customer Ema Carter's profile and past support ticket details."
)

print("Generated SQL:")
print(result["sql_query"])
print("\nAnswer:")
print(result["answer"])
print("\nRows:")
print(result["rows"])