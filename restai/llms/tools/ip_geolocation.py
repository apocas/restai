def ip_geolocation(ip: str) -> str:
    """
    Look up the geographic location and network info for an IP address. Uses the free ip-api.com service (no API key needed).

    Args:
        ip (str): The IP address to look up (e.g. "8.8.8.8").
    """
    import requests

    try:
        resp = requests.get(
            f"http://ip-api.com/json/{ip.strip()}",
            params={"fields": "status,message,country,regionName,city,zip,lat,lon,timezone,isp,org,as,query"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "success":
            return f"Error: {data.get('message', 'Lookup failed for ' + ip)}"

        lines = [
            f"IP: {data.get('query', ip)}",
            f"Location: {data.get('city', '?')}, {data.get('regionName', '?')}, {data.get('country', '?')}",
            f"ZIP: {data.get('zip', 'N/A')}",
            f"Coordinates: {data.get('lat', '?')}, {data.get('lon', '?')}",
            f"Timezone: {data.get('timezone', 'N/A')}",
            f"ISP: {data.get('isp', 'N/A')}",
            f"Org: {data.get('org', 'N/A')}",
            f"AS: {data.get('as', 'N/A')}",
        ]
        return "\n".join(lines)

    except requests.RequestException as e:
        return f"Error: Failed to reach ip-api.com — {e}"
