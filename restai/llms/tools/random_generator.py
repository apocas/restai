from typing import Optional


def random_generator(
    action: str = "uuid",
    count: Optional[int] = 1,
    min_val: Optional[int] = 0,
    max_val: Optional[int] = 100,
    length: Optional[int] = 16,
    choices: Optional[str] = None,
) -> str:
    """
    Generate random values: UUIDs, passwords, numbers, or pick from a list.

    Args:
        action (str): What to generate — "uuid", "password", "number", "choice". Default: "uuid".
        count (Optional[int]): How many values to generate. Default: 1.
        min_val (Optional[int]): Minimum value for "number" action. Default: 0.
        max_val (Optional[int]): Maximum value for "number" action. Default: 100.
        length (Optional[int]): Length for "password" action. Default: 16.
        choices (Optional[str]): Comma-separated options for "choice" action (e.g. "red,blue,green").
    """
    import uuid
    import secrets
    import string
    import random

    count = max(1, min(count or 1, 50))
    results = []

    for _ in range(count):
        if action == "uuid":
            results.append(str(uuid.uuid4()))

        elif action == "password":
            ln = max(4, min(length or 16, 128))
            alphabet = string.ascii_letters + string.digits + "!@#$%&*-_"
            pw = "".join(secrets.choice(alphabet) for _ in range(ln))
            results.append(pw)

        elif action == "number":
            lo = min_val if min_val is not None else 0
            hi = max_val if max_val is not None else 100
            results.append(str(random.randint(lo, hi)))

        elif action == "choice":
            if not choices:
                return "Error: 'choices' parameter required (comma-separated list)"
            opts = [c.strip() for c in choices.split(",") if c.strip()]
            if not opts:
                return "Error: No valid choices provided"
            results.append(random.choice(opts))

        else:
            return f"Error: Unknown action '{action}'. Use: uuid, password, number, choice"

    return "\n".join(results)
