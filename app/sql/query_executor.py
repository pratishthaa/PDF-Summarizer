from app.sql.db import get_connection

FORBIDDEN_KEYWORDS = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE"]


def is_safe_select_query(query: str) -> bool:
    normalized = query.strip().upper()

    if not normalized.startswith("SELECT"):
        return False

    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in normalized:
            return False

    return True


def run_safe_query(query: str):
    if not is_safe_select_query(query):
        raise ValueError("Unsafe SQL query blocked. Only SELECT queries are allowed.")

    conn = get_connection()
    cursor = conn.execute(query)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows