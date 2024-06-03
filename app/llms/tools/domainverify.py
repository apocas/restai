import os
import requests

def domainverify(domain: str) -> bool:
    """Verify if a domain is available"""
    try:
        headers = {"Authorization": "Basic " + os.environ.get("PTISP_API")}
        response = requests.get(f"https://api.ptisp.pt/domains/{domain}/check", headers=headers)
        data = response.json()
        return data['available']
    except Exception as e:
        return False