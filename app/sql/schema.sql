CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    plan_type TEXT NOT NULL,
    signup_date TEXT NOT NULL,
    account_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS support_tickets (
    ticket_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    issue_category TEXT NOT NULL,
    ticket_subject TEXT NOT NULL,
    ticket_description TEXT NOT NULL,
    ticket_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolution_summary TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);