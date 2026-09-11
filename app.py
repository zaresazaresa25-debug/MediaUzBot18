import os
import re
import glob
import shutil
import tempfile
import threading
from urllib.parse import urlparse

from flask import Flask, request
import telebot
from telebot import types
import yt_dlp


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set")


bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML",
    threaded=True
)

app = Flask(__name__)


SUPPORTED_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "tiktok.com",
    "instagram.com",
)


# =========================================================
# URL FUNCTIONS
# =========================================================

def is_supported_url(url):
    if not url:
        return False

    try:
        parsed = urlparse(url.strip())

        if parsed.scheme not in ("http", "https"):
            return False

        host = parsed.netloc.lower()

        if host.startswith("www."):
            host = host[4:]

        return any(
            host == domain or host.endswith("." + domain)
            for domain in SUPPORTED_DOMAINS
        )

    except Exception:
        return False


def extract_url(text):
    if not text:
        return None

    urls = re.findall(
        r'https?://[^\s<>"\']+',
        text
    )

    for url in urls:
        url = url.rstrip(".,!?;:)]}>")

        if is_supported_url(url):
            return url

    return None


# =========================================================
# DOWNLOAD VIDEO
# =========================================================

def download_video(url, work_dir):

    output_template = os.path.join(
        work_dir,
        "%(title).80s_%(id)s.%(ext)s"
    )

    ydl_opts = {
        "format": (
            "bv*[ext=mp4]+ba[ext=m4a]/"
            "bv*+ba/"
            "b[ext=mp4]/"
            "b"
        ),

        "outtmpl": output_template,
        "noplaylist": True,

        "retries": 5,
        "fragment_retries": 5,

        "socket_timeout": 30,

        "restrictfilenames": True,

        "merge_output_format": "mp4",

        "quiet": True,
        "no_warnings": True,

        "nocheckcertificate": False,

        "extract_flat": False,

        "overwrites": True,

        "concurrent_fragment_downloads": 4,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:

        info = ydl.extract_info(
            url,
            download=True
        )

        title = info.get("title") or "Video"

        files = []

        for path in glob.glob(
            os.path.join(work_dir, "*")
        ):
            if os.path.isfile(path):
                files.append(path)

        if not files:
            raise RuntimeError(
                "Video fayl yuklanmadi."
            )

        media_file = max(
            files,
            key=os.path.getsize
        )

        return {
            "file": media_file,
            "title": title
        }


# =========================================================
# DOWNLOAD AUDIO / MP3
# =========================================================

def download_audio(url, work_dir):

    output_template = os.path.join(
        work_dir,
        "%(title).80s_%(id)s.%(ext)s"
    )

    ydl_opts = {
        "format": (
            "bestaudio[ext=m4a]/"
            "bestaudio/best"
        ),

        "outtmpl": output_template,

        "noplaylist": True,

        "retries": 5,
        "fragment_retries": 5,

        "socket_timeout": 30,

        "restrictfilenames": True,

        "quiet": True,
        "no_warnings": True,

        "nocheckcertificate": False,

        "overwrites": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:

        info = ydl.extract_info(
            url,
            download=True
        )

        title = info.get("title") or "Audio"

        files = []

        for path in glob.glob(
            os.path.join(work_dir, "*")
        ):
            if os.path.isfile(path):
                files.append(path)

        if not files:
            raise RuntimeError(
                "Audio fayl yuklanmadi."
            )

        audio_file = max(
            files,
            key=os.path.getsize
        )

        return {
            "file": audio_file,
            "title": title
        }


# =========================================================
# VIDEO PROCESS
# =========================================================

def process_video(
    chat_id,
    url,
    status_message_id
):

    work_dir = tempfile.mkdtemp(
        prefix="mediauz_video_"
    )

    try:

        bot.edit_message_text(
            "🔎 <b>Havola tekshirilmoqda...</b>\n\n"
            "⏳ Video tayyorlanmoqda.",
            chat_id=chat_id,
            message_id=status_message_id,
            parse_mode="HTML"
        )

        result = download_video(
            url,
            work_dir
        )

        media_file = result["file"]
        title = result["title"]

        if not os.path.exists(media_file):
            raise RuntimeError(
                "Video fayl topilmadi."
            )

        file_size = os.path.getsize(media_file)

        max_size = 49 * 1024 * 1024

        if file_size > max_size:

            size_mb = file_size / (1024 * 1024)

            bot.edit_message_text(
                "⚠️ <b>Video juda katta.</b>\n\n"
                f"📦 Hajmi: <b>{size_mb:.1f} MB</b>\n\n"
                "Kichikroq video havolasini sinab ko‘ring.",
                chat_id=chat_id,
                message_id=status_message_id,
                parse_mode="HTML"
            )

            return

        bot.edit_message_text(
            "📤 <b>Video tayyor!</b>\n\n"
            "⏳ Telegramga yuborilmoqda...",
            chat_id=chat_id,
            message_id=status_message_id,
            parse_mode="HTML"
        )

        caption = (
            "🎬 <b>MediaUzBot</b>\n\n"
            f"📌 <b>{title}</b>\n\n"
            "✅ Video tayyor."
        )

        with open(media_file, "rb") as media:

            bot.send_document(
                chat_id=chat_id,
                document=media,
                caption=caption,
                timeout=180
            )

        try:
            bot.delete_message(
                chat_id,
                status_message_id
            )
        except Exception:
            pass

    except yt_dlp.utils.DownloadError as error:

        print(
            "Video yt-dlp error:",
            error
        )

        try:
            bot.edit_message_text(
                "❌ <b>Videoni yuklab bo‘lmadi.</b>\n\n"
                "🔗 Havola ishlamasligi yoki platformada "
                "cheklov bo‘lishi mumkin.\n\n"
                "Boshqa havolani sinab ko‘ring.",
                chat_id=chat_id,
                message_id=status_message_id,
                parse_mode="HTML"
            )
        except Exception:
            pass

    except Exception as error:

        print(
            "Video error:",
            type(error).__name__,
            error
        )

        try:
            bot.edit_message_text(
                "❌ <b>Yuklash vaqtida xatolik yuz berdi.</b>\n\n"
                "🔗 Boshqa havolani sinab ko‘ring.",
                chat_id=chat_id,
                message_id=status_message_id,
                parse_mode="HTML"
            )
        except Exception:
            pass

    finally:

        shutil.rmtree(
            work_dir,
            ignore_errors=True
        )


# =========================================================
# AUDIO PROCESS
# =========================================================

def process_audio(
    chat_id,
    url,
    status_message_id
):

    work_dir = tempfile.mkdtemp(
        prefix="mediauz_audio_"
    )

    try:

        bot.edit_message_text(
            "🎵 <b>Audio tayyorlanmoqda...</b>\n\n"
            "⏳ Biroz kuting.",
            chat_id=chat_id,
            message_id=status_message_id,
            parse_mode="HTML"
        )

        result = download_audio(
            url,
            work_dir
        )

        audio_file = result["file"]
        title = result["title"]

        if not os.path.exists(audio_file):
            raise RuntimeError(
                "Audio fayl topilmadi."
            )

        file_size = os.path.getsize(audio_file)

        max_size = 49 * 1024 * 1024

        if file_size > max_size:

            size_mb = file_size / (1024 * 1024)

            bot.edit_message_text(
                "⚠️ <b>Audio juda katta.</b>\n\n"
                f"📦 Hajmi: <b>{size_mb:.1f} MB</b>",
                chat_id=chat_id,
                message_id=status_message_id,
                parse_mode="HTML"
            )

            return

        bot.edit_message_text(
            "📤 <b>Audio tayyor!</b>\n\n"
            "⏳ Telegramga yuborilmoqda...",
            chat_id=chat_id,
            message_id=status_message_id,
            parse_mode="HTML"
        )

        caption = (
            "🎵 <b>MediaUzBot</b>\n\n"
            f"📌 <b>{title}</b>\n\n"
            "✅ Audio tayyor."
        )

        with open(audio_file, "rb") as audio:

            bot.send_document(
                chat_id=chat_id,
                document=audio,
                caption=caption,
                timeout=180
            )

        try:
            bot.delete_message(
                chat_id,
                status_message_id
            )
        except Exception:
            pass

    except yt_dlp.utils.DownloadError as error:

        print(
            "Audio yt-dlp error:",
            error
        )

        try:
            bot.edit_message_text(
                "❌ <b>Audioni yuklab bo‘lmadi.</b>\n\n"
                "🔗 Boshqa havolani sinab ko‘ring.",
                chat_id=chat_id,
                message_id=status_message_id,
                parse_mode="HTML"
            )
        except Exception:
            pass

    except Exception as error:

        print(
            "Audio error:",
            type(error).__name__,
            error
        )

        try:
            bot.edit_message_text(
                "❌ <b>Audio tayyorlashda xatolik yuz berdi.</b>\n\n"
                "🔗 Boshqa havolani sinab ko‘ring.",
                chat_id=chat_id,
                message_id=status_message_id,
                parse_mode="HTML"
            )
        except Exception:
            pass

    finally:

        shutil.rmtree(
            work_dir,
            ignore_errors=True
        )


# =========================================================
# START
# =========================================================

@bot.message_handler(commands=["start"])
def start_command(message):

    keyboard = types.InlineKeyboardMarkup()

    help_button = types.InlineKeyboardButton(
        "ℹ️ Yordam",
        callback_data="help"
    )

    keyboard.add(help_button)

    bot.send_message(
        message.chat.id,

        "👋 <b>Assalomu alaykum!</b>\n\n"
        "🎬 <b>MediaUzBot</b>ga xush kelibsiz!\n\n"
        "📥 YouTube, TikTok yoki Instagram "
        "havolasini yuboring.\n\n"
        "⚡ Keyin video yoki audio formatini "
        "tanlashingiz mumkin.\n\n"
        "🔗 <b>Havolani yuboring.</b>",

        reply_markup=keyboard
    )


# =========================================================
# HELP
# =========================================================

@bot.message_handler(commands=["help"])
def help_command(message):

    bot.send_message(
        message.chat.id,

        "ℹ️ <b>MediaUzBot yordam</b>\n\n"
        "🎬 YouTube\n"
        "🎵 TikTok\n"
        "📸 Instagram\n\n"
        "🔗 Havolani yuboring.\n\n"
        "Keyin:\n"
        "🎥 Video yoki\n"
        "🎵 Audio formatini tanlang."
    )


@bot.callback_query_handler(
    func=lambda call: call.data == "help"
)
def help_callback(call):

    bot.answer_callback_query(call.id)

    bot.send_message(
        call.message.chat.id,

        "ℹ️ <b>Qanday foydalaniladi?</b>\n\n"
        "1️⃣ YouTube, TikTok yoki Instagram "
        "havolasini nusxalang.\n\n"
        "2️⃣ Havolani MediaUzBotga yuboring.\n\n"
        "3️⃣ 🎥 Video yoki 🎵 Audio tugmasini "
        "bosing.\n\n"
        "4️⃣ Bot faylni tayyorlab yuboradi."
    )


# =========================================================
# LINK RECEIVED
# =========================================================

@bot.message_handler(
    content_types=["text"],
    func=lambda message: bool(
        extract_url(message.text or "")
    )
)
def link_handler(message):

    url = extract_url(
        message.text or ""
    )

    if not url:
        return

    keyboard = types.InlineKeyboardMarkup(
        row_width=2
    )

    video_button = types.InlineKeyboardButton(
        "🎥 Video",
        callback_data="video"
    )

    audio_button = types.InlineKeyboardButton(
        "🎵 Audio",
        callback_data="audio"
    )

    keyboard.add(
        video_button,
        audio_button
    )

    status = bot.send_message(
        message.chat.id,

        "🔗 <b>Havola qabul qilindi!</b>\n\n"
        "Qaysi format kerak?",

        reply_markup=keyboard,
        parse_mode="HTML"
    )

    bot.set_state(
        message.from_user.id,
        None,
        message.chat.id
    )

    # URL ni chatga vaqtincha bog‘lash
    bot_data = getattr(bot, "_media_urls", {})

    bot_data[status.message_id] = {
        "chat_id": message.chat.id,
        "url": url
    }

    bot._media_urls = bot_data


# =========================================================
# VIDEO BUTTON
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "video"
)
def video_callback(call):

    bot.answer_callback_query(
        call.id,
        "🎥 Video tayyorlanmoqda..."
    )

    data = getattr(
        bot,
        "_media_urls",
        {}
    ).get(call.message.message_id)

    if not data:

        bot.edit_message_text(
            "❌ <b>Havola ma'lumoti topilmadi.</b>\n\n"
            "Iltimos, havolani qaytadan yuboring.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML"
        )

        return

    bot.edit_message_text(
        "🎥 <b>Video yuklanmoqda...</b>\n\n"
        "⏳ Biroz kuting.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML"
    )

    thread = threading.Thread(
        target=process_video,
        args=(
            call.message.chat.id,
            data["url"],
            call.message.message_id
        ),
        daemon=True
    )

    thread.start()


# =========================================================
# AUDIO BUTTON
# =========================================================

@bot.callback_query_handler(
    func=lambda call: call.data == "audio"
)
def audio_callback(call):

    bot.answer_callback_query(
        call.id,
        "🎵 Audio tayyorlanmoqda..."
    )

    data = getattr(
        bot,
        "_media_urls",
        {}
    ).get(call.message.message_id)

    if not data:

        bot.edit_message_text(
            "❌ <b>Havola ma'lumoti topilmadi.</b>\n\n"
            "Iltimos, havolani qaytadan yuboring.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML"
        )

        return

    bot.edit_message_text(
        "🎵 <b>Audio yuklanmoqda...</b>\n\n"
        "⏳ Biroz kuting.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML"
    )

    thread = threading.Thread(
        target=process_audio,
        args=(
            call.message.chat.id,
            data["url"],
            call.message.message_id
        ),
        daemon=True
    )

    thread.start()


# =========================================================
# OTHER TEXT
# =========================================================

@bot.message_handler(content_types=["text"])
def other_text(message):

    bot.send_message(
        message.chat.id,

        "🔗 <b>Video havolasini yuboring.</b>\n\n"
        "Qo‘llab-quvvatlanadi:\n"
        "• YouTube\n"
        "• TikTok\n"
        "• Instagram"
    )


# =========================================================
# FLASK
# =========================================================

@app.route("/", methods=["GET"])
def home():

    return "MediaUzBot is running!", 200


@app.route("/health", methods=["GET"])
def health():

    return {
        "status": "ok",
        "bot": "MediaUzBot"
    }, 200


@app.route("/webhook", methods=["POST"])
def webhook():

    try:
        if not request.is_json:
            print("WEBHOOK: JSON emas")
            return "Bad Request", 400

        json_string = request.get_data().decode("utf-8")

        print("WEBHOOK UPDATE:", json_string)

        update = types.Update.de_json(json_string)

        if update is None:
            print("WEBHOOK: Update yaratilmadi")
            return "OK", 200

        bot.process_new_updates([update])

        print("WEBHOOK: Update qayta ishlandi")

        return "OK", 200

    except Exception as error:
        print(
            "WEBHOOK ERROR:",
            type(error).__name__,
            str(error)
        )
        return "OK", 200
# WEBHOOK SETUP
# =========================================================

def setup_webhook():

    render_url = os.environ.get(
        "RENDER_EXTERNAL_URL",
        ""
    ).strip()

    if not render_url:

        print(
            "RENDER_EXTERNAL_URL topilmadi."
        )

        return

    webhook_url = (
        render_url.rstrip("/")
        + "/webhook"
    )

    try:

        bot.remove_webhook()

        bot.set_webhook(
            url=webhook_url
        )

        print(
            "Webhook o‘rnatildi:",
            webhook_url
        )

    except Exception as error:

        print(
            "Webhook xatosi:",
            error
        )


setup_webhook()


# =========================================================
# LOCAL RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
)
