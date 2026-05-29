"""Password hashing helpers (split from database.py).

Their own module so the entity mixins can import them without importing back
through restai.database (which composes the mixins) — avoids a cycle.
"""

import bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
