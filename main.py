import os
import logging
import sqlite3
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip().isdigit()]
PSY_LINK = "https://t.me/Gerta_Kass?text=Привет%21%20Я%20хочу%20записаться%20на%20консультацию"

DB_NAME = "appointments.db"
SLOTS_FRI = ["15:00", "16:30"]
SLOTS_SAT = ["12:00", "13:30"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------- База данных ----------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        user_id INTEGER,
        username TEXT,
        booked_at TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

# ---------- Вспомогательные функции ----------
def get_free_slots(target_date: str) -> list:
    day_of_week = datetime.strptime(target_date, "%Y-%m-%d").weekday()
    if day_of_week == 4:
        all_slots = SLOTS_FRI
    elif day_of_week == 5:
        all_slots = SLOTS_SAT
    else:
        return []

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT time FROM appointments WHERE date=? AND user_id IS NOT NULL", (target_date,))
    booked = [row[0] for row in c.fetchall()]
    conn.close()
    return [s for s in all_slots if s not in booked]

def book_slot(target_date: str, time: str, user_id: int, username: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO appointments (date, time, user_id, username, booked_at) VALUES (?,?,?,?,?)",
              (target_date, time, user_id, username, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def cancel_slot(appointment_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE appointments SET user_id=NULL, username=NULL, booked_at=NULL WHERE id=?", (appointment_id,))
    conn.commit()
    conn.close()

def get_upcoming_appointments():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, date, time, user_id, username FROM appointments WHERE date >= date('now') AND user_id IS NOT NULL ORDER BY date, time")
    rows = c.fetchall()
    conn.close()
    return rows

# ---------- Главное меню ----------
async def show_main_menu(update: Update, context):
    keyboard = [
        [InlineKeyboardButton("💰 Цены", callback_data="prices")],
        [InlineKeyboardButton("📅 Слоты / Запись", callback_data="calendar")],
        [InlineKeyboardButton("📝 Как записаться", callback_data="howto")],
        [InlineKeyboardButton("👋 Привет, я тут", url=PSY_LINK)],
    ]
    text = (
        "🕊 <b>Тихое окно</b>\n"
        "кабинет психолога-консультанта\n\n"
        "Выберите, что вас интересует 👇"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def start(update: Update, context):
    await show_main_menu(update, context)

# ---------- Обработчики кнопок ----------
async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "prices":
        text = (
            "💰 <b>Стоимость консультаций</b>\n\n"
            "• <b>Переписка</b> (работа в выделенное время) — 1300 ₽ за сессию\n"
            "• <b>Первая сессия</b> — скидка 25% (975 ₽)\n"
            "• <b>Экспресс</b> (ограниченный объём сообщений) — 800 ₽\n"
            "• <b>Пакет из 4 сессий</b> — 4800 ₽ (по 1200 ₽ за встречу).\n"
            "   Скидка на первую сессию не суммируется с пакетом."
        )
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "howto":
        text = (
            "📝 <b>Как записаться</b>\n\n"
            "Чтобы забронировать время, напишите мне в ЛС.\n"
            "Если все слоты заняты, оставьте контакты — я напишу, когда появится окно."
        )
        keyboard = [
            [InlineKeyboardButton("👋 Привет, я тут", url=PSY_LINK)],
            [InlineKeyboardButton("🔙 Назад", callback_data="back")],
        ]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "calendar":
        await show_calendar(query)

async def back_button(update: Update, context):
    await show_main_menu(update, context)

# ---------- Календарь ----------
async def show_calendar(query, offset=0):
    today = date.today()
    dates = []
    for i in range(offset * 7, (offset + 4) * 7):
        d = today + timedelta(days=i)
        if d.weekday() == 4 or d.weekday() == 5:
            dates.append(d)

    keyboard = []
    for d in dates:
        day_name = "Пт" if d.weekday() == 4 else "Сб"
        free = get_free_slots(d.strftime("%Y-%m-%d"))
        status = "🟢" if free else "🔴"
        keyboard.append([InlineKeyboardButton(
            f"{status} {day_name} {d.strftime('%d.%m')}",
            callback_data=f"pick_{d.strftime('%Y-%m-%d')}"
        )])

    nav_buttons = []
    if offset > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Раньше", callback_data=f"cal_offset_{offset - 1}"))
    nav_buttons.append(InlineKeyboardButton("Позже ➡️", callback_data=f"cal_offset_{offset + 1}"))
    nav_buttons.append(InlineKeyboardButton("🔙 Назад", callback_data="back"))
    keyboard.append(nav_buttons)

    text = (
        "📅 <b>Выберите дату:</b>\n"
        "🟢 — есть свободные слоты\n"
        "🔴 — всё занято\n\n"
        "Нажимайте на дату, чтобы посмотреть доступное время."
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def calendar_pick(update: Update, context):
    query = update.callback_query
    await query.answer()
    target_date = query.data.split("_")[1]
    free = get_free_slots(target_date)
    if not free:
        await query.answer("На эту дату все слоты заняты 😔", show_alert=True)
        return

    # Сетка кнопок: по 2 в ряд
    keyboard = []
    row = []
    for t in free:
        row.append(InlineKeyboardButton(f"⏰ {t}", callback_data=f"book_{target_date}_{t}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Назад к календарю", callback_data="calendar")])

    date_obj = datetime.strptime(target_date, "%Y-%m-%d")
    day_name = "пятница" if date_obj.weekday() == 4 else "суббота"
    text = f"📅 <b>{date_obj.strftime('%d.%m.%Y')}</b> ({day_name})\n\nДоступное время:"
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def book_slot_handler(update: Update, context):
    query = update.callback_query
    user = query.from_user
    await query.answer()
    _, target_date, time = query.data.split("_")
    free = get_free_slots(target_date)
    if time not in free:
        await query.answer("Этот слот только что заняли 😔", show_alert=True)
        await show_calendar(query)
        return

    book_slot(target_date, time, user.id, user.username or user.full_name)
    date_obj = datetime.strptime(target_date, "%Y-%m-%d")
    confirm_text = (
        f"✅ <b>Запись подтверждена!</b>\n\n"
        f"📅 {date_obj.strftime('%d.%m.%Y')} в {time}\n"
        f"📍 Психолог: <a href='https://t.me/Gerta_Kass'>Gerta_Kass</a>\n\n"
        f"За 24 часа до встречи я пришлю напоминание."
    )
    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="back")]]
    await query.edit_message_text(confirm_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- Админ-панель ----------
async def admin_panel(update: Update, context):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return
    appointments = get_upcoming_appointments()
    if not appointments:
        await update.message.reply_text("📭 Пока нет записей.")
        return
    text = "<b>📋 Предстоящие записи:</b>\n\n"
    keyboard = []
    for app in appointments:
        app_id, app_date, app_time, uid, uname = app
        text += f"<b>ID:</b> {app_id} | {app_date} {app_time} | {uname or uid}\n"
        keyboard.append([InlineKeyboardButton(
            f"❌ Отменить ID {app_id} ({app_date} {app_time})",
            callback_data=f"cancel_{app_id}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back")])
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def cancel_appointment(update: Update, context):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await query.answer()
    app_id = int(query.data.split("_")[1])
    cancel_slot(app_id)
    await query.edit_message_text(
        f"✅ Запись ID {app_id} отменена.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Админ-панель", callback_data="admin")]])
    )

# ---------- Заглушка ----------
async def any_message(update: Update, context):
    text = (
        "🤖 Я пока умею только отвечать по кнопкам.\n"
        "Выберите команду из меню или нажмите «Привет, я тут» 👇"
    )
    keyboard = [[InlineKeyboardButton("👋 Привет, я тут", url=PSY_LINK)]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- Запуск ----------
if __name__ == "__main__":
    proxy_url = os.getenv("SOCKS5_PROXY")
    builder = ApplicationBuilder().token(BOT_TOKEN)
    if proxy_url:
        logger.info(f"🔁 Использую прокси: {proxy_url}")
        builder.proxy(proxy_url).get_updates_proxy(proxy_url)
    app = builder.build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(prices|howto|calendar)$"))
    app.add_handler(CallbackQueryHandler(back_button, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(show_calendar, pattern="^cal_offset_"))
    app.add_handler(CallbackQueryHandler(calendar_pick, pattern="^pick_"))
    app.add_handler(CallbackQueryHandler(book_slot_handler, pattern="^book_"))
    app.add_handler(CallbackQueryHandler(cancel_appointment, pattern="^cancel_"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))

    app.run_polling()
