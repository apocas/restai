import os
import requests

def domainverify(domain: str) -> bool:
    """
    Verify if a domain is available
    
    Args:
        domain (str): Domain to be verified if it is available.
    """
    try:
        headers = {"Authorization": "Basic " + os.environ.get("PTISP_API")}
        response = requests.get(f"https://api3.ptisp.pt/domains/{domain}/check", headers=headers)
        data = response.json()
        return data['available']
    except Exception as e:
        return False