import os

for f in ['.env.local', 'env.local']:
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8') as fp:
            for line in fp:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")

from google import genai
client = genai.Client(api_key=os.environ.get('GEMINI_API_KEY'))
try:
    models = list(client.models.list())
    flash_models = [m.name for m in models if 'flash' in m.name.lower()]
    print('Available Flash models:')
    for fm in flash_models:
        print(' ', fm)
except Exception as e:
    print('Error listing models:', type(e), e)
