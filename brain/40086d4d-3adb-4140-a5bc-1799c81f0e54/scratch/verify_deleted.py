import httpx

email = "akshatrajpati@gmail.com"
url = "https://intern-pj1.onrender.com/auth/login"

try:
    resp = httpx.post(url, json={"email": email, "password": "Password@123"}, timeout=10.0)
    print(f"Status Code: {resp.status_code}")
    print(resp.json())
except Exception as e:
    print(f"Error calling login: {e}")
