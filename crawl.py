import requests
import json

payload = {
    "host": "https://roma.co.ke/",
    "key": "c2a41f16d2224232915eaedcd257ccef",
    "keyLocation": "https://roma.co.ke/c2a41f16d2224232915eaedcd257ccef.txt",
    "urlList": [
        
        "https://roma.co.ke/?article=mllc5ndqw3tkwo4tsxa",
        "https://roma.co.ke/?article=mlmet3b8ql821uqcqu8",
        "https://roma.co.ke/?article=mlnxk3mouyog4hftmth",
        "https://roma.co.ke/?article=mlza16vr94j0pf2y35h",
        "https://roma.co.ke/"

    ]
}

headers = {
    "Content-Type": "application/json; charset=utf-8"
}

response = requests.post(
    "https://api.indexnow.org/indexnow",
    headers=headers,
    data=json.dumps(payload)
)

print(f"Status Code: {response.status_code}")

if response.status_code == 200:
    print("✅ Success! All URLs submitted to IndexNow.")
elif response.status_code == 202:
    print("⏳ Accepted — key not yet verified.")
elif response.status_code == 403:
    print("❌ Key not found. Check your keyLocation URL.")
elif response.status_code == 422:
    print("❌ Invalid request — check your URLs match the host.")
else:
    print("⚠️ Unexpected response.")
