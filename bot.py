import os
import sys
import time
import logging
import asyncio
import shutil

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from pathlib import Path
from typing import Dict, Any, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from config import BOT_TOKEN, TEMP_DIR, WEB_APP_URL, MAX_FILE_SIZE_BYTES
import pdf_tools

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("OpenAIPDF_Bot")


def make_input_file(filepath: str, filename: str) -> InputFile:
    """Safely open and read full binary file content into memory for Telegram transmission."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found on disk: {filepath}")
    with open(filepath, "rb") as f:
        return InputFile(f.read(), filename=filename)


# In-memory user state tracker
user_sessions: Dict[int, Dict[str, Any]] = {}
user_locks: Dict[int, asyncio.Lock] = {}


def get_user_lock(user_id: int) -> asyncio.Lock:
    """Retrieve or initialize a per-user asyncio.Lock to serialize concurrent uploads."""
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()
    return user_locks[user_id]


def get_session(user_id: int) -> Dict[str, Any]:
    """Retrieve or initialize a user session."""
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "active_pdf": None,
            "active_filename": None,
            "merge_queue": [],
            "awaiting": None,
            "img_queue": [],
            "mode": "idle",
            "last_upload_time": 0.0
        }
    return user_sessions[user_id]


def cleanup_session_files(user_id: int):
    """Clean up user temporary files from disk."""
    session = get_session(user_id)
    files_to_remove = []
    if session.get("active_pdf"):
        files_to_remove.append(session["active_pdf"])
    for item in session.get("merge_queue", []):
        files_to_remove.append(item.get("path"))
    for p in session.get("img_queue", []):
        files_to_remove.append(p)
        
    for path_str in files_to_remove:
        try:
            if path_str and os.path.exists(path_str):
                os.remove(path_str)
        except Exception:
            pass
            
    session["active_pdf"] = None
    session["active_filename"] = None
    session["merge_queue"] = []
    session["awaiting"] = None
    session["img_queue"] = []
    session["mode"] = "idle"
    session["last_upload_time"] = 0.0


# =========================================================================
# KEYBOARD BUILDERS
# =========================================================================

def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu displayed on /start or /help."""
    keyboard = [
        [
            InlineKeyboardButton("📑 Merge PDFs", callback_data="cmd_merge_start"),
            InlineKeyboardButton("🗜️ Compress PDF", callback_data="cmd_prompt_upload")
        ],
        [
            InlineKeyboardButton("📝 PDF to Word", callback_data="cmd_prompt_upload"),
            InlineKeyboardButton("🖼️ Images to PDF", callback_data="cmd_img2pdf_start")
        ],
        [
            InlineKeyboardButton("✂️ Split PDF", callback_data="cmd_prompt_upload"),
            InlineKeyboardButton("🔒 Protect / Unlock", callback_data="cmd_prompt_upload")
        ],
        [
            InlineKeyboardButton("🤖 AI Summarize", callback_data="cmd_prompt_upload"),
            InlineKeyboardButton("💧 Watermark", callback_data="cmd_prompt_upload")
        ],
        [
            InlineKeyboardButton("🌐 Open Web App (50+ Tools)", url=WEB_APP_URL)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_pdf_actions_keyboard(filename: str) -> InlineKeyboardMarkup:
    """Action keypad shown whenever a PDF document is uploaded."""
    keyboard = [
        [
            InlineKeyboardButton("🗜️ Compress Size", callback_data="act_compress"),
            InlineKeyboardButton("📝 Convert to Word", callback_data="act_to_docx")
        ],
        [
            InlineKeyboardButton("🖼️ Extract Images (ZIP)", callback_data="act_to_images"),
            InlineKeyboardButton("✂️ Split Pages", callback_data="act_split")
        ],
        [
            InlineKeyboardButton("🤖 AI Summary & Stats", callback_data="act_summarize"),
            InlineKeyboardButton("ℹ️ PDF Info", callback_data="act_info")
        ],
        [
            InlineKeyboardButton("🔒 Password Protect", callback_data="act_protect"),
            InlineKeyboardButton("🔓 Unlock PDF", callback_data="act_unlock")
        ],
        [
            InlineKeyboardButton("🔄 Rotate 90° Clockwise", callback_data="act_rotate"),
            InlineKeyboardButton("💧 Add Watermark", callback_data="act_watermark")
        ],
        [
            InlineKeyboardButton("➕ Add to Merge Queue", callback_data="act_add_merge"),
            InlineKeyboardButton("❌ Cancel", callback_data="act_cancel")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# =========================================================================
# COMMAND HANDLERS
# =========================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    greeting = (
        f"👋 **Welcome to OpenAIPDF Bot, {user.first_name}!**\n\n"
        f"I am your all-in-one AI document assistant powered by [OpenAIPDF]({WEB_APP_URL}).\n\n"
        "⚡ **Quick Start:**\n"
        "• **Simply send me any PDF** to compress, convert to Word, split, protect, or summarize it!\n"
        "• Send **multiple photos** to compile them into a single PDF.\n"
        "• Send **/merge** to combine multiple PDF documents.\n"
        "• Send **/cancel** anytime to clear your active session.\n\n"
        "Choose a feature below or drop a file directly into our chat:"
    )
    await update.message.reply_text(
        greeting,
        reply_markup=build_main_menu_keyboard(),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "🛠️ **OpenAIPDF Bot Command Guide**\n\n"
        "• **/start** — Open the main menu & options\n"
        "• **/tools** — Browse all available PDF utilities\n"
        "• **/merge** — Enter multi-file merge mode\n"
        "• **/cancel** — Reset current operation and clear files\n"
        "• **/info** — View bot and system status\n\n"
        "📂 **Supported Files:**\n"
        "• **PDF Documents** (`.pdf`) — Full suite of editing & AI operations\n"
        "• **Word Documents** (`.docx`) — Convert to PDF format\n"
        "• **Images** (`.jpg`, `.png`) — Combine multiple photos into PDF\n\n"
        "🔒 *All uploaded files are processed securely in temporary sandbox storage and automatically cleared.*"
    )
    await update.message.reply_text(
        help_text,
        reply_markup=build_main_menu_keyboard(),
        parse_mode="Markdown"
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command."""
    user_id = update.effective_user.id
    cleanup_session_files(user_id)
    await update.message.reply_text(
        "🧹 **Session cleared!** All temporary files and pending actions have been reset.\n"
        "Send me a new file whenever you're ready.",
        reply_markup=build_main_menu_keyboard(),
        parse_mode="Markdown"
    )


async def merge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /merge command."""
    user_id = update.effective_user.id
    async with get_user_lock(user_id):
        session = get_session(user_id)
        session["merge_queue"] = []
        session["mode"] = "merge"
    
    keyboard = [
        [InlineKeyboardButton("🏁 Done & Merge Now", callback_data="act_execute_merge")],
        [InlineKeyboardButton("❌ Cancel Merge", callback_data="act_cancel")]
    ]
    await update.message.reply_text(
        "📑 **Merge Mode Activated!**\n\n"
        "You can now send **2, 3, or more PDF files continuously or all at once**.\n"
        "When all files are uploaded, tap **Done & Merge Now** below.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# =========================================================================
# FILE HANDLERS
# =========================================================================

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming document attachments (PDF, DOCX, etc.)."""
    message = update.message
    doc = message.document
    user_id = update.effective_user.id
    
    if doc.file_size > MAX_FILE_SIZE_BYTES:
        await message.reply_text(
            f"⚠️ File is too large ({pdf_tools.format_size(doc.file_size)}). "
            f"Telegram bot maximum file size is {MAX_FILE_SIZE_BYTES // (1024*1024)} MB."
        )
        return
        
    filename = doc.file_name or "document.pdf"
    ext = os.path.splitext(filename)[1].lower()
    
    # Download file to temp folder
    file_obj = await context.bot.get_file(doc.file_id)
    safe_name = f"u{user_id}_{doc.file_unique_id}_{filename}"
    local_path = str(TEMP_DIR / safe_name)
    await file_obj.download_to_drive(local_path)
    
    # Acquire lock for this user to serialize concurrent/multi-file uploads
    async with get_user_lock(user_id):
        session = get_session(user_id)
        now = time.time()
        
        # 1. Handle PDF
        if ext == ".pdf":
            file_entry = {
                "path": local_path,
                "name": filename,
                "size": doc.file_size
            }
            
            # Case A: User is in explicit Merge mode OR already has 1+ items in merge_queue
            if session.get("mode") == "merge" or (session.get("merge_queue") and len(session["merge_queue"]) > 0):
                session["merge_queue"].append(file_entry)
                session["active_pdf"] = local_path
                session["active_filename"] = filename
                session["last_upload_time"] = now
                count = len(session["merge_queue"])
                
                file_list_str = "\n".join([
                    f"{i+1}. 📄 `{item['name']}` ({pdf_tools.format_size(item['size'])})"
                    for i, item in enumerate(session["merge_queue"][-8:])
                ])
                if count > 8:
                    file_list_str = f"*(... and {count-8} earlier files)*\n" + file_list_str

                keyboard = [
                    [InlineKeyboardButton(f"🏁 Merge ({count} files) Now", callback_data="act_execute_merge")],
                    [InlineKeyboardButton("➕ Add More PDFs", callback_data="cmd_prompt_upload")],
                    [InlineKeyboardButton("❌ Clear / Cancel", callback_data="act_cancel")]
                ]
                await message.reply_text(
                    f"✅ **Added to Merge Queue!** ({count} files ready)\n\n"
                    f"{file_list_str}\n\n"
                    "Send more PDFs continuously, or tap **Merge Now** when ready:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                return

            # Case B: Multi-file / consecutive upload detection (within 75s of previous PDF)
            time_diff = now - session.get("last_upload_time", 0.0)
            if session.get("active_pdf") and os.path.exists(session["active_pdf"]) and time_diff < 75.0:
                prev_path = session["active_pdf"]
                prev_name = session.get("active_filename") or "document.pdf"
                prev_size = os.path.getsize(prev_path) if os.path.exists(prev_path) else 0
                
                session["merge_queue"] = [
                    {"path": prev_path, "name": prev_name, "size": prev_size},
                    file_entry
                ]
                session["mode"] = "merge"
                session["active_pdf"] = local_path
                session["active_filename"] = filename
                session["last_upload_time"] = now
                
                count = len(session["merge_queue"])
                file_list_str = "\n".join([
                    f"{i+1}. 📄 `{item['name']}` ({pdf_tools.format_size(item['size'])})"
                    for i, item in enumerate(session["merge_queue"])
                ])
                keyboard = [
                    [InlineKeyboardButton(f"🏁 Merge ({count} files) Now", callback_data="act_execute_merge")],
                    [InlineKeyboardButton("➕ Add More PDFs", callback_data="cmd_prompt_upload")],
                    [InlineKeyboardButton(f"⚙️ Work with `{filename[:15]}` Only", callback_data="act_switch_single")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="act_cancel")]
                ]
                await message.reply_text(
                    f"📥 **Multi-PDF Upload Detected! ({count} files queued)**\n\n"
                    f"{file_list_str}\n\n"
                    "You can keep sending more PDFs continuously, or tap **Merge Now** below:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
                return

            # Case C: First single PDF upload
            session["active_pdf"] = local_path
            session["active_filename"] = filename
            session["merge_queue"] = []
            session["awaiting"] = None
            session["mode"] = "idle"
            session["last_upload_time"] = now
            
            info = pdf_tools.get_pdf_metadata(local_path)
            caption = (
                f"📄 **PDF Document Ready:** `{filename}`\n"
                f"📊 **Pages:** {info['page_count']} | **Size:** {info['file_size']}\n\n"
                "Select a tool below, or **simply send another PDF** to merge them:"
            )
            await message.reply_text(
                caption,
                reply_markup=build_pdf_actions_keyboard(filename),
                parse_mode="Markdown"
            )
            return
            
        # 2. Handle DOCX -> PDF conversion
        elif ext in (".docx", ".doc"):
            conv_msg = await message.reply_text("🔄 Converting Word document to PDF format...")
            out_pdf = local_path + ".pdf"
            try:
                res = pdf_tools.docx_to_pdf(local_path, out_pdf)
                await message.reply_document(
                    document=make_input_file(out_pdf, filename=filename.replace(ext, ".pdf")),
                    caption=f"✅ Converted Word document to PDF ({res['output_size']})!"
                )
                await conv_msg.delete()
            except Exception as e:
                await conv_msg.edit_text(f"❌ Conversion failed: {str(e)}")
            finally:
                if os.path.exists(out_pdf):
                    try: os.remove(out_pdf)
                    except: pass
                if os.path.exists(local_path):
                    try: os.remove(local_path)
                    except: pass
        else:
            await message.reply_text(
                f"ℹ️ Received `{filename}`.\n"
                "Please upload a `.pdf` file, `.docx` document, or send images to process.",
                parse_mode="Markdown"
            )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming photos to compile into PDF."""
    message = update.message
    user_id = update.effective_user.id
    session = get_session(user_id)
    
    # Get highest resolution photo
    photo = message.photo[-1]
    file_obj = await context.bot.get_file(photo.file_id)
    
    local_path = str(TEMP_DIR / f"u{user_id}_{photo.file_unique_id}.jpg")
    await file_obj.download_to_drive(local_path)
    
    session["img_queue"].append(local_path)
    count = len(session["img_queue"])
    
    keyboard = [
        [InlineKeyboardButton(f"📄 Create PDF from {count} Image(s)", callback_data="act_execute_img2pdf")],
        [InlineKeyboardButton("➕ Add More Photos", callback_data="cmd_prompt_upload")],
        [InlineKeyboardButton("❌ Cancel", callback_data="act_cancel")]
    ]
    await message.reply_text(
        f"📸 **Image received!** ({count} image{'s' if count > 1 else ''} queued)\n"
        "Send more photos or tap below to compile them into a single PDF document:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# =========================================================================
# CALLBACK QUERY (BUTTON) HANDLERS
# =========================================================================

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle interactive inline keyboard taps."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    session = get_session(user_id)
    active_pdf = session.get("active_pdf")
    active_name = session.get("active_filename") or "document.pdf"

    # --- MAIN COMMAND SHORTCUTS ---
    if data == "cmd_prompt_upload":
        await query.message.reply_text(
            "📤 **Ready!** Please send or drag-and-drop your PDF document into the chat.",
            parse_mode="Markdown"
        )
        return

    if data == "cmd_merge_start":
        session["merge_queue"] = []
        session["mode"] = "merge"
        keyboard = [
            [InlineKeyboardButton("🏁 Done & Merge Now", callback_data="act_execute_merge")],
            [InlineKeyboardButton("❌ Cancel Merge", callback_data="act_cancel")]
        ]
        await query.message.reply_text(
            "📑 **Merge Mode Activated!**\n\n"
            "You can now send **2, 3, or more PDF files continuously or all at once**.\n"
            "When all files are uploaded, tap **Done & Merge Now** below.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    if data == "act_switch_single":
        if not active_pdf or not os.path.exists(active_pdf):
            await query.message.reply_text("⚠️ No active file found to process.")
            return
        session["mode"] = "idle"
        session["merge_queue"] = []
        info = pdf_tools.get_pdf_metadata(active_pdf)
        caption = (
            f"📄 **Working with Single File:** `{active_name}`\n"
            f"📊 **Pages:** {info['page_count']} | **Size:** {info['file_size']}\n\n"
            "Select what you would like to do with this document:"
        )
        await query.message.reply_text(
            caption,
            reply_markup=build_pdf_actions_keyboard(active_name),
            parse_mode="Markdown"
        )
        return

    if data == "cmd_img2pdf_start":
        session["img_queue"] = []
        await query.message.reply_text(
            "📸 **Images to PDF:** Send one or more photos/images into the chat to compile them into a PDF.",
            parse_mode="Markdown"
        )
        return

    if data == "act_cancel":
        cleanup_session_files(user_id)
        await query.message.edit_text(
            "❌ Action cancelled and temporary files cleared. Send a new file whenever you're ready!"
        )
        return

    # --- EXECUTE MULTI-IMAGE TO PDF ---
    if data == "act_execute_img2pdf":
        img_queue = session.get("img_queue", [])
        if not img_queue:
            await query.message.reply_text("⚠️ No images in queue. Please send some photos first.")
            return
            
        status_msg = await query.message.reply_text("⚙️ Compiling images into PDF document...")
        out_pdf = str(TEMP_DIR / f"u{user_id}_compiled_images.pdf")
        try:
            res = pdf_tools.images_to_pdf(img_queue, out_pdf)
            await query.message.reply_document(
                document=make_input_file(out_pdf, filename="images_document.pdf"),
                caption=f"✅ Created PDF from {res['images_count']} images ({res['output_size']})!"
            )
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ Failed to create PDF from images: {str(e)}")
        finally:
            cleanup_session_files(user_id)
        return

    # --- EXECUTE MERGE ---
    if data == "act_execute_merge":
        queue = session.get("merge_queue", [])
        if len(queue) < 2:
            await query.message.reply_text("⚠️ Please send at least 2 PDF files to merge.")
            return
            
        status_msg = await query.message.reply_text(f"⚙️ Merging {len(queue)} PDF documents...")
        out_pdf = str(TEMP_DIR / f"u{user_id}_merged.pdf")
        try:
            paths = [item["path"] for item in queue]
            res = pdf_tools.merge_pdfs(paths, out_pdf)
            await query.message.reply_document(
                document=make_input_file(out_pdf, filename="merged_documents.pdf"),
                caption=f"✅ Successfully merged {res['merged_count']} PDFs ({res['total_pages']} total pages, {res['output_size']})!"
            )
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ Merge failed: {str(e)}")
        finally:
            cleanup_session_files(user_id)
        return

    # --- OPERATIONS REQUIRING ACTIVE PDF ---
    if not active_pdf or not os.path.exists(active_pdf):
        await query.message.reply_text(
            "⚠️ No active document found. Please send your PDF document first.",
            reply_markup=build_main_menu_keyboard()
        )
        return

    # 1. COMPRESS
    if data == "act_compress":
        status_msg = await query.message.reply_text("🗜️ Optimizing and compressing PDF...")
        out_pdf = active_pdf.replace(".pdf", "_compressed.pdf")
        try:
            res = pdf_tools.compress_pdf(active_pdf, out_pdf)
            await query.message.reply_document(
                document=make_input_file(out_pdf, filename=active_name.replace(".pdf", "_compressed.pdf")),
                caption=(
                    f"✅ **PDF Compressed Successfully!**\n"
                    f"• Original Size: {res['original_size']}\n"
                    f"• New Size: {res['compressed_size']}\n"
                    f"• Space Saved: **{res['reduction_pct']}**"
                ),
                parse_mode="Markdown"
            )
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ Compression failed: {str(e)}")
        finally:
            if os.path.exists(out_pdf):
                try: os.remove(out_pdf)
                except: pass

    # 2. TO DOCX
    elif data == "act_to_docx":
        status_msg = await query.message.reply_text("📝 Converting PDF to Word (.docx)... this may take a moment.")
        out_docx = active_pdf.replace(".pdf", ".docx")
        try:
            res = pdf_tools.pdf_to_docx(active_pdf, out_docx)
            await query.message.reply_document(
                document=make_input_file(out_docx, filename=active_name.replace(".pdf", ".docx")),
                caption=f"✅ Converted `{active_name}` to editable Word document ({res['output_size']})!",
                parse_mode="Markdown"
            )
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ PDF to Word conversion failed: {str(e)}")
        finally:
            if os.path.exists(out_docx):
                try: os.remove(out_docx)
                except: pass

    # 3. TO IMAGES (ZIP)
    elif data == "act_to_images":
        status_msg = await query.message.reply_text("🖼️ Rendering PDF pages to high-res JPG images...")
        out_zip = active_pdf.replace(".pdf", "_images.zip")
        try:
            zip_path, preview_img = pdf_tools.pdf_to_images(active_pdf, out_zip, dpi=150)
            if preview_img and os.path.exists(preview_img):
                await query.message.reply_photo(
                    photo=make_input_file(preview_img, filename="preview.jpg"),
                    caption="🔎 Page 1 Preview:"
                )
                try: os.remove(preview_img)
                except: pass
            await query.message.reply_document(
                document=make_input_file(zip_path, filename=active_name.replace(".pdf", "_images.zip")),
                caption=f"✅ Exported all pages as JPG images ({pdf_tools.format_size(os.path.getsize(zip_path))})!"
            )
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ PDF to Images conversion failed: {str(e)}")
        finally:
            if os.path.exists(out_zip):
                try: os.remove(out_zip)
                except: pass

    # 4. ROTATE 90°
    elif data == "act_rotate":
        status_msg = await query.message.reply_text("🔄 Rotating all pages by 90°...")
        out_pdf = active_pdf.replace(".pdf", "_rotated.pdf")
        try:
            res = pdf_tools.rotate_pdf(active_pdf, out_pdf, degrees=90)
            await query.message.reply_document(
                document=make_input_file(out_pdf, filename=active_name.replace(".pdf", "_rotated.pdf")),
                caption="✅ Rotated all pages 90° clockwise!"
            )
            # Update active file to the rotated version
            session["active_pdf"] = out_pdf
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ Rotation failed: {str(e)}")

    # 5. AI SUMMARIZE
    elif data == "act_summarize":
        status_msg = await query.message.reply_text("🤖 Analyzing document content with AI...")
        try:
            res = pdf_tools.summarize_pdf(active_pdf)
            summary_msg = (
                f"📊 **AI Document Insights:** `{active_name}`\n\n"
                f"• **Pages:** {res['pages']}\n"
                f"• **Word Count:** {res['word_count']:,} words\n"
                f"• **Character Count:** {res['char_count']:,} chars\n"
                f"• **Est. Reading Time:** ~{res['est_reading_time_min']} min\n\n"
                f"📝 **Executive Summary:**\n"
                f"_{res['summary']}_"
            )
            await status_msg.edit_text(summary_msg, parse_mode="Markdown")
        except Exception as e:
            await status_msg.edit_text(f"❌ Summarization failed: {str(e)}")

    # 6. INFO
    elif data == "act_info":
        info = pdf_tools.get_pdf_metadata(active_pdf)
        dim_str = ""
        if info.get("pages_info"):
            dim_str = "\n".join([f"• Page {p['page']}: {p['width']} x {p['height']} pt" for p in info["pages_info"]])
        info_msg = (
            f"ℹ️ **Document Metadata:** `{active_name}`\n\n"
            f"• **Title:** {info['title']}\n"
            f"• **Author:** {info['author']}\n"
            f"• **Page Count:** {info['page_count']}\n"
            f"• **File Size:** {info['file_size']}\n"
            f"• **Password Protected:** {'Yes 🔒' if info['is_encrypted'] else 'No 🔓'}\n\n"
            f"📐 **Page Geometry:**\n{dim_str}"
        )
        await query.message.reply_text(info_msg, parse_mode="Markdown")

    # 7. ADD TO MERGE
    elif data == "act_add_merge":
        session["mode"] = "merge"
        if "merge_queue" not in session or not session["merge_queue"]:
            session["merge_queue"] = []
        if active_pdf and os.path.exists(active_pdf):
            if not any(item["path"] == active_pdf for item in session["merge_queue"]):
                session["merge_queue"].append({
                    "path": active_pdf,
                    "name": active_name,
                    "size": os.path.getsize(active_pdf)
                })
        count = len(session["merge_queue"])
        keyboard = [
            [InlineKeyboardButton(f"🏁 Merge ({count} files) Now", callback_data="act_execute_merge")],
            [InlineKeyboardButton("➕ Add More PDFs", callback_data="cmd_prompt_upload")],
            [InlineKeyboardButton("❌ Cancel", callback_data="act_cancel")]
        ]
        await query.message.reply_text(
            f"✅ **Added `{active_name}` to merge queue!** ({count} files queued)\n\n"
            "You can now send **more PDFs continuously or all at once**.\n"
            "When ready, tap **Merge Now** below:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    # 8. SPLIT PROMPT
    elif data == "act_split":
        session["awaiting"] = "split_range"
        keyboard = [
            [InlineKeyboardButton("✂️ Split Each Page to ZIP", callback_data="act_split_all")],
            [InlineKeyboardButton("❌ Cancel", callback_data="act_cancel")]
        ]
        await query.message.reply_text(
            "✂️ **Split PDF:**\n\n"
            "Please type the page range you want to extract (e.g. `1-3`, `2, 4, 6`), "
            "or tap **Split Each Page to ZIP** below:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif data == "act_split_all":
        status_msg = await query.message.reply_text("✂️ Splitting each page into individual PDFs...")
        out_zip = active_pdf.replace(".pdf", "_pages.zip")
        try:
            res = pdf_tools.split_pdf(active_pdf, out_zip, page_range_str="all")
            await query.message.reply_document(
                document=make_input_file(out_zip, filename=active_name.replace(".pdf", "_pages.zip")),
                caption=f"✅ Split {res['page_count']} pages into individual PDFs ({pdf_tools.format_size(os.path.getsize(out_zip))})!"
            )
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ Split failed: {str(e)}")
        finally:
            if os.path.exists(out_zip):
                try: os.remove(out_zip)
                except: pass

    # 9. PROTECT PROMPT
    elif data == "act_protect":
        session["awaiting"] = "protect_pw"
        await query.message.reply_text(
            "🔒 **Protect PDF:**\n\n"
            "Please send the password you would like to set for this document in your next reply:",
            parse_mode="Markdown"
        )

    # 10. UNLOCK PROMPT
    elif data == "act_unlock":
        session["awaiting"] = "unlock_pw"
        await query.message.reply_text(
            "🔓 **Unlock PDF:**\n\n"
            "Please send the existing document password in your next reply to remove encryption:",
            parse_mode="Markdown"
        )

    # 11. WATERMARK PROMPT
    elif data == "act_watermark":
        session["awaiting"] = "watermark_text"
        await query.message.reply_text(
            "💧 **Add Watermark:**\n\n"
            "Please send the text you want stamped diagonally across each page (e.g. `CONFIDENTIAL`, `DRAFT`, `COPY`):",
            parse_mode="Markdown"
        )


# =========================================================================
# TEXT PROMPT HANDLERS (AWAITING USER INPUT)
# =========================================================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text responses when awaiting user parameters (password, ranges, watermark)."""
    user_id = update.effective_user.id
    session = get_session(user_id)
    awaiting = session.get("awaiting")
    text = update.message.text.strip()
    active_pdf = session.get("active_pdf")
    active_name = session.get("active_filename") or "document.pdf"

    if not awaiting or not active_pdf or not os.path.exists(active_pdf):
        # Default conversational reply
        await update.message.reply_text(
            "📄 Send me any PDF, Word document, or image to start processing!\n"
            "Or type **/help** to see all available commands.",
            reply_markup=build_main_menu_keyboard(),
            parse_mode="Markdown"
        )
        return

    # 1. PROTECT WITH PASSWORD
    if awaiting == "protect_pw":
        session["awaiting"] = None
        status_msg = await update.message.reply_text("🔒 Encrypting PDF with AES-256 password...")
        out_pdf = active_pdf.replace(".pdf", "_protected.pdf")
        try:
            pdf_tools.protect_pdf(active_pdf, out_pdf, password=text)
            await update.message.reply_document(
                document=make_input_file(out_pdf, filename=active_name.replace(".pdf", "_protected.pdf")),
                caption=f"✅ **Password protection added!**\nPassword: `{text}`",
                parse_mode="Markdown"
            )
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ Encryption failed: {str(e)}")
        finally:
            if os.path.exists(out_pdf):
                try: os.remove(out_pdf)
                except: pass

    # 2. UNLOCK WITH PASSWORD
    elif awaiting == "unlock_pw":
        session["awaiting"] = None
        status_msg = await update.message.reply_text("🔓 Verifying password and removing restrictions...")
        out_pdf = active_pdf.replace(".pdf", "_unlocked.pdf")
        try:
            pdf_tools.unlock_pdf(active_pdf, out_pdf, password=text)
            await update.message.reply_document(
                document=make_input_file(out_pdf, filename=active_name.replace(".pdf", "_unlocked.pdf")),
                caption="✅ **PDF Unlocked Successfully!** Password restrictions removed.",
                parse_mode="Markdown"
            )
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ Unlock failed: {str(e)}")
        finally:
            if os.path.exists(out_pdf):
                try: os.remove(out_pdf)
                except: pass

    # 3. SPLIT WITH PAGE RANGE
    elif awaiting == "split_range":
        session["awaiting"] = None
        status_msg = await update.message.reply_text(f"✂️ Extracting pages `{text}`...")
        out_pdf = active_pdf.replace(".pdf", "_extracted.pdf")
        try:
            res = pdf_tools.split_pdf(active_pdf, out_pdf, page_range_str=text)
            if res.get("mode") == "all_pages_zip":
                await update.message.reply_document(
                    document=make_input_file(res["output_path"], filename=active_name.replace(".pdf", "_pages.zip")),
                    caption=f"✅ Split {res['page_count']} pages into zip archive!"
                )
            else:
                await update.message.reply_document(
                    document=make_input_file(out_pdf, filename=active_name.replace(".pdf", "_extracted.pdf")),
                    caption=f"✅ Extracted {res['extracted_pages']} pages according to range `{text}`!"
                )
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ Page extraction failed: {str(e)}")
        finally:
            if os.path.exists(out_pdf):
                try: os.remove(out_pdf)
                except: pass

    # 4. WATERMARK TEXT
    elif awaiting == "watermark_text":
        session["awaiting"] = None
        status_msg = await update.message.reply_text(f"💧 Stamping watermark `{text}`...")
        out_pdf = active_pdf.replace(".pdf", "_watermarked.pdf")
        try:
            res = pdf_tools.watermark_pdf(active_pdf, out_pdf, watermark_text=text)
            await update.message.reply_document(
                document=make_input_file(out_pdf, filename=active_name.replace(".pdf", "_watermarked.pdf")),
                caption=f"✅ Added diagonal watermark: **{res['watermark']}**",
                parse_mode="Markdown"
            )
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit_text(f"❌ Watermarking failed: {str(e)}")
        finally:
            if os.path.exists(out_pdf):
                try: os.remove(out_pdf)
                except: pass


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and notify the user gracefully without crashing."""
    logger.error("Exception while handling update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ An unexpected error occurred while processing this document. "
                "Please try again or use /cancel to reset your session."
            )
        except Exception:
            pass


def create_bot_application() -> Application:
    """Build and configure the Telegram bot Application."""
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is empty! Set TELEGRAM_BOT_TOKEN in .env or config.py")
        
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Error handler
    app.add_error_handler(global_error_handler)
    
    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tools", help_command))
    app.add_handler(CommandHandler("merge", merge_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Message handlers
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    return app


if __name__ == "__main__":
    import run_bot
    run_bot.main()
