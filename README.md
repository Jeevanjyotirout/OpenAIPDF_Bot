# OpenAIPDF Telegram Chatbot 🤖

An all-in-one AI PDF productivity chatbot for Telegram powered by [OpenAIPDF](https://openaipdf.com).
---

## ⚡ How to Keep the Bot Live (Never Need to Run It Again!)

You have two powerful options to keep the bot alive:

### Option 1: Automatic Windows Background Service (Recommended for Local PC)

We have created 1-click automation scripts inside this folder:

1. **Auto-Start on PC Boot (Run Once & Forget It):**
   - Double-click **`install_autostart_on_boot.bat`**.
   - This creates an invisible startup shortcut in Windows. Every time you turn on your laptop or log in, the bot starts silently in the background.
   - **No terminal window will open**, and it will run 24/7 as long as your computer is on!

2. **Start Silently in Background Right Now:**
   - Double-click **`start_bot_background.bat`**.
   - Launches the bot silently using `run_bot_silent.vbs` without keeping any Command Prompt window open.

3. **Check If Bot is Running:**
   - Double-click **`status_bot.bat`**.
   - Tells you whether the bot is currently active, displays its Process ID, and shows uptime.

4. **Stop the Bot Anytime:**
   - Double-click **`stop_bot.bat`**.

---

### Option 2: 24/7 Cloud Deployment (Runs Even When PC Is Turned Off)

If you want the bot running continuously even when your laptop is closed, asleep, or turned off:

#### Deploy to Railway (Free / Cheap 24/7 Cloud)
1. Push this folder to a GitHub repository (e.g. `openaipdf-telegram-bot`).
2. Go to [railway.app](https://railway.app) and click **New Project** → **Deploy from GitHub repo**.
3. Railway automatically detects `Procfile` and `requirements.txt`.
4. Add the environment variable in Railway dashboard:
   - `TELEGRAM_BOT_TOKEN = 8993850012:AAEkel2F0v3OKuJ0TvE6u6D3mRDNzthVMUA`
5. Click **Deploy**. The bot will run 24/7 in the cloud!

#### Deploy to Render
1. Go to [render.com](https://render.com) and create a **Background Worker**.
2. Connect your GitHub repository.
3. Set Build Command: `pip install -r requirements.txt`
4. Set Start Command: `python run_bot.py`
5. Add `TELEGRAM_BOT_TOKEN = 8993850012:AAEkel2F0v3OKuJ0TvE6u6D3mRDNzthVMUA` in Environment settings.

---

## 🚀 Features & Capabilities

The bot provides full local processing for all document workflows:

| Feature | Description | Supported Files |
|---|---|---|
| 🗜️ **Compress PDF** | Intelligent deflation, stream cleanup & image downsampling for size reduction | `.pdf` |
| 📝 **PDF to Word** | Convert PDF into fully editable Microsoft Word documents (`.docx`) | `.pdf` |
| 🔄 **Word to PDF** | Convert Microsoft Word documents into standard PDFs | `.docx`, `.doc` |
| 📑 **Merge PDFs** | Combine multiple uploaded PDFs into a single unified document | `.pdf` (2+) |
| ✂️ **Split PDF** | Extract custom page ranges (e.g. `1-3, 5`) or split all pages into a `.zip` archive | `.pdf` |
| 🖼️ **PDF to Images** | Render high-resolution JPG images of every page packaged into a `.zip` file | `.pdf` |
| 📸 **Images to PDF** | Convert one or multiple uploaded photos into a clean PDF document | `.jpg`, `.png`, `.webp` |
| 🔒 **Protect PDF** | Add AES-256 password encryption to lock opening & editing | `.pdf` |
| 🔓 **Unlock PDF** | Decrypt and remove password restrictions from protected documents | `.pdf` |
| 🔄 **Rotate PDF** | Rotate all document pages by 90°, 180°, or 270° | `.pdf` |
| 💧 **Add Watermark** | Stamp custom diagonal semi-transparent watermark text on every page | `.pdf` |
| 🤖 **AI Summarize** | Extract text, compute word/char metrics, reading time, and executive summary | `.pdf` |
| ℹ️ **Document Info** | Inspect page dimensions, author, creator, page counts & encryption status | `.pdf` |

---

## 📱 User Commands

- `/start` — Launch the welcome menu and see feature buttons.
- `/help` — Detailed feature and file format guide.
- `/tools` — Quick interactive tool selector.
- `/merge` — Activate multi-file merge mode.
- `/cancel` — Clear the current session, active files, and pending inputs.

---

## 🛡️ Reliability & Fixes Implemented

1. **True Binary File Streaming (`make_input_file`)**:
   - Fixed an issue where passing file path strings to Telegram caused files to be sent as tiny text files containing the file path (e.g., 89 bytes).
   - All files and images are now streamed as complete binary documents into memory, ensuring valid PDF headers and exact byte lengths.
2. **Single-Instance Conflict Prevention**:
   - `run_bot.py` uses `psutil` to verify no duplicate bot instances are running simultaneously.
   - Prevents Telegram `409 Conflict: terminated by other getUpdates request`.
3. **Auto-Reconnect Loop**:
   - Automatically recovers and reconnects if internet connectivity drops temporarily.
4. **Temporary File Cleanup**:
   - Working files in `temp_files/` are safely deleted after transmission, preventing memory or disk leaks.
