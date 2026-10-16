# pip install google-genai

from google import genai

API_KEY = "AQ.Ab8RN6JzpBKEvstDA9_cHtim6lWQftCGQn16BVj-lDY2gYbESQ"

try:
    client = genai.Client(api_key=API_KEY)

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents="Reply with only: API Key Working"
    )

    print("✅ Success")
    print(response.text)

except Exception as e:
    print("❌ Error")
    print(str(e))