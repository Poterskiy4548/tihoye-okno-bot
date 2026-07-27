import os
import logging
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
# Ссылка на диалог с готовым текстом
PSY_LINK = (
    "https://t.me/Gertakass?text="
    "Привет%E2%80%A6%20хм%2C%20даже%20не%20знаю%2C%20с%20чего%20начать.%20"
    "Может%2C%20просто%20скажи%20что-нибудь%20спокойное%3F%20"
    "Про%20чай%2C%20про%20облака%2C%20про%20что%20угодно.%20"
    "Или%20вообще%20ничего%20%E2%80%94%20можно%20просто%20%C2%ABя%20тут%C2%BB.%20"
    "Мне%20этого%20хватит%2C%20чтобы%20выдохнуть."
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def show_main_menu(update: Update, context):
    """Главное меню с кнопкой «Привет, я тут»."""
    keyboard = [
        [InlineKeyboardButton("💰 Цены", callback_data="prices")],
        [InlineKeyboardButton("📅 Слоты", callback_data="slots")],
        [InlineKeyboardButton("📝 Как записаться", callback_data="howto")],
        [InlineKeyboardButton("👋 Привет, я тут", url=PSY_LINK)],
    ]
    text = (
        "🕊 <b>Тихое окно</b>\n"
        "кабинет психолога-консультанта\n\n"
        "Выберите, что вас интересует 👇\n"
        "Или просто дайте знать, что вы здесь — нажмите «Привет, я тут»."
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def start(update: Update, context):
    await show_main_menu(update, context)

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
    elif query.data == "slots":
        text = (
            "📅 <b>Доступные слоты</b>\n\n"
            "• <b>Пятница:</b> 15:00 или 16:30\n"
            "• <b>Суббота:</b> 12:00 или 13:30\n\n"
            "По будням бывают свободные окна обычно после 14:00.\n"
            "Точные свободные слоты пришлю в ЛС — напиши мне, какой день ближе."
        )
    else:  # howto
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

async def back_button(update: Update, context):
    await show_main_menu(update, context)

async def any_message(update: Update, context):
    text = (
        "🤖 Я пока умею только отвечать по кнопкам.\n"
        "Выберите команду из меню или просто нажмите «Привет, я тут» 👇"
    )
    keyboard = [[InlineKeyboardButton("👋 Привет, я тут", url=PSY_LINK)]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

if __name__ == "__main__":
    proxy_url = os.getenv("SOCKS5_PROXY")
    builder = ApplicationBuilder().token(BOT_TOKEN)
    if proxy_url:
        logger.info(f"🔁 Использую прокси: {proxy_url}")
        builder.proxy(proxy_url).get_updates_proxy(proxy_url)
    app = builder.build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^(prices|slots|howto)$"))
    app.add_handler(CallbackQueryHandler(back_button, pattern="^back$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))
    app.run_polling()
