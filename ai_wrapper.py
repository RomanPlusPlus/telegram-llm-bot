import os
from openai import OpenAI  # pip install openai


key = os.environ["OPENAI_API_KEY"]

client = OpenAI(api_key=key)


def ask_gpt_single_message(prompt, sys_msg, max_length):
    print("Asking GPT...")

    try:
        completion = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {
                    "role": "system",
                    "content": sys_msg,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            max_tokens=max_length,
        )
        res = str(completion.choices[0].message.content)
        
    except Exception as e:
        res = f"Error: {e}"

    return res

