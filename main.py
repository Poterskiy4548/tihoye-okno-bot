import os
import logging
import sqlite3
import calendar as cal
from datetime import datetime, date, timedelta
from html import escape as html_escape

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

# ---------- Конфигурация ----------
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
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        booked_at TEXT NOT NULL
    )""")
    # Уникальность слота: только одна активная запись на дату+время
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_appointment_slot ON appointments(date, time)")
    conn.commit()
    conn.close()

init_db()

def get_free_slots(target_date_str: str) -> list:
    """Возвращает список доступных слотов (времени) на указанную дату."""
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        return []
    if target_date < date.today():
        return []
    day_of_week = target_date.weekday()
    if day_of_week == 4:
        all_slots = SLOTS_FRI
    elif day_of_week == 5:
        all_slots = SLOTS_SAT
    else:
        return []
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT time FROM appointments WHERE date=?", (target_date_str,))
    booked = [row[0] for row in c.fetchall()]
    conn.close()
    return [s for s in all_slots if s not in booked]

def book_slot(target_date: str, time: str, user_id: int, username: str) -> bool:
    """Пытается забронировать слот. Возвращает True в случае успеха."""
    conn = sqlite3.connect(DB_NAME)
    try:
        # Проверяем, не прошла ли дата, и день недели
        try:
            slot_date = datetime.strptime(target_date, "%Y-%m-%d").date()
            if slot_date < date.today():
                return False
            if slot_date.weekday() not in (4, 5):
                return False
        except ValueError:
            return False
        # Транзакция с вставкой, которая упадёт при нарушении уникальности
        conn.execute("BEGIN EXCLUSIVE")
        c = conn.cursor()
        c.execute("INSERT INTO appointments (date, time, user_id, username, booked_at) VALUES (?,?,?,?,?)",
                  (target_date, time, user_id, username, datetime.now().isoformat()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.rollback()
        return False
    finally:
        conn.close()

def cancel_slot(appointment_id: int):
    """Удаляет запись (освобождает слот)."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM appointments WHERE id=?", (appointment_id,))
    conn.commit()
    conn.close()

def get_upcoming_appointments():
    """Возвращает все будущие (включая сегодняшние) активные записи."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, date, time, user_id, username FROM appointments WHERE date >= date('now') ORDER BY date, time")
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_appointments():
    """Все записи (для диагностики)."""
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

def clear_all_appointments():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM appointments")
    conn.commit()
    conn.close()

# ---------- Безопасное редактирование сообщений ----------
async def safe_edit(query, text, parse_mode="HTML", reply_markup=None):
    try:
        await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise

def safe_html(text: str) -> str:
    """Экранирует HTML-символы в строке."""
    return html_escape(text, quote=False)

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

async def help_command(update: Update, context):
    text = (
        "ℹ️ <b>Помощь</b>\n\n"
        "Этот бот позволяет записаться на консультацию.\n"
        "Используйте кнопки меню для навигации.\n"
        "По любым вопросам свяжитесь с психологом напрямую."
    )
    await update.message.reply_text(text, parse_mode="HTML")

# ---------- Обработчики кнопок ----------
async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "prices":
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

    elif data == "howto":
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

    elif data == "calendar":
        await show_calendar(update, context)

    elif data == "admin":
        await admin_panel(update, context)

    elif data == "none":
        await query.answer("Этот день недоступен", show_alert=True)

async def back_button(update: Update, context):
    await show_main_menu(update, context)

# ---------- Календарь ----------
async def show_calendar(update: Update, context, year=None, month=None, day=None):
    query = update.callback_query
    await query.answer()
    if query.data and query.data.startswith("cal_"):
        parts = query.data.split("_")[1:]
        try:
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
        except (ValueError, IndexError):
            # Некорректные данные — возвращаем на сегодня
            today = date.today()
            year, month, day = today.year, today.month, None
    else:
        today = date.today()
        year, month = today.year, today.month
        day = None

    if day is not None:
        try:
            selected_date = date(year, month, day)
            if selected_date < date.today():
                await query.answer("Нельзя выбрать прошедшую дату", show_alert=True)
                return
        except ValueError:
            await query.answer("Некорректная дата", show_alert=True)
            return

    cal_matrix = cal.monthcalendar(year, month)
    keyboard = []
    header = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(h, callback_data="none") for h in header])
    today = date.today()

    for week in cal_matrix:
        row = []
        for d in week:
            if d == 0:
                row.append(InlineKeyboardButton(" ", callback_data="none"))
            else:
                cur_date = date(year, month, d)
                day_str = f"{d:02d}"
                if cur_date < today:
                    # Прошедшая дата — всегда неактивна
                    btn_text = f"⬛{day_str}"
                    cb = "none"
                elif cur_date.weekday() not in (4, 5):
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
    if day is not None:
        selected_date_str = f"{year}-{month:02d}-{day:02d}"
        free = get_free_slots(selected_date_str)
        if free:
            slot_kb = []
            row_slot = []
            for t in free:
                row_slot.append(InlineKeyboardButton(t, callback_data=f"book_{selected_date_str}_{t}"))
                if len(row_slot) == 2:
                    slot_kb.append(row_slot)
                    row_slot = []
            if row_slot:
                slot_kb.append(row_slot)
            slot_kb.append([InlineKeyboardButton("🔙 К календарю", callback_data=f"cal_prev_{year}_{month}_0")])
            await safe_edit(
                query,
                f"📅 <b>{selected_date_str}</b>\n\nДоступное время:",
                reply_markup=InlineKeyboardMarkup(slot_kb)
            )
            return
        else:
            # Красный день: нет слотов
            text = f"📅 <b>{selected_date_str}</b>\n\nК сожалению, на эту дату все слоты заняты."
            keyboard = [[InlineKeyboardButton("🔙 К календарю", callback_data=f"cal_prev_{year}_{month}_0")]]
            await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
            return

    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard))

async def calendar_day(update: Update, context):
    query = update.callback_query
    parts = query.data.split("_")
    try:
        year, month, day = map(int, parts[2:])
    except (ValueError, IndexError):
        await query.answer("Ошибка данных", show_alert=True)
        return
    await show_calendar(update, context, year=year, month=month, day=day)

# ---------- Запись ----------
async def book_slot_handler(update: Update, context):
    query = update.callback_query
    user = query.from_user
    await query.answer()
    try:
        _, target_date, time = query.data.split("_")
    except ValueError:
        await query.answer("Некорректный запрос", show_alert=True)
        return

    username = user.username or user.full_name
    success = book_slot(target_date, time, user.id, username)
    if not success:
        await query.answer("Этот слот только что заняли или дата недоступна 😔", show_alert=True)
        await show_calendar(update, context)
        return

    date_obj = datetime.strptime(target_date, "%Y-%m-%d")
    safe_username = safe_html(username)
    confirm_text = (
        f"✅ <b>Запись подтверждена!</b>\n\n"
        f"📅 {date_obj.strftime('%d.%m.%Y')} в {time}\n"
        f"📍 Психолог: <a href='https://t.me/Gerta_Kass'>Gerta_Kass</a>\n"
        f"👤 {safe_username}\n\n"
        f"За 24 часа до встречи я пришлю напоминание."
    )
    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="back")]]
    await safe_edit(query, confirm_text, reply_markup=InlineKeyboardMarkup(keyboard))

# ---------- Админ-панель ----------
async def admin_panel(update: Update, context):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        if update.callback_query:
            await update.callback_query.answer("⛔ У вас нет доступа.", show_alert=True)
        else:
            await context.bot.send_message(user.id, "⛔ У вас нет доступа.")
        return

    appointments = get_upcoming_appointments()
    keyboard = []
    if appointments:
        text_lines = ["<b>📋 Предстоящие записи:</b>", ""]
        for app in appointments:
            app_id, app_date, app_time, uid, uname = app
            safe_uname = safe_html(uname)
            text_lines.append(f"<b>ID:</b> {app_id} | {app_date} {app_time} | {safe_uname} (ID {uid})")
            row = [
                InlineKeyboardButton(f"✏️ ID {app_id}", callback_data=f"adm_edit_{app_id}"),
                InlineKeyboardButton(f"❌ ID {app_id}", callback_data=f"cancel_{app_id}"),
            ]
            keyboard.append(row)
        text = "\n".join(text_lines)
    else:
        text = "📭 Пока нет записей."

    keyboard.append([InlineKeyboardButton("🗑 Очистить историю записей", callback_data="clear_history")])
    keyboard.append([InlineKeyboardButton("🔙 Главное меню", callback_data="back")])

    if update.callback_query:
        query = update.callback_query
        await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await context.bot.send_message(user.id, text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def clear_history_handler(update: Update, context):
    query = update.callback_query
    user = query.from_user
    if user.id not in ADMIN_IDS:
        await query.answer("⛔ Нет доступа", show_alert=True)
        return

    await query.answer()
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить всё", callback_data="clear_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="admin"),
        ]
    ]
    await safe_edit(query, "⚠️ Вы уверены, что хотите удалить <b>ВСЕ</b> записи из базы данных?",
                    reply_markup=InlineKeyboardMarkup(keyboard))

async def clear_confirm_handler(update: Update, context):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("⛔ Нет доступа", show_alert=True)
        return

    clear_all_appointments()
    await query.answer("✅ История очищена.")
    await admin_panel(update, context)

async def admin_edit_appointment(update: Update, context):
    query = update.callback_query
    await query.answer()
    try:
        app_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await safe_edit(query, "Некорректный ID записи.")
        return
    app = get_appointment_by_id(app_id)
    if not app:
        await safe_edit(query, "Запись не найдена.")
        return
    _, app_date, app_time, uid, uname = app
    context.user_data["edit_app_id"] = app_id
    safe_uname = safe_html(uname)
    text = f"✏️ <b>Редактирование ID {app_id}</b>\n\nДата: {app_date}\nВремя: {app_time}\nКлиент: {safe_uname} (ID {uid})"
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
        "📅 Введите новую дату в формате <b>ГГГГ-ММ-ДД</b> (например, 2026-08-02):\n"
        "<i>Только пятница или суббота, не раньше сегодняшнего дня.</i>",
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
    error = None
    if state == "date":
        try:
            new_date = datetime.strptime(value, "%Y-%m-%d").date()
            if new_date < date.today():
                error = "Дата не может быть в прошлом."
            elif new_date.weekday() not in (4, 5):
                error = "Дата должна быть пятницей или субботой."
            else:
                update_appointment_date(app_id, value)
        except ValueError:
            error = "Неверный формат даты. Используйте ГГГГ-ММ-ДД."
    elif state == "time":
        try:
            datetime.strptime(value, "%H:%M")
            update_appointment_time(app_id, value)
        except ValueError:
            error = "Неверный формат времени. Используйте ЧЧ:ММ."
    else:
        return False

    if error:
        await update.message.reply_text(f"❌ {error} Попробуйте ещё раз или нажмите /start.")
        return True

    context.user_data.pop("edit_state", None)
    app = get_appointment_by_id(app_id)
    if not app:
        await update.message.reply_text("Запись не найдена.")
        return True
    _, new_date, new_time, uid, uname = app
    safe_uname = safe_html(uname)
    text = (f"✅ <b>Запись ID {app_id} обновлена</b>\n\n"
            f"Новая дата: {new_date}\nНовое время: {new_time}\n"
            f"Клиент: {safe_uname} (ID {uid})")
    keyboard = [[InlineKeyboardButton("🔙 Админ-панель", callback_data="admin")]]
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return True

async def cancel_appointment(update: Update, context):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("⛔ Нет доступа", show_alert=True)
        return
    await query.answer()
    try:
        app_id = int(query.data.split("_")[1])
    except (ValueError, IndexError):
        await query.answer("Ошибка ID", show_alert=True)
        return
    cancel_slot(app_id)
    await safe_edit(query, f"✅ Запись ID {app_id} отменена.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Админ-панель", callback_data="admin")]]))

# ---------- Обработчик текстовых сообщений ----------
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

    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(prices|howto|calendar|admin|none)$"))
    app.add_handler(CallbackQueryHandler(back_button, pattern="^back$"))
    app.add_handler(CallbackQueryHandler(show_calendar, pattern="^cal_"))
    app.add_handler(CallbackQueryHandler(calendar_day, pattern="^cal_day_"))
    app.add_handler(CallbackQueryHandler(book_slot_handler, pattern="^book_"))
    app.add_handler(CallbackQueryHandler(cancel_appointment, pattern="^cancel_"))
    app.add_handler(CallbackQueryHandler(admin_edit_appointment, pattern="^adm_edit_"))
    app.add_handler(CallbackQueryHandler(admin_set_date_start, pattern="^adm_set_date$"))
    app.add_handler(CallbackQueryHandler(admin_set_time_start, pattern="^adm_set_time$"))
    app.add_handler(CallbackQueryHandler(admin_cancel_edit, pattern="^adm_cancel_edit$"))
    app.add_handler(CallbackQueryHandler(clear_history_handler, pattern="^clear_history$"))
    app.add_handler(CallbackQueryHandler(clear_confirm_handler, pattern="^clear_confirm$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))

    app.run_polling()
