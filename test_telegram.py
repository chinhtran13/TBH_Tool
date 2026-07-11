"""Quick test to diagnose Telegram API issues."""
import json
import urllib.request
import urllib.parse
import sys
import io
from pathlib import Path

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

CONFIG_PATH = Path(__file__).with_name("inventory_bag_monitor_config.json")

config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
bot_token = config.get("telegram_bot_token", "").strip()
chat_id = config.get("telegram_chat_id", "").strip()

print(f"Bot Token: {bot_token[:10]}...{bot_token[-5:]}" if len(bot_token) > 15 else f"Bot Token: '{bot_token}'")
print(f"Chat ID:   '{chat_id}'")

if not bot_token or not chat_id:
    print("\n[ERROR] Bot Token or Chat ID is empty.")
    exit(1)

url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
data = urllib.parse.urlencode({
    "chat_id": chat_id,
    "text": "Test message from debug script",
}).encode("utf-8")

print(f"\nSending request to: {url[:60]}...")

try:
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        print(f"Status: {resp.status}")
        print(f"Response: {body}")
        print("\nSUCCESS!")
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8")
    print(f"\nHTTP Error {e.code}: {e.reason}")
    print(f"Response: {body}")
except urllib.error.URLError as e:
    print(f"\nURL Error: {e.reason}")
    print("Possible SSL certificate or network issue.")
except Exception as e:
    print(f"\nError: {type(e).__name__}: {e}")
