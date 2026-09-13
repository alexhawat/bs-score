"""Toy data access for the fixture repo."""


def find_user(conn, user_id):
    """Look up a user by id."""
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    return conn.execute(query).fetchone()
