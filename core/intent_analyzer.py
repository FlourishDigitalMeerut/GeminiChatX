from groq import Groq
from config.settings import GROQ_API_KEY

def analyze_intent(user_input: str) -> str:
    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            messages=[{
                "role": "system",
                "content": "You are an intent classification system. Respond with only the most specific intent in 2-4 words."
            },
            {"role": "user", "content": user_input}],
            model="LLaMA-3.1-8B-Instant",
            temperature=0.1
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error in intent analysis -> {e}")
        return "unknown_intent"