import json
import os
import time
from typing import Dict, Any
import asyncio
from datetime import datetime  # <--- добавили для форматирования дат

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ================== НАСТРОЙКИ ==================

TOKEN = "8449787376:AAHiF6t-pG5uSjiW7EayJBbH5ZliS1lSSNU"  # ⚠️ сильно советую потом сменить токен
ADMIN_ID = 7877092881          # ID админа
DATA_FILE = "data.json"        # файл для хранения данных
WELCOME_IMAGE_PATH = "welcome.jpg"  # имя файла с картинкой

CLICK_COOLDOWN = 15  # секунд между кликами

# Канал
CHANNEL_LINK = "https://t.me/+g1mm-WpU9owwMWJk"

# ID канала (и для подписки, и для выдачи админки)
CHANNEL_ID = -1003009758716

# Цены бустеров (в кликах)
BOOSTER_PRICES = {
    "1.25": 20,   # 1.25x за 20 кликов
    "1.5": 50,    # 1.5x за 50 кликов
    "2": 100,     # 2x за 100 кликов
}

# Цены админок
ADMIN_L1_PRICE = 250  # админка 1 ур. — писать в канал
ADMIN_L2_PRICE = 250  # админка 2 ур. — ещё и менять профиль канала

# Срок действия админки (7 дней)
WEEK_SECONDS = 7 * 24 * 60 * 60

# Структура данных:
data: Dict[str, Any] = {"users": {}}

# ================== РАБОТА С ДАННЫМИ ==================

def load_data():
    global data
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {"users": {}}
    else:
        data = {"users": {}}


def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user_dict(user_id: int, username: str | None) -> Dict[str, Any]:
    """Возвращает словарь пользователя, создаёт, если его нет."""
    uid = str(user_id)
    users = data.setdefault("users", {})
    if uid not in users:
        users[uid] = {
            "username": username or "Без ника",
            "clicks": 0.0,
            "multiplier": 1.0,
            "last_click": 0.0,
            "admin_level": 0,        # 0 — нет админки, 1 — ур.1, 2 — ур.2
            "admin_expires_at": 0.0, # unix-время окончания админки
            "accepted_tos": False,   # принял ли ToS
        }
        save_data()
    else:
        # Обновим ник, если изменился
        if username and users[uid].get("username") != username:
            users[uid]["username"] = username
            save_data()
        # Дозакинем новые поля, если старый юзер
        if "admin_level" not in users[uid]:
            users[uid]["admin_level"] = 0
            save_data()
        if "admin_expires_at" not in users[uid]:
            users[uid]["admin_expires_at"] = 0.0
            save_data()
        if "accepted_tos" not in users[uid]:
            users[uid]["accepted_tos"] = False
            save_data()
    return users[uid]

# ================== ПРОВЕРКА ПОДПИСКИ ==================

async def is_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Проверяет, подписан ли пользователь на канал.
    Бот должен быть админом в канале.
    """
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        # statuses: "creator", "administrator", "member", "restricted", "left", "kicked"
        return member.status not in ("left", "kicked")
    except Exception as e:
        print(f"Error while checking subscription for {user_id}: {e}")
        return False

# ================== КЛАВИАТУРЫ ==================

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👆 Кликнуть", callback_data="click")],
        [InlineKeyboardButton("📊 Топ игроков", callback_data="stats")],
        [InlineKeyboardButton("🤑 Магазин", callback_data="shop")],
    ])


def shop_keyboard(user_data: Dict[str, Any]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"⚡ Бустер 1.25x — {BOOSTER_PRICES['1.25']} кликов", callback_data="buy_1.25")],
        [InlineKeyboardButton(f"🚀 Бустер 1.5x — {BOOSTER_PRICES['1.5']} кликов", callback_data="buy_1.5")],
        [InlineKeyboardButton(f"🔥 Бустер 2x — {BOOSTER_PRICES['2']} кликов", callback_data="buy_2")],
    ]

    admin_level = user_data.get("admin_level", 0)

    if admin_level < 1:
        buttons.append([
            InlineKeyboardButton(
                f"👑 Админка 1 ур. (7 дней) — {ADMIN_L1_PRICE} кликов",
                callback_data="buy_admin_1"
            )
        ])
    elif admin_level == 1:
        buttons.append([
            InlineKeyboardButton(
                f"👑 Админка 2 ур. (7 дней) — {ADMIN_L2_PRICE} кликов",
                callback_data="buy_admin_2"
            )
        ])
    else:
        buttons.append([
            InlineKeyboardButton(
                "✅ Админка 2 ур. уже есть у тя",
                callback_data="admin_max"
            )
        ])

    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(buttons)


def subscribe_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для экрана подписки."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Наш канал", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")],
    ])


def tos_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для ToS."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Принять правила", callback_data="accept_tos")],
    ])

# ================== ОБЩЕЕ ПРИВЕТСТВИЕ ДЛЯ ПОДПИСАННЫХ ==================

async def send_welcome_tunuzia(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    """
    Красивое приветствие TunuziaClicker для подписанных.
    Можно вызывать как из /start, так и после успешной проверки подписки / ToS.
    """
    chat_id = (
        update_or_query.effective_chat.id
        if isinstance(update_or_query, Update)
        else update_or_query.message.chat.id
    )

    caption = (
        "<b><blockquote>👋 Добро пожаловать в TunuziaClicker!</blockquote>\n\n"
        "<blockquote>💠 Пока что бесполезный кликер хз для чего\n"
        "📢 Наш канал: <a href=\"https://t.me/+g1mm-WpU9owwMWJk\">tunuZia</a></blockquote>\n\n"
        "👇 <b>Используй кнопки ниже для продолжения:</b></b>"
    )

    if os.path.exists(WELCOME_IMAGE_PATH):
        with open(WELCOME_IMAGE_PATH, "rb") as img:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=InputFile(img),
                caption=caption,
                reply_markup=main_keyboard(),
                parse_mode="HTML"
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )

# ================== ToS ==================

async def send_tos_message(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<blockquote><b>📜 Условия использования TunuziaClicker</b></blockquote>\n\n"
        "<blockquote>"
        "<b>• Бот создан для развлечения, всё внутри — виртуально.</b>\n"
        "<b>• Права администрации в канале выдаются на 7 дней + день покупки.</b>\n"
        "<b>• Админка, купленная в боте, может быть отозвана без объяснения причины.</b>\n"
        "<b>• Администратор может заблокировать вас в боте или канале без объяснения причины.</b>\n"
        "<b>• По доп вопросам - /help и /me | разработчик - @codespaster.</b>\n"
        "</blockquote>\n"
        "<b>Нажимая кнопку «✅ Принять правила», ты подтверждаешь согласие с вышеуказанным.</b>"
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=tos_keyboard(),
        parse_mode="HTML"
    )

# ================== ПРОГРЕСС-БАР ==================

def make_progress_bar(current: float, target: float, length: int = 10) -> tuple[str, int, float]:
    """
    Возвращает (bar, percent, remaining).
    bar — строка из █ и ░
    percent — целое число процентов
    remaining — сколько ещё не хватает (не меньше 0)
    """
    if target <= 0:
        return "██████████", 100, 0.0

    remaining = max(0.0, target - current)
    ratio = min(max(current / target, 0.0), 1.0)
    filled = int(ratio * length)
    bar = "█" * filled + "░" * (length - filled)
    percent = int(ratio * 100)
    return bar, percent, remaining

# ================== JOB: СНЯТИЕ АДМИНКИ ==================

async def remove_admin_job(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_id = job.data["user_id"]
    user_data = get_user_dict(user_id, None)

    level = user_data.get("admin_level", 0)
    expires_at = float(user_data.get("admin_expires_at", 0.0))

    # если уже нет админки или срок ещё не пришёл — ничего не делаем
    now = time.time()
    if level == 0 or expires_at == 0 or now < expires_at:
        return

    try:
        # снимаем все админ-права
        await context.bot.promote_chat_member(
            chat_id=CHANNEL_ID,
            user_id=user_id,
            can_manage_chat=False,
            can_post_messages=False,
            can_edit_messages=False,
            can_delete_messages=False,
            can_invite_users=False,
            can_change_info=False,
            can_promote_members=False,
            can_manage_video_chats=False,
            is_anonymous=False,
        )
    except Exception as e:
        print(f"Error while demoting user {user_id}: {e}")

    user_data["admin_level"] = 0
    user_data["admin_expires_at"] = 0.0
    save_data()

    # Уведомление пользователю
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "⌛️ <b>Срок действия твоей админки истёк</b>\n\n"
                "все права были отозваны.\n"
                "вы можете купить админку заново в магазине бота за ту же цену 🛒"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Error notifying user {user_id} about admin removal: {e}")

    # Лог в ЛС админу
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "⌛️ <b>Срок админки истёк и права были отозваны.</b>\n\n"
                f"🆔 Ur ID: <code>{user_id}</code>\n"
                f"👑 Бывший уровень прав: {level}"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Error logging admin removal to admin: {e}")

def schedule_admin_expiry_job_for_user(app, user_id: int, expires_at: float):
    """Создаёт/пересоздаёт джобу снятия админки для пользователя."""
    job_queue = app.job_queue
    job_name = f"admin_expire_{user_id}"
    # убираем старые джобы с тем же именем
    for job in job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()

    now = time.time()
    delay = max(0, expires_at - now)
    job_queue.run_once(
        remove_admin_job,
        when=delay,
        data={"user_id": user_id},
        name=job_name,
    )

def schedule_admin_expiry_jobs_for_all_users(app):
    """Вызывается при старте бота — досоздаёт джобы для тех, у кого есть активная админка."""
    now = time.time()
    users = data.get("users", {})
    for uid, uinfo in users.items():
        level = uinfo.get("admin_level", 0)
        expires_at = float(uinfo.get("admin_expires_at", 0.0))
        if level > 0 and expires_at > 0:
            delay = max(0, expires_at - now)
            job_name = f"admin_expire_{uid}"
            # удалим старые, если были
            for job in app.job_queue.get_jobs_by_name(job_name):
                job.schedule_removal()
            app.job_queue.run_once(
                remove_admin_job,
                when=delay,
                data={"user_id": int(uid)},
                name=job_name,
            )

# ================== ОБРАБОТЧИКИ КОМАНД ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Сначала проверяем подписку
    if not await is_subscribed(user.id, context):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                "🚫<blockquote> <b>Доступ к TunuziaClicker закрыт</b></blockquote>\n\n"
                "Чтобы пользоваться ботом, подпишись на наш канал:\n"
                f"<a href=\"{CHANNEL_LINK}\">📢 Наш канал</a>\n\n"
                "После подписки нажми кнопку <b>«✅ Проверить подписку»</b> ниже 👇"
            ),
            reply_markup=subscribe_keyboard(),
            parse_mode="HTML"
        )
        return

    # Уже подписан
    user_data = get_user_dict(user.id, user.username)

    # Если ещё не принял ToS — показываем ToS
    if not user_data.get("accepted_tos", False):
        await send_tos_message(update.effective_chat.id, context)
        return

    # Если ToS принят — обычный старт
    await send_welcome_tunuzia(update, context)


async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Только админ
    if user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text(
            "📢 Использование:\n<b>/broadcast</b> <текст сообщения>",
            parse_mode="HTML"
        )
        return

    message_text = " ".join(context.args)

    users = data.get("users", {})
    success = 0
    failed = 0

    await update.message.reply_text(
        f"📨 Рассылка запущена...\n👥 Пользователей: {len(users)}"
    )

    for uid in users.keys():
        try:
            await context.bot.send_message(
                chat_id=int(uid),
                text=message_text,
                parse_mode="HTML"
            )
            success += 1
            await asyncio.sleep(0.05)  # ⏱ защита от лимитов
        except Exception:
            failed += 1

    await update.message.reply_text(
        f"✅ Готово!\n\n"
        f"📬 Успешно (400): {success}\n"
        f"⚠️ Ошибок (503): {failed}"
    )


async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return
    text = (
        "🛠 <b>Админ-панель TunuziaClicker</b>\n\n"
        "📌 Команды:\n"
        "• <code>/broadcast &lt;текст&gt;</code> — отправить рассылку всем пользователям.\n"
        "• <code>/addclicks &lt;user_id&gt; &lt;amount&gt;</code> — начислить пользователю клики.\n"
        "• <code>/users_admins</code> — список всех с админкой.\n"
        "• <code>/me</code> — профиль игрока (для всех).\n\n"
        "Примеры:\n"
        "• <code>/addclicks 123456789 100</code>\n"
        "• <code>/broadcast &lt;b&gt;Внимание!&lt;/b&gt; Завтра будет обновление 🚀</code>"
    )

    await update.message.reply_text(text, parse_mode="HTML")


async def add_clicks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return

    if len(context.args) != 2:
        await update.message.reply_text(
            "ℹ️ Использование: <code>/addclicks &lt;user_id&gt; &lt;amount&gt;</code>",
            parse_mode="HTML"
        )
        return

    try:
        target_id = int(context.args[0])
        amount = float(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ user_id и amount должны быть числами.")
        return

    target = get_user_dict(target_id, None)
    target["clicks"] += amount
    save_data()

    await update.message.reply_text(
        f"💰 Начислено <b>{amount}</b> кликов пользователю "
        f"<b>{target.get('username')}</b> (ID: <code>{target_id}</code>).\n"
        f"Теперь у него <b>{target['clicks']:.2f}</b> кликов.",
        parse_mode="HTML"
    )




# ================== /me ==================

async def me_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = get_user_dict(user.id, user.username)

    # Проверка подписки
    if not await is_subscribed(user.id, context):
        await update.message.reply_text(
            "🚫 Сначала подпишись на канал и нажми «Проверить подписку».",
            parse_mode="HTML"
        )
        return

    # Проверка ToS
    if not user_data.get("accepted_tos", False):
        await update.message.reply_text(
            "📜 Ты ещё не принял правила использования.\n"
            "Нажми кнопку ниже:",
            reply_markup=tos_keyboard(),
            parse_mode="HTML"
        )
        return

    admin_level = user_data.get("admin_level", 0)
    clicks = float(user_data.get("clicks", 0.0))

    # Название уровня админки
    admin_text = {
        0: "❌ Нет прав у тя лол",
        1: "👑 Админ 1 ур.",
        2: "👑 Админ 2 ур.",
    }.get(admin_level, "❓ Неизвестно")

    # Прогресс до следующей админки (по кликам)
    if admin_level == 0:
        target = ADMIN_L1_PRICE
        label_next = "до админки 1 ур."
    elif admin_level == 1:
        target = ADMIN_L2_PRICE
        label_next = "до админки 2 ур."
    else:
        target = None
        label_next = None

    if target is not None:
        bar, percent, remaining = make_progress_bar(clicks, target)
        next_admin_block = (
            f"\n\n👑 <b>Прогресс {label_next}:</b>\n"
            f"[{bar}] {percent}%\n"
            f"⬇️ <i>Осталось:</i> <code>{remaining:.2f}</code> кликов"
        )
    else:
        next_admin_block = "\n\n👑 <b>Админка:</b> максимальный уровень у тя щя."

    caption = (
        "<blockquote><b>👤 Твой профиль с информацией TunuziaClicker</b></blockquote>\n\n"
        f"<blockquote>🆔 <b>Ur ID:</b> <code>{user.id}</code>\n"
        f"📛 <b>Юзернейм:</b> <code>{user_data['username']}</code></blockquote>\n\n"
        f"<blockquote>💰 <b>Кликов:</b> <code>{clicks:.2f}</code>\n"
        f"⚙️ <b>Уровень бустера:</b> x{float(user_data['multiplier']):.2f}\n"
        f"👑 <b>Админка:</b> {admin_text}\n"
        f"📜 <b>ToS принят:</b> {'✅ Да' if user_data['accepted_tos'] else '❌ Нет'}</blockquote>"
        f"{next_admin_block}"
    )

    chat_id = update.effective_chat.id

    # Отправляем как "карточку-профиль" с картинкой, если есть
    if os.path.exists(WELCOME_IMAGE_PATH):
        with open(WELCOME_IMAGE_PATH, "rb") as img:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=InputFile(img),
                caption=caption,
                parse_mode="HTML"
            )
    else:
        await update.message.reply_text(
            caption,
            parse_mode="HTML"
        )

# ================== /users_admins ==================

async def users_admins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return

    users_dict = data.get("users", {})
    admins = [
        (uid, uinfo)
        for uid, uinfo in users_dict.items()
        if uinfo.get("admin_level", 0) > 0
    ]

    if not admins:
        await update.message.reply_text(
            "👑 Админов, купленных через бота, пока нет.",
            parse_mode="HTML"
        )
        return

    # сортируем: сначала по уровню админки (2 -> 1), потом по кликам
    admins.sort(
        key=lambda item: (
            -item[1].get("admin_level", 0),
            -float(item[1].get("clicks", 0.0))
        )
    )

    lines = []
    now = time.time()
    for i, (uid, uinfo) in enumerate(admins, start=1):
        level = uinfo.get("admin_level", 0)
        level_text = "1 ур." if level == 1 else "2 ур."
        expires_at = float(uinfo.get("admin_expires_at", 0.0))
        if expires_at > 0:
            remain = max(0, int(expires_at - now))
            hours = remain // 3600
            # красивое время конца
            expires_dt = datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M:%S")
            lines.append(
                f"{i}. <b>{uinfo.get('username', 'Без ника')}</b> "
                f"(ID: <code>{uid}</code>) — 👑 {level_text}, "
                f"осталось ~ <code>{hours}</code> ч (до {expires_dt})"
            )
        else:
            lines.append(
                f"{i}. <b>{uinfo.get('username', 'Без ника')}</b> "
                f"(ID: <code>{uid}</code>) — 👑 {level_text}, "
                f"⏳ срок неизвестен"
            )

    text = (
        "<blockquote><b>👑 Админы TunuziaClicker (по данным бота лог из data.json)</b></blockquote>\n\n"
        + "\n".join(lines)
    )

    await update.message.reply_text(text, parse_mode="HTML")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "<b><blockquote>❓ Помощь по TunuziaClicker</blockquote>\n\n"
        "👋 Небольшая помощь по боту:\n\n"
        "<blockquote>🟢 <b>Основное</b>\n"
        "• <code>/start</code> — запуск бота, ToS, чек подписки.\n"
        "• <code>/me</code> — твой профиль: клики, бустеры, админка.</blockquote>\n\n"
        "<blockquote>🟡 <b>Кнопки под сообщением</b>\n"
        "• <b>👆 Кликнуть</b> — фарм кликов (кд 15 сек).\n"
        "• <b>📊 Топ игроков</b> — рейтинг по кликам (топ 10 крч).\n"
        "• <b>🤑 Магазин</b> — покупка бустеров и админки.</blockquote>\n\n"
        "<blockquote>💸 <b>Магазин</b>\n"
        "• Бустеры увеличивают количество кликов за один тап.\n"
        "• Админка 1 ур. — право писать в канал на 7 дней.\n"
        "• Админка 2 ур. — писать + менять профиль канала 7 дней.</blockquote>\n\n"
        "по доп вопросам @codespaster 💬</b>"
    )

    await update.message.reply_text(text, parse_mode="HTML")

# ================== ОБРАБОТЧИК КНОПОК ==================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    # --- Отдельно обрабатываем кнопку проверки подписки ---
    if query.data == "check_sub":
        if await is_subscribed(user.id, context):
            user_data = get_user_dict(user.id, user.username)

            # Если ToS ещё не принят — показываем ToS
            if not user_data.get("accepted_tos", False):
                await send_tos_message(query.message.chat.id, context)
            else:
                await send_welcome_tunuzia(query, context)

            await query.answer("✅ Подписка подтверждена!", show_alert=False)
        else:
            await query.answer(
                "🚫 Вы ещё не подписаны на канал. Подпишитесь и попробуйте снова.",
                show_alert=True
            )
        return

    # Проверка подписки для всех остальных кнопок
    if not await is_subscribed(user.id, context):
        await query.answer(
            "🚫 Сначала подпишитесь на наш канал, затем нажмите «Проверить подписку».",
            show_alert=True
        )
        await context.bot.send_message(
            chat_id=query.message.chat.id,
            text=(
                "<blockquote>🔒 <b>Доступ к TunuziaClicker закрыт</b></blockquote>\n\n"
                "Чтобы пользоваться ботом, подпишитесь на канал:\n"
                f"<a href=\"{CHANNEL_LINK}\">📢 Наш канал</a>\n\n"
                "После подписки нажмите «✅ Проверить подписку» 👇"
            ),
            reply_markup=subscribe_keyboard(),
            parse_mode="HTML"
        )
        return

    user_data = get_user_dict(user.id, user.username)

    # --- Обработка принятия ToS ---
    if query.data == "accept_tos":
        if user_data.get("accepted_tos", False):
            await query.answer("Ты уже принял правила ✅", show_alert=False)
        else:
            user_data["accepted_tos"] = True
            save_data()
            await query.answer("✅ Правила приняты!", show_alert=True)

            # ЛОГ В ЛС АДМИНУ
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        "📜 <b>Пользователь принял ToS</b>\n\n"
                        f"🆔 ID: <code>{user.id}</code>\n"
                        f"📛 Username: <code>{user.username or 'Без ника'}</code>"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Error logging ToS accept to admin: {e}")

            # Меняем текст сообщения с ToS
            await query.edit_message_text(
                "✅ Ты принял условия использования TunuziaClicker.\nОткрываю меню...",
                parse_mode="HTML"
            )
            # Отправляем приветствие
            await send_welcome_tunuzia(query, context)
        return

    # Если ToS ещё не принят — блокируем остальные кнопки
    if not user_data.get("accepted_tos", False):
        await query.answer(
            "📜 Сначала нужно принять правила использования (ToS).",
            show_alert=True
        )
        await send_tos_message(query.message.chat.id, context)
        return

    # --- Дальше идёт логика для подписанных и принявших ToS пользователей ---
    data_changed = False

    if query.data == "click":
        now = time.time()
        last = user_data.get("last_click", 0)
        diff = now - last

        if diff < CLICK_COOLDOWN:
            remain = int(CLICK_COOLDOWN - diff)
            await query.answer(
                text=f"⏳ Следующий клик через {remain} сек.",
                show_alert=True
            )
            return

        gained = 1.0 * float(user_data.get("multiplier", 1.0))
        user_data["clicks"] += gained
        user_data["last_click"] = now
        data_changed = True

        await query.edit_message_caption(
            caption=(
                "<blockquote>👆 <b>Клик засчитан!</b></blockquote>\n\n"
                f"<blockquote>➕ Получено: <b>{gained:.2f} кликов\n"
                f"💰 Всего кликов: <code>{user_data['clicks']:.2f}</code>\n"
                f"⚙️ Текущий бустер: <b>x{user_data['multiplier']:.2f}</b></b></blockquote>"
            ),
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )

    elif query.data == "stats":
        users = data.get("users", {})
        sorted_users = sorted(
            users.items(),
            key=lambda item: item[1].get("clicks", 0.0),
            reverse=True
        )[:10]

        if not sorted_users:
            text = "📊 <b>Топ игроков</b>\n\nПока никто не кликал. Будь первым! 💥"
        else:
            lines = []
            for i, (uid, uinfo) in enumerate(sorted_users, start=1):
                lines.append(
                    f"{i}. <b>{uinfo.get('username', 'Без ника')}</b> "
                    f"(ID: <code>{uid}</code>) — <b>{uinfo.get('clicks', 0.0):.2f}</b> кликов"
                )
            text = "<blockquote>📊 <b>Топ игроков TunuziaClicker</b></blockquote>\n\n" + "\n".join(lines)

        await query.edit_message_caption(
            caption=text,
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )

    elif query.data == "shop":
        await query.edit_message_caption(
            caption=(
                "<b><blockquote>🛒 Магазин</blockquote>\n\n"
                f"<blockquote>💰 Твои клики: <code>{user_data['clicks']:.2f}</code>\n"
                f"⚙️ Текущий бустер: x{user_data['multiplier']:.2f}</blockquote>\n\n"
                "Выбери, что хочешь приобрести:</b>"
            ),
            reply_markup=shop_keyboard(user_data),
            parse_mode="HTML"
        )

    elif query.data == "back_main":
        await query.edit_message_caption(
            caption="<b><blockquote>👋 Мейн меню TunuziaClicker!</blockquote>\n\n"
                    f"<blockquote>🤗 Привет, <code>{user_data['username']}</code>\n"
                    "📢 Наш канал: <a href=\"https://t.me/+g1mm-WpU9owwMWJk\">tunuZia</a></blockquote>\n\n"
                    "👇 <b>Используй кнопки ниже для продолжения:</b></b>",
            reply_markup=main_keyboard(),
            parse_mode="HTML",
        )

    elif query.data == "admin_max":
        await query.answer(
            "✅ У тебя уже максимальная админка (2 ур.) нах те ещо.",
            show_alert=True
        )

    elif query.data == "buy_admin_1":
        if user_data.get("admin_level", 0) >= 1:
            await query.answer("🤔 У тебя уже есть админка 1 ур. или выше.", show_alert=True)
            return

        if user_data["clicks"] < ADMIN_L1_PRICE:
            await query.answer(
                f"❌ Недостаточно кликов.\n"
                f"Нужно: {ADMIN_L1_PRICE}, а у тебя: {user_data['clicks']:.2f}.",
                show_alert=True
            )
            return

        user_data["clicks"] -= ADMIN_L1_PRICE
        data_changed = True

        try:
            await context.bot.promote_chat_member(
                chat_id=CHANNEL_ID,
                user_id=user.id,
                can_manage_chat=False,
                can_post_messages=True,       # право писать
                can_edit_messages=False,
                can_delete_messages=False,
                can_invite_users=False,
                can_change_info=False,
                can_promote_members=False,
                can_manage_video_chats=False,
                is_anonymous=False,
            )

            user_data["admin_level"] = 1
            user_data["admin_expires_at"] = time.time() + WEEK_SECONDS
            data_changed = True

            # Планируем снятие админки через 7 дней
            schedule_admin_expiry_job_for_user(context.application, user.id, user_data["admin_expires_at"])

            await query.answer(
                "✅ Ты купил админку 1 ур. (7 дней) — теперь можешь писать в канал.",
                show_alert=True
            )

            # ЛОГ В ЛС АДМИНУ — В ЧЕЛОВЕЧЕСКОМ ФОРМАТЕ
            try:
                expires_dt = datetime.fromtimestamp(user_data["admin_expires_at"]).strftime("%Y-%m-%d %H:%M:%S")
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        "👑 <b>Покупка админки 1 ур.</b>\n\n"
                        f"🆔 ID: <code>{user.id}</code>\n"
                        f"📛 Username: <code>{user.username or 'Без ника'}</code>\n"
                        f"💰 Клики после покупки: <code>{user_data['clicks']:.2f}</code>\n"
                        f"⏳ Действует до: <code>{expires_dt}</code>"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Error logging admin L1 purchase: {e}")

            await query.edit_message_caption(
                caption=(
                    "👑 <b>Админка 1 ур. куплена!</b>\n\n"
                    "Теперь ты админ с правом писать в канал на 7 дней <3.\n\n"
                    f"💰 Оставшиеся клики: <code>{user_data['clicks']:.2f}</code>"
                ),
                reply_markup=main_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Error while promoting user {user.id} to admin L1: {e}")
            user_data["clicks"] += ADMIN_L1_PRICE
            data_changed = True
            await query.answer(
                "⚠️ Конфликт администраторов is_already_admin. Свяжитесь с @codespaster.",
                show_alert=True
            )

    elif query.data == "buy_admin_2":
        if user_data.get("admin_level", 0) < 1:
            await query.answer(
                "⚠️ Сначала купи админку 1 ур., потом 2 ур.",
                show_alert=True
            )
            return

        if user_data.get("admin_level", 0) >= 2:
            await query.answer("✅ У тебя уже админка 2 ур. куда там", show_alert=True)
            return

        if user_data["clicks"] < ADMIN_L2_PRICE:
            await query.answer(
                f"❌ Недостаточно кликов. Копи олух.\n"
                f"Нужно: {ADMIN_L2_PRICE}, а у тебя: {user_data['clicks']:.2f}.",
                show_alert=True
            )
            return

        user_data["clicks"] -= ADMIN_L2_PRICE
        data_changed = True

        try:
            await context.bot.promote_chat_member(
                chat_id=CHANNEL_ID,
                user_id=user.id,
                can_manage_chat=False,
                can_post_messages=True,
                can_edit_messages=False,
                can_delete_messages=False,
                can_invite_users=False,
                can_change_info=True,         # можно менять профиль канала
                can_promote_members=False,
                can_manage_video_chats=False,
                is_anonymous=False,
            )

            user_data["admin_level"] = 2
            user_data["admin_expires_at"] = time.time() + WEEK_SECONDS
            data_changed = True

            # Перепланируем снятие админки (теперь 2 ур., снова 7 дней)
            schedule_admin_expiry_job_for_user(context.application, user.id, user_data["admin_expires_at"])

            await query.answer(
                "✅ Ты купил админку 2 ур. (7 дней) — можешь менять профиль канала еще.",
                show_alert=True
            )

            # ЛОГ В ЛС АДМИНУ — В ЧЕЛОВЕЧЕСКОМ ФОРМАТЕ
            try:
                expires_dt = datetime.fromtimestamp(user_data["admin_expires_at"]).strftime("%Y-%m-%d %H:%M:%S")
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        "👑 <b>Покупка админки 2 ур.</b>\n\n"
                        f"🆔 ID: <code>{user.id}</code>\n"
                        f"📛 Username: <code>{user.username or 'Без ника'}</code>\n"
                        f"💰 Клики после покупки: <code>{user_data['clicks']:.2f}</code>\n"
                        f"⏳ Действует до: <code>{expires_dt}</code>"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Error logging admin L2 purchase: {e}")

            await query.edit_message_caption(
                caption=(
                    "👑 <b>Админка 2 ур. куплена!</b>\n\n"
                    "Теперь ты можешь менять профиль канала (название, аву, описание) в течение 7 дней.\n\n"
                    f"💰 Оставшиеся клики: <code>{user_data['clicks']:.2f}</code>"
                ),
                reply_markup=main_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Error while promoting user {user.id} to admin L2: {e}")
            user_data["clicks"] += ADMIN_L2_PRICE
            data_changed = True
            await query.answer(
                "⚠️ Конфликт администраторов is_already_admin. Свяжитесь с @codespaster.",
                show_alert=True
            )

    elif query.data.startswith("buy_"):
        booster_str = query.data.split("_", 1)[1]
        price = BOOSTER_PRICES.get(booster_str)

        if price is None:
            await query.answer("⚠️ Неизвестный бустер.", show_alert=True)
            return

        if user_data["multiplier"] >= float(booster_str):
            await query.answer(
                "🤔 У тебя уже есть такой или более сильный бустер.",
                show_alert=True
            )
            return

        if user_data["clicks"] < price:
            await query.answer(
                f"❌ Недостаточно кликов. КОпи олух.\n"
                f"Нужно: {price}, а у тебя: {user_data['clicks']:.2f}.",
                show_alert=True
            )
            return

        user_data["clicks"] -= price
        user_data["multiplier"] = float(booster_str)
        data_changed = True

        await query.answer(
            f"✅ Покупка успешна! Новый бустер: x{user_data['multiplier']:.2f}",
            show_alert=True
        )

        await query.edit_message_caption(
            caption=(
                "✅ <b>Покупка успешна!</b>\n\n"
                f"⚙️ Новый бустер: <b>x{user_data['multiplier']:.2f}</b>\n"
                f"💰 Оставшиеся клики: <code>{user_data['clicks']:.2f}</code>\n\n"
                "Продолжай кликать и поднимайся в топ! 📈"
            ),
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )

    if data_changed:
        save_data()

# ================== ЗАПУСК ПРИЛОЖЕНИЯ ==================

def main():
    load_data()

    app = ApplicationBuilder().token(TOKEN).build()

    # Планируем снятие админок для уже существующих пользователей
    schedule_admin_expiry_jobs_for_all_users(app)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_help))
    app.add_handler(CommandHandler("addclicks", add_clicks_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("me", me_cmd))
    app.add_handler(CommandHandler("users_admins", users_admins_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    # Один обработчик для всех callback-кнопок
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
