import json
import os
import time
from typing import Dict, Any
import asyncio

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

TOKEN = "8449787376:AAHiF6t-pG5uSjiW7EayJBbH5ZliS1lSSNU"  # ⚠️ СЮДА ВСТАВЬ СВОЙ ТОКЕН
ADMIN_ID = 7877092881          # ID админа
DATA_FILE = "data.json"        # файл для хранения данных
WELCOME_IMAGE_PATH = "welcome.jpg"  # имя файла с картинкой

CLICK_COOLDOWN = 15  # секунд между кликами

# Канал
CHANNEL_LINK = "https://t.me/+g1mm-WpU9owwMWJk"

# ⚠️ СЮДА ВПИШИ ИД КАНАЛА (например -1001234567890)
CHANNEL_ID = -1003009758716

# Цены бустеров (в кликах)
BOOSTER_PRICES = {
    "1.25": 20,   # 1.25x за 20 кликов
    "1.5": 50,    # 1.5x за 50 кликов
    "2": 100,     # 2x за 100 кликов
}

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
        }
        save_data()
    else:
        # Обновим ник, если изменился
        if username and users[uid].get("username") != username:
            users[uid]["username"] = username
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
        [InlineKeyboardButton("🤑 Магазин бустеров", callback_data="shop")],
    ])


def shop_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"⚡ Бустер 1.25x — {BOOSTER_PRICES['1.25']} кликов", callback_data="buy_1.25")],
        [InlineKeyboardButton(f"🚀 Бустер 1.5x — {BOOSTER_PRICES['1.5']} кликов", callback_data="buy_1.5")],
        [InlineKeyboardButton(f"🔥 Бустер 2x — {BOOSTER_PRICES['2']} кликов", callback_data="buy_2")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(buttons)


def subscribe_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для экрана подписки."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Наш канал", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")],
    ])

# ================== ОБЩЕЕ ПРИВЕТСТВИЕ ДЛЯ ПОДПИСАННЫХ ==================

async def send_welcome_tunuzia(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    """
    Красивое приветствие TunuziaClicker для подписанных.
    Можно вызывать как из /start, так и после успешной проверки подписки.
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

    # Если уже подписан – запускаем основную логику
    get_user_dict(user.id, user.username)
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
        "• <code>/addclicks &lt;user_id&gt; &lt;amount&gt;</code> — начислить пользователю клики.\n\n"
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

# ================== ОБРАБОТЧИК КНОПОК ==================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user

    # --- Отдельно обрабатываем кнопку проверки подписки ---
    if query.data == "check_sub":
        if await is_subscribed(user.id, context):
            get_user_dict(user.id, user.username)
            await send_welcome_tunuzia(query, context)
            await query.answer("✅ Подписка подтверждена!", show_alert=False)
        else:
            await query.answer(
                "🚫 Вы ещё не подписаны на канал. Подпишитесь и попробуйте снова.",
                show_alert=True
            )
        return

    # Для всех остальных кнопок — доступ только при подписке
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

    # --- Дальше идёт логика для подписанных пользователей ---
    user_data = get_user_dict(user.id, user.username)
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
                "<b><blockquote>🛒 Магазин бустеров</blockquote>\n\n"
                f"<blockquote>💰 Твои клики: <code>{user_data['clicks']:.2f}</code>\n"
                f"⚙️ Текущий бустер: x{user_data['multiplier']:.2f}</blockquote>\n\n"
                "Выбери бустер ниже, чтобы фармить ещё быстрее:</b>"
            ),
            reply_markup=shop_keyboard(),
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
                f"❌ Недостаточно кликов.\n"
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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_help))
    app.add_handler(CommandHandler("addclicks", add_clicks_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))

    # Один обработчик для всех callback-кнопок
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
