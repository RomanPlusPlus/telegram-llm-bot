import os
from openai import OpenAI  # pip install openai


def build_client():
    key = os.environ["OPENAI_API_KEY"]
    client = OpenAI(api_key=key)
    return client


def build_model_handle():
    handle = os.environ["OPENAI_MODEL"]  # e.g. "gpt-4o"
    return handle


if os.environ["AI_PROVIDER"] == "openai":
    MODEL = build_model_handle()
    CLIENT = build_client()
    print(f"Using OpenAI model: {MODEL}")
    print(f"Using OpenAI client: {CLIENT}")
else:
    MODEL = None
    CLIENT = None


def ask_open_ai(messages, max_length):
    try:
        completion = CLIENT.chat.completions.create(
            model=MODEL, messages=messages, max_tokens=max_length,
        )
        answer = completion.choices[0].message.content
        print(f"OpenAI response: {answer}")
    except Exception as e:
        msg = f"Error while sending to OpenAI: {e}"
        print(msg)
        answer = msg
    return answer
