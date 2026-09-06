"""
OpenAIPDF Telegram Bot Runner
Token: 8993850012:AAEkel2F0v3OKuJ0TvE6u6D3mRDNzthVMUA
Bot Username: @OpenAIPDF_bot
"""
import os
import sys
import time
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from bot import create_bot_application
from config import BOT_TOKEN, BOT_USERNAME

logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("Runner")


def ensure_single_instance():
    """Ensure no duplicate Python run_bot.py process is running to prevent Telegram 409 Conflict."""
    current_pid = os.getpid()
    parent_pid = os.getppid() if hasattr(os, "getppid") else None
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                pid = proc.info['pid']
                if pid == current_pid or pid == parent_pid:
                    continue
                name = (proc.info.get('name') or '').lower()
                if not name.startswith('python'):
                    continue
                cmdline = proc.info.get('cmdline') or []
                cmdline_str = " ".join(cmdline).lower()
                if "run_bot.py" in cmdline_str or "bot.py" in cmdline_str:
                    logger.warning(f"Found conflicting bot instance (PID {pid}). Terminating it...")
                    proc.kill()
                    logger.info(f"Terminated conflicting instance (PID {pid}).")
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Process check warning: {e}")


def start_health_check_server():
    """Start lightweight HTTP server for Render Free Web Service health checks."""
    port_str = os.getenv("PORT")
    if not port_str:
        return
    try:
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import threading

        port = int(port_str)

        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OpenAIPDF Bot is LIVE and running!\n")

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Render health check HTTP server running on port {port}")
    except Exception as e:
        logger.warning(f"Failed to start health check server: {e}")


def main():
    print("=" * 60)
    print("  🚀 OPENAIPDF TELEGRAM BOT SERVICE")
    print(f"  🤖 Bot Handle: @{BOT_USERNAME}")
    print(f"  🔑 Token Prefix: {BOT_TOKEN[:10]}...")
    print("=" * 60)
    
    ensure_single_instance()
    start_health_check_server()
    
    # Auto-retry loop in case of network disconnects
    max_restarts = 10
    restart_count = 0
    
    while restart_count < max_restarts:
        try:
            app = create_bot_application()
            logger.info("Application initialized successfully. Starting long polling...")
            print("\n✅ Bot is LIVE and actively polling Telegram updates!")
            print("💡 Open Telegram and search for @OpenAIPDF_bot or send /start.\n")
            print("Press Ctrl+C to stop the bot.\n")
            
            app.run_polling(drop_pending_updates=True)
            break
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped gracefully by user.")
            break
        except Exception as e:
            err_msg = str(e)
            if "Conflict" in err_msg:
                logger.error(f"Telegram 409 Conflict: Another instance is polling. Waiting 5s and reclaiming instance: {e}")
                ensure_single_instance()
            else:
                logger.error(f"Error in Telegram Bot: {e}", exc_info=True)
            restart_count += 1
            print(f"🔄 Reconnecting bot in 5 seconds (Attempt {restart_count}/{max_restarts})...")
            time.sleep(5)


if __name__ == "__main__":
    main()
