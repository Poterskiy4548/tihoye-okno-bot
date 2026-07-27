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
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 Цены", callback_data="prices")],
        [InlineKeyboardButton("📅 Слоты", callback_data="slots")],
        [InlineKeyboardButton("📝 Как записаться", callback_data="howto")],
    ]
    await update.message.reply_text(
        "🕊 <b>Тихое окно</b> — кабинет психолога-консультанта.\n\nВыберите, что вас интересует 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    else:
        text = (
            "📝 <b>Как записаться</b>\n\n"
            "Чтобы забронировать время, напишите мне в ЛС.\n"
            "Если все слоты заняты, оставьте контакты — я напишу, когда появится окно."
        )
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

async def back_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("💰 Цены", callback_data="prices")],
        [InlineKeyboardButton("📅 Слоты", callback_data="slots")],
        [InlineKeyboardButton("📝 Как записаться", callback_data="howto")],
    ]
    await query.edit_message_text(
        "🕊 <b>Тихое окно</b> — кабинет психолога-консультанта.\n\nВыберите, что вас интересует 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Я пока умею только по кнопкам. Выберите команду из меню или напишите напрямую в ЛС — я помогу."
    )

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
