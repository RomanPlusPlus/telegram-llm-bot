# How to deploy:

## -1. Create a telegram bot and get the token

You can do this by talking with the official "BotFather" tool on Telegram: https://t.me/botfather

## 0. Get the telegram IDs of the allowed users 

For example, of your friends in telegram.

## 1. Create a VM, and SSH to it

For example, in Digital Ocean, Azure, etc.

You can also run the script locally. Useful for testing.

## 2. Clone the repository

```
git clone https://github.com/RomanPlusPlus/telegram-llm-bot.git
```

## 3. Create a tmux session

```
tmux new -s session_name
```

## 4. Install the dependencies with pip

cd to the dir where you cloned this and run in a terminal:

```
pip install -r requirements.txt

```

## 5. Specify the API keys and allowed users like this:

```
echo "export TELEGRAM_LLM_BOT_TOKEN='<your_token>'" >> ~/.bashrc

echo "export OPENAI_API_KEY='<your_token>'" >> ~/.bashrc

echo "export OPENAI_MODEL='<your_token>'" >> ~/.bashrc

echo "export ALLOWED_USER_IDS='some_id1,some_id2,some_id3'" >> ~/.bashrc

source ~/.bashrc
```

## 5. Run the main script

```
python3 main.py
```

To leave the script running even after you log out, press `Ctrl+b`, and then press `d`.

To return to the tmux session in the future, run `tmux attach -t session_name`.

