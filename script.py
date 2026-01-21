import asyncio
import logging
import sqlite3
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatMemberStatus,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError

# ================== НАСТРОЙКИ ==================

BOT_TOKEN = "8368695770:AAGrToIf4nlWfH7U_lP3-yOcl7wmTWdwZaI"

# Числовой ID канала (ОБЯЗАТЕЛЬНО заменить!)
CHANNEL_ID = -1003009758716
CHANNEL_INVITE_LINK = "https://t.me/+g1mm-WpU9owwMWJk"

DB_PATH = "anon_bot.db"

# ===============================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальное соединение с SQLite (для примера)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row

# Память в процессе: кто сейчас пишет анонимный вопрос кому
pending_questions: dict[int, int] = {}       # {sender_id: target_user_id}
pending_start_payloads: dict[int, str] = {}  # {user_id: payload_from_start}


# ============ ИНИЦИАЛИЗАЦИЯ БД ============

def init_db():
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            deep_link_code TEXT UNIQUE,
            tos_accepted INTEGER DEFAULT 0,
            created_at TEXT
        );
        """
    )
    conn.commit()


# ============ ХЕЛПЕРЫ ПО БД ============

def base36encode(number: int) -> str:
    """Просто чтобы ссылка была короче, чем чистый user_id."""
    if number < 0:
        raise ValueError("number must be non-negative")
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if number == 0:
        return "0"
    result = []
    while number:
        number, i = divmod(number, 36)
        result.append(alphabet[i])
    return "".join(reversed(result))


def get_user(user_id: int):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return cur.fetchone()


def create_or_update_user(tg_user) -> sqlite3.Row:
    """Создаём пользователя, если его ещё нет, и возвращаем запись."""
    cur = conn.cursor()
    row = get_user(tg_user.id)
    if row is None:
        deep_link_code = base36encode(tg_user.id)
        cur.execute(
            """
            INSERT INTO users (user_id, username, first_name, last_name, deep_link_code, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                tg_user.id,
                tg_user.username,
                tg_user.first_name,
                tg_user.last_name,
                deep_link_code,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        row = get_user(tg_user.id)
    else:
        # Обновляем basic-инфу (на всякий случай)
        cur.execute(
            """
            UPDATE users
            SET username = ?, first_name = ?, last_name = ?
            WHERE user_id = ?
            """,
            (tg_user.username, tg_user.first_name, tg_user.last_name, tg_user.id),
        )
        conn.commit()
        row = get_user(tg_user.id)
    return row


def set_tos_accepted(user_id: int):
    cur = conn.cursor
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET tos_accepted = 1 WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()


def get_user_by_code(code: str):
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE deep_link_code = ?",
        (code,),
    )
    return cur.fetchone()


# ============ ПРОВЕРКА ПОДПИСКИ ============

async def is_subscribed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
    except TelegramError as e:
        logger.warning("Ошибка при проверке подписки: %s", e)
        return False

    if member.status in (
        ChatMemberStatus.LEFT,
        ChatMemberStatus.KICKED,
    ):
        return False
    return True


async def ensure_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Вернёт True, если подписан, иначе покажет сообщение и вернёт False."""
    if await is_subscribed(update, context):
        return True

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Подписаться на канал", url=CHANNEL_INVITE_LINK
                )
            ]
        ]
    )
    await update.effective_message.reply_text(
        "Чтобы пользоваться ботом, нужно быть подписанным на наш канал.",
        reply_markup=keyboard,
    )
    return False


# ============ ToS ============

TOS_TEXT = (
    "📜 <b>Условия использования (ToS)</b>\n\n"
    "1. Не отправляйте спам и оскорбления.\n"
    "2. Не нарушайте законы вашей страны.\n"
    "3. Администрация может заблокировать доступ без объяснения причин.\n\n"
    "Нажимая «Принимаю», вы соглашаетесь с этими условиями."
)


async def ensure_tos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет, принял ли пользователь ToS. Если нет – показывает кнопки. Возвращает True/False."""
    tg_user = update.effective_user
    row = create_or_update_user(tg_user)

    if row["tos_accepted"]:
        return True

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Принимаю", callback_data="tos_accept"),
                InlineKeyboardButton("❌ Не принимаю", callback_data="tos_decline"),
            ]
        ]
    )
    await update.effective_message.reply_html(TOS_TEXT, reply_markup=keyboard)
    return False


async def tos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if query.data == "tos_accept":
        set_tos_accepted(user.id)
        await query.edit_message_text(
            "Спасибо! ✅ Условия использования приняты.\n"
            "Используйте /profile, чтобы получить свою личную ссылку."
        )

        # Если пользователь пришёл по ссылке вида /start uid_xxx и мы это помним —
        # можно сразу вернуть его в сценарий анонимного вопроса.
        payload = pending_start_payloads.pop(user.id, None)
        if payload:
            fake_update = Update(
                update.update_id,
                message=update.effective_message  # для простоты используем то же сообщение
            )
            # "Ручной" вызов логики старта с аргументом
            await handle_start_with_payload(fake_update, context, payload)

    elif query.data == "tos_decline":
        await query.edit_message_text(
            "Вы отклонили условия использования. Бот не будет доступен."
        )


# ============ КОМАНДЫ ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает /start с аргументом и без."""
    # Сначала проверка подписки
    if not await ensure_subscription(update, context):
        return

    user = update.effective_user
    text = update.message.text or ""
    parts = text.split(maxsplit=1)
    payload = None
    if len(parts) == 2:
        payload = parts[1].strip()

    # Если пользователь не принял ToS – сначала ToS
    row = create_or_update_user(user)
    if not row["tos_accepted"]:
        if payload:
            # запомним, что он пришёл с payload
            pending_start_payloads[user.id] = payload
        await ensure_tos(update, context)
        return

    # Если payload есть – обработаем как анонимный вопрос
    if payload:
        await handle_start_with_payload(update, context, payload)
    else:
        # Обычный /start без аргументов – просто приветствие и подсказка
        await update.message.reply_text(
            "Привет! Я бот для анонимных вопросов.\n\n"
            "👤 Используй команду /profile, чтобы получить свою личную ссылку.\n"
            "Эту ссылку можно отправить друзьям, чтобы они задавали тебе анонимные вопросы."
        )


async def handle_start_with_payload(
    update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str
):
    """Отдельная логика обработки /start с аргументом (payload)."""
    user = update.effective_user

    if not payload.startswith("uid_"):
        await update.effective_message.reply_text(
            "Неверная или устаревшая ссылка. Попросите у пользователя новую ссылку."
        )
        return

    code = payload[4:]
    target = get_user_by_code(code)
    if target is None:
        await update.effective_message.reply_text(
            "Такого пользователя не найдено. Возможно, он ещё не запускал бота."
        )
        return

    target_name = target["first_name"] or "пользователю"
    pending_questions[user.id] = target["user_id"]

    await update.effective_message.reply_text(
        f"✉️ Напишите мне сообщение, и я анонимно отправлю его пользователю {target_name}.\n\n"
        "Чтобы отменить — отправьте /cancel."
    )


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает личную ссылку пользователя."""
    if not await ensure_subscription(update, context):
        return
    if not await ensure_tos(update, context):
        return

    tg_user = update.effective_user
    row = get_user(tg_user.id)
    if row is None:
        row = create_or_update_user(tg_user)

    deep_code = row["deep_link_code"]
    bot_username = (await context.bot.get_me()).username

    link = f"https://t.me/{bot_username}?start=uid_{deep_code}"

    await update.message.reply_text(
        "👤 Твой профиль:\n\n"
        f"🔗 Личная ссылка для анонимных вопросов:\n{link}\n\n"
        "Отправь эту ссылку друзьям — они смогут задавать тебе вопросы анонимно."
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена режима отправки анонимного вопроса."""
    user_id = update.effective_user.id
    if user_id in pending_questions:
        pending_questions.pop(user_id, None)
        await update.message.reply_text("Режим анонимного вопроса отменён.")
    else:
        await update.message.reply_text("У тебя сейчас нет активного анонимного вопроса.")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n"
        "/start - запуск\n"
        "/profile - получить свою ссылку\n"
        "/cancel - отменить отправку анонимного вопроса\n"
        "/help - помощь"
    )


# ============ ОБРАБОТКА ОТ ТЕКСТА ============

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Любое текстовое сообщение."""
    if not await ensure_subscription(update, context):
        return
    if not await ensure_tos(update, context):
        return

    user_id = update.effective_user.id
    text = update.message.text

    if user_id in pending_questions:
        # Пользователь пишет анонимный вопрос
        target_id = pending_questions.pop(user_id)
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    "📩 Вам пришло <b>анонимное сообщение</b>:\n\n"
                    f"{text}"
                ),
                parse_mode="HTML",
            )
            await update.message.reply_text("✅ Ваше анонимное сообщение отправлено!")
        except TelegramError as e:
            logger.error("Ошибка при отправке анонимного сообщения: %s", e)
            await update.message.reply_text(
                "Не удалось отправить сообщение пользователю. Возможно, он ещё не писал боту."
            )
    else:
        # Обычный текст вне режима вопросов
        await update.message.reply_text(
            "Я бот для анонимных вопросов.\n"
            "Чтобы получить свою ссылку — используй /profile.\n"
            "Чтобы задать анонимный вопрос по ссылке другого пользователя — перейди по её ссылке."
        )


# ============ MAIN ============

async def main():
    init_db()

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("help", help_cmd))

    application.add_handler(CallbackQueryHandler(tos_callback, pattern=r"^tos_"))

    # Любой текст, который не команда
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    await application.run_polling(close_loop=False)


if __name__ == "__main__":
    asyncio.run(main())
