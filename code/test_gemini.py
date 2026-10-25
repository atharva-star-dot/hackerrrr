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

# Test gemini-2.5-flash-lite
try:
    resp = client.models.generate_content(
        model='gemini-2.5-flash-lite',
        contents='Confirm function calling and vision support. Reply with OK.'
    )
    print('gemini-2.5-flash-lite response:', resp.text.strip())
except Exception as e:
    print('gemini-2.5-flash-lite error:', e)

# Test gemini-2.5-flash
try:
    resp = client.models.generate_content(
        model='gemini-2.5-flash',
        contents='Confirm function calling and vision support. Reply with OK.'
    )
    print('gemini-2.5-flash response:', resp.text.strip())
except Exception as e:
    print('gemini-2.5-flash error:', e)
