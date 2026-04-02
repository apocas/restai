def whois_lookup(domain: str) -> str:
    """
    Look up domain registration (WHOIS) information for a domain name. Returns registrar, creation/expiry dates, name servers, and status.

    Args:
        domain (str): The domain name to look up (e.g. "example.com").
    """
    import socket

    domain = domain.strip().lower()
    if domain.startswith("http"):
        from urllib.parse import urlparse
        domain = urlparse(domain).hostname or domain

    # Determine WHOIS server
    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    whois_servers = {
        "com": "whois.verisign-grs.com",
        "net": "whois.verisign-grs.com",
        "org": "whois.pir.org",
        "io": "whois.nic.io",
        "dev": "whois.nic.google",
        "app": "whois.nic.google",
        "ai": "whois.nic.ai",
        "co": "whois.nic.co",
        "me": "whois.nic.me",
        "uk": "whois.nic.uk",
        "de": "whois.denic.de",
        "fr": "whois.nic.fr",
        "nl": "whois.sidn.nl",
        "eu": "whois.eu",
        "pt": "whois.dns.pt",
    }
    server = whois_servers.get(tld, f"whois.nic.{tld}")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((server, 43))
        query = f"{domain}\r\n"
        if tld == "de":
            query = f"-T dn {domain}\r\n"
        sock.send(query.encode())

        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        sock.close()

        raw = response.decode("utf-8", errors="replace")

        # Extract key fields
        lines = []
        seen_keys = set()
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("%") or line.startswith("#"):
                continue
            lower = line.lower()
            for key in ("domain name", "registrar", "creation date", "updated date",
                        "expir", "name server", "status", "registrant",
                        "nserver", "created", "changed"):
                if lower.startswith(key) or (": " in line and key in lower):
                    label = line.split(":", 1)[0].strip()
                    if label not in seen_keys:
                        lines.append(line)
                        seen_keys.add(label)
                    elif "name server" in lower or "nserver" in lower:
                        lines.append(line)
                    break

        if not lines:
            # Return first 20 non-empty lines as fallback
            fallback = [l.strip() for l in raw.splitlines() if l.strip() and not l.strip().startswith(("%", "#", ">>>"))]
            return "\n".join(fallback[:20]) if fallback else f"No WHOIS data found for {domain}"

        return "\n".join(lines)

    except socket.gaierror:
        return f"Error: WHOIS server '{server}' not found for TLD '.{tld}'"
    except socket.timeout:
        return f"Error: WHOIS lookup timed out for {domain}"
    except Exception as e:
        return f"Error: {e}"
