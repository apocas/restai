from typing import Optional


def datetime_tool(
    action: str = "now",
    timezone: Optional[str] = "UTC",
    date: Optional[str] = None,
    days: Optional[int] = None,
) -> str:
    """
    Get current date/time, convert between timezones, or perform date arithmetic.

    Args:
        action (str): Action to perform. One of: "now" (current date/time), "add" (add/subtract days from a date), "weekday" (get day of week for a date), "diff" (days between two dates — put second date in timezone param).
        timezone (Optional[str]): Timezone name (e.g. "US/Eastern", "Europe/London", "Asia/Tokyo", "UTC"). For "diff" action, this is the second date.
        date (Optional[str]): Date string in YYYY-MM-DD format. Used with "add", "weekday", and "diff" actions.
        days (Optional[int]): Number of days to add (positive) or subtract (negative). Used with "add" action.
    """
    from datetime import datetime, timedelta, timezone as tz
    import zoneinfo

    try:
        if action == "now":
            try:
                zi = zoneinfo.ZoneInfo(timezone)
            except Exception:
                return f"Error: Unknown timezone '{timezone}'. Examples: UTC, US/Eastern, Europe/London, Asia/Tokyo"
            now = datetime.now(zi)
            return f"{now.strftime('%Y-%m-%d %H:%M:%S %Z')} ({now.strftime('%A')})"

        elif action == "add":
            if not date:
                return "Error: 'date' parameter required for 'add' action (YYYY-MM-DD)"
            if days is None:
                return "Error: 'days' parameter required for 'add' action"
            dt = datetime.strptime(date, "%Y-%m-%d")
            result = dt + timedelta(days=days)
            return f"{result.strftime('%Y-%m-%d')} ({result.strftime('%A')})"

        elif action == "weekday":
            if not date:
                return "Error: 'date' parameter required for 'weekday' action (YYYY-MM-DD)"
            dt = datetime.strptime(date, "%Y-%m-%d")
            return dt.strftime("%A")

        elif action == "diff":
            if not date:
                return "Error: 'date' parameter required for 'diff' action (YYYY-MM-DD)"
            if not timezone:
                return "Error: put the second date in the 'timezone' parameter for 'diff' action"
            dt1 = datetime.strptime(date, "%Y-%m-%d")
            dt2 = datetime.strptime(timezone, "%Y-%m-%d")
            delta = (dt2 - dt1).days
            return f"{abs(delta)} days"

        else:
            return f"Error: Unknown action '{action}'. Use: now, add, weekday, diff"

    except ValueError as e:
        return f"Error: {e}. Use YYYY-MM-DD format for dates."
    except Exception as e:
        return f"Error: {e}"
