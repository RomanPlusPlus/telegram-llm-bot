import os
from openai import OpenAI  # pip install openai
import time
from functools import wraps
from collections import deque

#key = os.environ["OPENAI_API_KEY"]
#client = OpenAI(api_key=key)

MAX_CALLS_PER_PERIOD = 10000
PERIOD_S = 60 # 1 min


def build_client():
    key = os.environ["OPENAI_API_KEY"]
    client = OpenAI(api_key=key)
    return client


def build_model_handle():
    handle = os.environ["OPENAI_MODEL"]  # e.g. "gpt-4o"
    return handle


MODEL = build_model_handle()
CLIENT = build_client()

print(f"Using OpenAI model: {MODEL}")
print(f"Using OpenAI client: {CLIENT}")




class RateLimitExceededError(Exception):
    pass

def rate_limit(max_calls, period, stop_on_limit=True):
    calls = deque()
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            
            # Remove calls older than the period
            while calls and calls[0] <= now - period:
                calls.popleft()
            
            if len(calls) >= max_calls:
                if stop_on_limit:
                    raise RateLimitExceededError(f"Rate limit of {max_calls} calls per {period} seconds exceeded")
                else:
                    sleep_time = calls[0] - (now - period)
                    time.sleep(sleep_time)
            
            result = func(*args, **kwargs)
            calls.append(now)
            
            # Calculate and print the current rate
            current_rate = len(calls) / period * 60  # Convert to calls per min
            print(f"Current rate: {current_rate:.2f} calls/min")
            
            return result
        return wrapper
    return decorator

@rate_limit(max_calls=MAX_CALLS_PER_PERIOD, period=PERIOD_S, stop_on_limit=True)
def ask_gpt_multi_message(messages, max_length):
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


"""
def ask_gpt_multi_message(messages, max_length):

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
"""


def ask_gpt_single_message(prompt, sys_msg, max_length):
    print("Asking GPT...")

    try:
        completion = CLIENT.chat.completions.create(
            model=MODEL,
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

