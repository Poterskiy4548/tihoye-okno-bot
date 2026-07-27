import os
import logging
import sqlite3
import calendar as cal
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
from telegram.error import BadRequest

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip().isdigit()]
PSY_LINK = "https://t.me/Gerta_Kass?text=Привет%21%20Я%20хочу%20записаться%20на%20консультацию"

DB_NAME = "appointments.db"
SLOTS_FRI = ["15:00", "16:30"]
SLOTS_SAT = ["12:00", "13:30"]

MONTHS_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]

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

def book_slot(target_date: str, time: str, user_id: int, username: str) -> bool:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_id FROM appointments WHERE date=? AND time=? AND user_id IS NOT NULL", (target_date, time))
    if c.fetchone():
        conn.close()
        return False
    c.execute("INSERT INTO appointments (date, time, user_id, username, booked_at) VALUES (?,?,?,?,?)",
              (target_date, time, user_id, username, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return True

def cancel_slot(appointment_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE appointments SET user_id=NULL, username=NULL, booked_at=NULL WHERE id=?", (appointment_id,))
    conn.commit()
    conn.close()

def get_upcoming_appointments():
    """Возвращает все будущие записи, где есть user_id."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, date, time, user_id, username FROM appointments WHERE date >= date('now') AND user_id IS NOT NULL ORDER BY date, time")
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_appointments():
    """Абсолютно все записи (для диагностики)."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, date, time, user_id, username FROM appointments ORDER BY date, time")
    rows = c.fetchall()
    conn.close()
    return rows

def get_appointment_by_id(app_id: int):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, date, time, user_id, username FROM appointments WHERE id=?", (app_id,))
    row = c.fetchone()
    conn.close()
    return row

def update_appointment_date(app_id: int, new_date: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE appointments SET date=? WHERE id=?", (new_date, app_id))
    conn.commit()
    conn.close()

def update_appointment_time(app_id: int, new_time: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE appointments SET time=? WHERE id=?", (new_time, app_id))
    conn.commit()
    conn.close()

# ---------- Безопасное редактирование сообщений ----------
async def safe_edit(query, text, parse_mode="HTML", reply_markup=None):
    """Редактирует сообщение, игнорируя ошибку 'Message is not modified'."""
    try:
        await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise

# ---------- Главное меню ----------
async def show_main_menu(update: Update, context):
    user = update.effective_user
    is_admin = user.id in ADMIN_IDS
    keyboard = [
        [InlineKeyboardButton("💰 Цены", callback_data="prices")],
        [InlineKeyboardButton("📅 Слоты / Запись", callback_data="calendar")],
        [InlineKeyboardButton("📝 Как записаться", callback_data="howto")],
        [InlineKeyboardButton("👋 Привет, я тут", url=PSY_LINK)],
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin")])
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
        await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard))

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
        await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
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
        await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "calendar":
        await show_calendar(update, context)

async def back_button(update: Update, context):
    await show_main_menu(update, context)

# ---------- Календарь ----------
async def show_calendar(update: Update, context, year=None, month=None, day=None):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        if query.data and query.data.startswith("cal_"):
            parts = query.data.split("_")[1:]
            if parts[0] == "prev":
                year, month, _ = map(int, parts[1:])
                month -= 1
                if month < 1: month = 12; year -= 1
            elif parts[0] == "next":
                year, month, _ = map(int, parts[1:])
                month += 1
                if month > 12: month = 1; year += 1
            elif parts[0] == "day":
                year, month, day = map(int, parts[1:])
        else:
            today = date.today()
            year, month, _ = today.year, today.month, today.day
    else:
        today = date.today()
        year, month, _ = today.year, today.month, today.day

    cal_matrix = cal.monthcalendar(year, month)
    keyboard = []
    header = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(h, callback_data="none") for h in header])
    for week in cal_matrix:
        row = []
        for d in week:
            if d == 0:
                row.append(InlineKeyboardButton(" ", callback_data="none"))
            else:
                cur_date = date(year, month, d)
                day_str = f"{d:02d}"
                if cur_date.weekday() not in (4, 5):
                    btn_text = f"⬜{day_str}"
                    cb = "none"
                else:
                    free = get_free_slots(cur_date.strftime("%Y-%m-%d"))
                    if free:
                        btn_text = f"🟢{day_str}"
                        cb = f"cal_day_{year}_{month}_{d}"
                    else:
                        btn_text = f"🔴{day_str}"
                        cb = f"cal_day_{year}_{month}_{d}"
                row.append(InlineKeyboardButton(btn_text, callback_data=cb))
        keyboard.append(row)

    nav = [
        InlineKeyboardButton("⬅️", callback_data=f"cal_prev_{year}_{month}_0"),
        InlineKeyboardButton(f"{MONTHS_RU[month]} {year}", callback_data="none"),
        InlineKeyboardButton("➡️", callback_data=f"cal_next_{year}_{month}_0"),
    ]
    keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])

    text = "📅 <b>Календарь</b>\n\nВыберите дату (пт или сб):"
    if day:
        selected_date = f"{year}-{month:02d}-{day:02d}"
        free = get_free_slots(selected_date)
        if free:
            slot_kb = []
            row_slot = []
            for t in free:
                row_slot.append(InlineKeyboardButton(t, callback_data=f"book_{selected_date}_{t}"))
                if len(row_slot) == 2:
                    slot_kb.append(row_slot)
                    row_slot = []
            if row_slot:
                slot_kb.append(row_slot)
            slot_kb.append([InlineKeyboardButton("🔙 К календарю", callback_data=f"cal_prev_{year}_{month}_0")])
            await safe_edit(
                query,
                f"📅 <b>{selected_date}</b>\n\nДоступное время:",
                reply_markup=InlineKeyboardMarkup(slot_kb)
            )
            return

    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def calendar_day(update: Update, context):
    query = update.callback_query
    parts = query.data.split("_")
    year, month, day = map(int, parts[2:])
    await show_calendar(update, context, year=year, month=month, day=day)

# ---------- Запись ----------
async def book_slot_handler(update: Update, context):
    query = update.callback_query
    user = query.from_user
    await query.answer()
    _, target_date, time = query.data.split("_")

    success = book_slot(target_date, time, user.id, user.username or user.full_name)
    if not success:
        await query.answer("Этот слот только что заняли 😔", show_alert=True)
        await show_calendar(update, context)
        return

    date_obj = datetime.strptime(target_date, "%Y-%m-%d")
    confirm_text = (
        f"✅ <b>Запись подтверждена!</b>\n\n"
        f"📅 {date_obj.strftime('%d.%m.%Y')} в {time}\n"
        f"📍 Психолог: <a href='https://t.me/Gerta_Kass'>Gerta_Kass</a>\n\n"
        f"За 24 часа до встречи я пришлю напоминание."
    )
    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="back")]]
    await safe_edit(query, confirm_text, reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- Админ-панель ----------
async def admin_panel(update: Update, context):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await context.bot.send_message(user.id, "⛔ У вас нет доступа.")
        return

    appointments = get_upcoming_appointments()
    if not appointments:
        await context.bot.send_message(user.id, "📭 Пока нет записей.")
        return

    text = "<b>📋 Предстоящие записи:</b>\n\n"
    keyboard = []
    for app in appointments:
        app_id, app_date, app_time, uid, uname = app
        text += f"<b>ID:</b> {app_id} | {app_date} {app_time} | {uname or uid}\n"
        row = [
            InlineKeyboardButton(f"✏️ ID {app_id}", callback_data=f"adm_edit_{app_id}"),
            InlineKeyboardButton(f"❌ ID {app_id}", callback_data=f"cancel_{app_id}"),
        ]
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back")])
    await context.bot.send_message(user.id, text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_edit_appointment(update: Update, context):
    query = update.callback_query
    await query.answer()
    app_id = int(query.data.split("_")[-1])
    app = get_appointment_by_id(app_id)
    if not app:
        await query.edit_message_text("Запись не найдена.")
        return
    _, app_date, app_time, uid, uname = app
    context.user_data["edit_app_id"] = app_id
    text = f"✏️ <b>Редактирование ID {app_id}</b>\n\nДата: {app_date}\nВремя: {app_time}\nКлиент: {uname or uid}"
    keyboard = [
        [InlineKeyboardButton("📅 Изменить дату", callback_data="adm_set_date")],
        [InlineKeyboardButton("⏰ Изменить время", callback_data="adm_set_time")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin")],
    ]
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_set_date_start(update: Update, context):
    query = update.callback_query
    await query.answer()
    context.user_data["edit_state"] = "date"
    await safe_edit(query,
        "📅 Введите новую дату в формате <b>ГГГГ-ММ-ДД</b> (например, 2026-08-02):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="adm_cancel_edit")]])
    )

async def admin_set_time_start(update: Update, context):
    query = update.callback_query
    await query.answer()
    context.user_data["edit_state"] = "time"
    await safe_edit(query,
        "⏰ Введите новое время в формате <b>ЧЧ:ММ</b> (например, 15:00):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="adm_cancel_edit")]])
    )

async def admin_cancel_edit(update: Update, context):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("edit_state", None)
    app_id = context.user_data.get("edit_app_id")
    if app_id:
        await admin_edit_appointment(update, context)
    else:
        await admin_panel(update, context)

async def handle_edit_input(update: Update, context):
    state = context.user_data.get("edit_state")
    app_id = context.user_data.get("edit_app_id")
    if not state or not app_id:
        return False
    value = update.message.text.strip()
    if state == "date":
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text("❌ Неверный формат даты. Попробуйте ещё раз (ГГГГ-ММ-ДД) или нажмите /start.")
            return True
        update_appointment_date(app_id, value)
    elif state == "time":
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError:
            await update.message.reply_text("❌ Неверный формат времени. Попробуйте ещё раз (ЧЧ:ММ) или нажмите /start.")
            return True
        update_appointment_time(app_id, value)
    else:
        return False

    context.user_data.pop("edit_state", None)
    app = get_appointment_by_id(app_id)
    if not app:
        await update.message.reply_text("Запись не найдена.")
        return True
    _, new_date, new_time, uid, uname = app
    text = f"✅ <b>Запись ID {app_id} обновлена</b>\n\nНовая дата: {new_date}\nНовое время: {new_time}\nКлиент: {uname or uid}"
    keyboard = [[InlineKeyboardButton("🔙 Админ-панель", callback_data="admin")]]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return True

async def cancel_appointment(update: Update, context):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await query.answer()
    app_id = int(query.data.split("_")[1])
    cancel_slot(app_id)
    await safe_edit(query, f"✅ Запись ID {app_id} отменена.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Админ-панель", callback_data="admin")]]))

# ---------- Диагностическая команда для проверки записей ----------
async def show_all_bookings(update: Update, context):
    """Показывает ВООБЩЕ ВСЕ записи в базе (только для админов)."""
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    rows = get_all_appointments()
    if not rows:
        await update.message.reply_text("База данных пуста.")
        return
    text = "<b>Все строки в базе:</b>\n\n"
    for r in rows:
        text += f"ID {r[0]}: {r[1]} {r[2]} | user={r[3]} ({r[4]})\n"
    await update.message.reply_text(text, parse_mode="HTML")

async def any_message(update: Update, context):
    if await handle_edit_input(update, context):
        return
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
    app.add_handler(CommandHandler("showdb", show_all_bookings))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(prices|howto|calendar)$"))
    app.add_handler(CallbackQueryHandler(back_button, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(show_calendar, pattern="^cal_"))
    app.add_handler(CallbackQueryHandler(calendar_day, pattern="^cal_day_"))
    app.add_handler(CallbackQueryHandler(book_slot_handler, pattern="^book_"))
    app.add_handler(CallbackQueryHandler(cancel_appointment, pattern="^cancel_"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin$"))
    app.add_handler(CallbackQueryHandler(admin_edit_appointment, pattern="^adm_edit_"))
    app.add_handler(CallbackQueryHandler(admin_set_date_start, pattern="^adm_set_date$"))
    app.add_handler(CallbackQueryHandler(admin_set_time_start, pattern="^adm_set_time$"))
    app.add_handler(CallbackQueryHandler(admin_cancel_edit, pattern="^adm_cancel_edit$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))

    app.run_polling()
