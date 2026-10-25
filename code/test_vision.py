import os
from google import genai
from google.genai import types

for f in ['.env.local', 'env.local']:
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8') as fp:
            for line in fp:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))

with open('dataset/evidence/images/account_admin_console_20260926.png', 'rb') as fp:
    img_bytes = fp.read()

prompt = "Extract the customer details, account ID, and status shown in this console screenshot. Return a JSON object with resource_id, email, full_name, and status."

resp = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=[
        types.Part.from_bytes(data=img_bytes, mime_type='image/png'),
        types.Part.from_text(text=prompt)
    ]
)
print('Vision output:')
print(resp.text)
