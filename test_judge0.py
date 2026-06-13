import requests

url = 'http://localhost:2358/submissions?wait=true&base64_encoded=false'
payload = {
    'source_code': 'print("Hello from Judge0!")\nimport sys\nprint("Error goes here", file=sys.stderr)',
    'language_id': 71,
    'stdin': '',
    'enable_per_process_and_thread_time_limit': True,
    'enable_per_process_and_thread_memory_limit': True
}

try:
    response = requests.post(url, json=payload, timeout=10)
    print("Status Code:", response.status_code)
    print("Response JSON:")
    import json
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print("Error:", e)
