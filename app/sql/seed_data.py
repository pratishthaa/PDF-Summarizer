from app.sql.db import get_connection, init_db

print("seed_data.py started")

CUSTOMERS = [
    (1, "Ema Carter", "ema@example.com", "Premium", "2024-03-10", "Active"),
]

TICKETS = [
    (101, 1, "Refund", "Refund request for duplicate charge",
     "Customer reported being charged twice for the same monthly plan.",
     "Open", "2026-04-18", None, None),
]

def seed():
    print("Initializing DB...")
    init_db()

    print("Opening connection...")
    conn = get_connection()

    print("Clearing old data...")
    conn.execute("DELETE FROM support_tickets")
    conn.execute("DELETE FROM customers")

    print("Inserting customers...")
    conn.executemany(
        """
        INSERT INTO customers
        (customer_id, name, email, plan_type, signup_date, account_status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        CUSTOMERS,
    )

    print("Inserting tickets...")
    conn.executemany(
        """
        INSERT INTO support_tickets
        (ticket_id, customer_id, issue_category, ticket_subject, ticket_description,
         ticket_status, created_at, resolved_at, resolution_summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        TICKETS,
    )

    conn.commit()
    conn.close()
    print("Seed complete.")


if __name__ == "__main__":
    seed()
    print("Database seeded successfully.")