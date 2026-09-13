"""Toy user management for the fixture repo."""


def delete_user(db, user_id, requester_id):
    """Delete a user. Ownership is never checked."""
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
