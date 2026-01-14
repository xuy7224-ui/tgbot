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

TOKEN = "BOT_TOKEN"          # <-- сюда токен бота
ADMIN_ID = 7877092881                  # ID админа
DATA_FILE = "data.json"                # файл для хранения данных
WELCOME_IMAGE_PATH = "welcome.jpg"     # имя файла с картинкой

CLICK_COOLDOWN = 15  # секунд между кликами

# Цены бустеров (в кликах)
BOOSTER_PRICES = {
    "1.25": 20,   # 1.25x за 100 кликов
    "1.5": 50,    # 1.5x за 250 кликов
    "2": 100,      # 2x за 500 кликов
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


def get_user_dict(user_id: int, username: str) -> Dict[str, Any]:
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

# ================== КЛАВИАТУРЫ ==================

def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👆Клик", callback_data="click")],
        [InlineKeyboardButton("📊Статистика", callback_data="stats")],
        [InlineKeyboardButton("🤑Магазин", callback_data="shop")],
    ])

def shop_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"⬆️Бустер 1.25x — {BOOSTER_PRICES['1.25']} кликов", callback_data="buy_1.25")],
        [InlineKeyboardButton(f"⬆️Бустер 1.5x — {BOOSTER_PRICES['1.5']} кликов", callback_data="buy_1.5")],
        [InlineKeyboardButton(f"⬆️Бустер 2x — {BOOSTER_PRICES['2']} кликов", callback_data="buy_2")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(buttons)

# ================== ОБРАБОТЧИКИ КОМАНД ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user_dict(user.id, user.username)

    # Отправляем картинку с кнопками
    if os.path.exists(WELCOME_IMAGE_PATH):
        with open(WELCOME_IMAGE_PATH, "rb") as img:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=InputFile(img),
                caption="<b> - Привет, это кликер имени великой Tunuzia\n<a href=\"https://t.me/+g1mm-WpU9owwMWJk\">- Наш канал</a></b>",
                reply_markup=main_keyboard(),
                parse_mode="HTML"
            )

    else:
        # Если картинка не найдена, просто текст
        await update.message.reply_text(
            "Добро пожаловать в бота (файл welcome.jpg не найден)",
            reply_markup=main_keyboard(),
        )


async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Только админ
    if user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text(
            "Использование:\n/broadcast <текст сообщения>",
            parse_mode="HTML"
        )
        return

    message_text = " ".join(context.args)

    users = data.get("users", {})
    success = 0
    failed = 0

    await update.message.reply_text(
        f"📢 starting...\nusers regd: {len(users)}"
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
        f"✅ done\n\n"
        f"400: {success}\n"
        f"503: {failed}"
    )


async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return
    text = (
        "🛠 Админ-панель\n\n"
        "Команды:\n"
        "Использование:\n/broadcast <текст сообщения>.\n"
        "/addclicks <user_id> <amount> — начислить пользователю клики.\n\n"
        "Пример:\n"
        "/addclicks 123456789 100\n"
        "/broadcast < b > Внимание! < / b >Завтра будет обновление 🚀"

    )

    await update.message.reply_text(text)

parse_mode="HTML"
async def add_clicks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        return
    parse_mode = "HTML"
    if len(context.args) != 2:
        await update.message.reply_text(
            "Использование: /addclicks <user_id> <amount>"
        )
        return

    try:
        target_id = int(context.args[0])
        amount = float(context.args[1])
    except ValueError:
        await update.message.reply_text("user_id и amount должны быть числами.")
        return

    target = get_user_dict(target_id, None)
    target["clicks"] += amount
    save_data()

    await update.message.reply_text(
        f"Начислено {amount} кликов пользователю {target.get('username')} "
        f"(ID: {target_id}). Теперь у него {target['clicks']:.2f} кликов."
    )

# ================== ОБРАБОТЧИК КНОПОК ==================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # ❗ УБРАЛИ await query.answer() ОТСЮДА

    user = query.from_user
    user_data = get_user_dict(user.id, user.username)
    data_changed = False

    if query.data == "click":
        now = time.time()
        last = user_data.get("last_click", 0)
        diff = now - last

        if diff < CLICK_COOLDOWN:
            remain = int(CLICK_COOLDOWN - diff)
            await query.answer(
                text=f"✔️следующий клик через {remain} сек.",
                show_alert=True
            )
            return

        gained = 1.0 * float(user_data.get("multiplier", 1.0))
        user_data["clicks"] += gained
        user_data["last_click"] = now
        data_changed = True

        await query.edit_message_caption(
            caption=(
                "<blockquote><b>Добро пожаловать в бота</b>\n\n"
                "Ты кликнул! <b>+{:.2f}</b> кликов\n"
                "Всего кликов: <code>{:.2f}</code>\n"
                "Текущий бустер: <b>x{:.2f}</b></blockquote>"
            ).format(
                gained,
                user_data["clicks"],
                user_data["multiplier"]
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
            text = "Статистика пуста."
        else:
            lines = []
            for i, (uid, uinfo) in enumerate(sorted_users, start=1):
                lines.append(
                    f"{i}. {uinfo.get('username', 'Без ника')} "
                    f"(ID: {uid}) — {uinfo.get('clicks', 0.0):.2f} кликов"
                )
            text = "📊 Статистика игроков:\n\n" + "\n".join(lines)

        text = "<blockquote><b>📊 Статистика игроков</b></blockquote>\n\n"
        text += "<b>\n==\n</b>".join(lines)

        await query.edit_message_caption(
            caption=text,
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )


    elif query.data == "shop":
        await query.edit_message_caption(
            caption=(
                "<blockquote>🛒 <b>Магазин бустеров</b>\n\n"
                "Твои клики: <code>{:.2f}</code>\n"
                "Текущий бустер: <b>x{:.2f}</b>\n\n"
                "<i>Выбери бустер:</i></blockquote>"
            ).format(
                user_data["clicks"],
                user_data["multiplier"]
            ),
            reply_markup=shop_keyboard(),
            parse_mode="HTML"
        )


    elif query.data == "back_main":
        await query.edit_message_caption(
            caption="dev by @codespaster",
            reply_markup=main_keyboard(),
        )

    elif query.data.startswith("buy_"):
        booster_str = query.data.split("_", 1)[1]
        price = BOOSTER_PRICES.get(booster_str)

        if price is None:
            await query.answer("Неизвестный бустер.", show_alert=True)
            return

        if user_data["multiplier"] >= float(booster_str):
            await query.answer(
                "У тебя уже есть такой или более сильный бустер.",
                show_alert=True
            )
            return

        if user_data["clicks"] < price:
            await query.answer(
                f"Недостаточно кликов. Нужно {price}, у тебя {user_data['clicks']:.2f}.",
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
                f"✅Покупка успешна!\n"
                f"📊Новый бустер: x{user_data['multiplier']:.2f}\n"
                f"💵Оставшиеся клики: {user_data['clicks']:.2f}"
            ),
            reply_markup=main_keyboard(),
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
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
