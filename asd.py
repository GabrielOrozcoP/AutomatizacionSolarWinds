import requests
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CLIENT_ID = "eawtheb6j64q3whehv2aj7rb"
CLIENT_SECRET = "5zD9CUUDVCYW2sBxkpazNpEh"
CUSTOMER_ID = "Zz17LnLF5r8xQpI"

def diagnostico_ips():
    # 1. Obtener Token
    url = "https://id.cisco.com/oauth2/default/v1/token"
    payload = {'grant_type': 'client_credentials'}
    token = requests.post(url, data=payload, auth=(CLIENT_ID, CLIENT_SECRET), verify=False).json()['access_token']

    # 2. Bajar 1 solo registro de Network Elements (IPs)
    url_ne = f"https://apix.cisco.com/cs/api/v2/inventory/network-elements?customerId={CUSTOMER_ID}&page=1&rows=1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    res = requests.get(url_ne, headers=headers, verify=False)
    
    if res.status_code == 200:
        data = res.json().get('data', [])
        if data:
            print("\n=== LLAVES ENCONTRADAS EN NETWORK ELEMENTS (IPs) ===")
            print(json.dumps(list(data[0].keys()), indent=4))
        else:
            print("No hay datos de red para este ID.")
    else:
        print(f"Error: {res.status_code}")

diagnostico_ips()