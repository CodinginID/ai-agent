from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import requests
import subprocess

TOKEN = "8709090758:AAGupPXuwUDYubf3sAjNHchRHACMEsgyyaQ"

# --- CALL QWEN ---
def call_qwen(prompt):
    res = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "qwen",
            "prompt": prompt,
            "stream": False
        }
    )
    return res.json()["response"]

# --- EXECUTOR ---
def run_command(cmd):
    try:
        result = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
        return result.decode()
    except Exception as e:
        return str(e)

# --- HANDLER ---
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text

    # 1. parsing intent pakai AI
    prompt = f"""
    Convert this instruction into safe Linux commands.
    Only allow docker, git, ls, ps.
    Instruction: {user_text}
    Return only command.
    """

    command = call_qwen(prompt)

    # 2. simple validator
    if not any(cmd in command for cmd in ["docker", "git", "ls", "ps"]):
        await update.message.reply_text("❌ Command not allowed")
        return

    # 3. execute
    result = run_command(command)

    # 4. summary
    summary = call_qwen(f"Summarize this output:\n{result}")

    await update.message.reply_text(f"🧠 Command:\n{command}\n\n📊 Result:\n{summary}")

# --- RUN ---
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT, handle))

app.run_polling()
