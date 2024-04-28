# How to deploy:

1. Create a VM, and SSH to it.

2. Clone the repository into it with "git clone"

3. Install the dependencies with pip

cd to the dir where you cloned this and run in a terminal:

```
pip install -r requirements.txt

```

4. Specify the API keys like this:

```
echo "export TELEGRAM_LLM_BOT_TOKEN='<your_token>'" >> ~/.bashrc

echo "export OPENAI_API_KEY='<your_token>'" >> ~/.bashrc

source ~/.bashrc
```

5. Run the main script in tmux

```
tmux new -s session_name

python3 main.py
```

To leave the script running even after you log out, press `Ctrl+b`, and then press `d`.

To return to the session in the future, run `tmux attach -t session_name`.

