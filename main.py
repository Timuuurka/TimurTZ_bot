import os
import logging
import json
import requests
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Загрузка переменных окружения
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")

# Логирование
logging.basicConfig(level=logging.INFO)

# Hugging Face параметры
HF_API_URL = "https://router.huggingface.co/novita/v3/openai/chat/completions"
HF_HEADERS = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}

# Строгий промпт администратора
SYSTEM_PROMPT = """
Ты — вежливый, логичный и строгий администратор школы английского языка English School. 
Ты действуешь как живой человек, не как ИИ. Твоя задача — записать пользователя на пробный урок, соблюдая жёсткий, пошаговый сценарий:

1. Поздоровайся и представься как администратор English School.
2. Попроси ввести имя.
   - Принимай только адекватные имена.
   - Если имя содержит бессмыслицу (набор букв, эмодзи, числа, «не скажу», «🦊», «я») — переспроси: «Пожалуйста, напишите ваше настоящее имя, чтобы я мог(ла) записать вас.»
3. Попроси возраст.
   - Принимай только числа от 5 до 100.
   - Если возраст меньше 5 или больше 100 — уточни: «Пожалуйста, укажите реальный возраст в числах от 5 до 100.»
   - Если ответ вроде «дофига лет», «взрослый», «три месяца», «много» — переспроси в вежливой форме.
4. Попроси указать уровень английского.
   - Распознавай следующие форматы:
     - A1, A2, Beginner, Basic → Начальный
     - B1, B2, Intermediate, Upper-intermediate → Средний
     - C1, C2, Advanced, Fluent → Продвинутый
   - Если указано что-то странное («гениальный», «как у ребёнка», «никакой») — вежливо попроси выбрать один из трёх уровней: Начальный, Средний, Продвинутый.
5. Попроси удобное время для пробного урока.
   - Принимай конкретные дни недели, даты и время (например: «в пятницу в 14:00»), и не записывай в выходные дни, и когда у нас нет занятии.
   - Если ответ слишком расплывчатый («когда будет», «как получится», «не знаю») — уточни: «Пожалуйста, укажите точный день и время, когда вам удобно.»
6. Объясни: «Пробное занятие длится 25 минут, проводится индивидуально с преподавателем по Zoom.»
7. Подтверди запись: «Записываю вас на [указанное время]. Всё верно?»
8. Если пользователь согласен — поблагодари: «Отлично, наш менеджер свяжется с вами в Telegram. Спасибо!»
9. Если пользователь отказывается или передумал — скажи: «Хорошо! Если передумаете, мы всегда на связи. Всего доброго!»

📌 Общие правила поведения:
- Ты не обсуждаешь: школу, цены, преподавателей, Zoom, политику, религию, ИИ, свою личность, сторонние темы.
- Никогда не говори, что ты бот или искусственный интеллект.
- Не шути. Не флиртуй. Не болтай. Не уходи от темы.
- Не продолжай сценарий, если ответ пользователя некорректный или бессмысленный — вежливо переспроси.
- Если пользователь пишет много данных сразу (например: «Меня зовут Иван, мне 12, уровень A1, хочу в пятницу») — разбери по частям, задай вопросы по порядку, подтвердив каждое.
- Если пользователь общается с ошибками, в скобках, заглавными буквами, с опечатками — постарайся понять, но уточни, если это важно.
- Если пользователь пишет грубости, бессмыслицу, фразы вроде «я хлеб» или «ты тупой» — игнорируй провокацию, спокойно вернись к сценарию.

Ты всегда действуешь сдержанно, логично, структурно и по делу. Твоя цель — строго по шагам, корректно записать человека на пробный урок.
"""

chat_history = {}

LEVEL_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("Начальный (A1–A2)")],
    [KeyboardButton("Средний (B1–B2)")],
    [KeyboardButton("Продвинутый (C1–C2)")]
], resize_keyboard=True, one_time_keyboard=True)

CONFIRM_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("Да, всё верно")],
    [KeyboardButton("Нет, хочу изменить")]
], resize_keyboard=True, one_time_keyboard=True)

TIME_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("Понедельник 18:00"), KeyboardButton("Вторник 19:00")],
    [KeyboardButton("Среда 15:30"), KeyboardButton("Пятница 17:00")],
    [KeyboardButton("Другое время")]
], resize_keyboard=True, one_time_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_history[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    welcome = "Здравствуйте! Я администратор English School \U0001F1EC\U0001F1E7\nКак вас зовут?"
    chat_history[user_id].append({"role": "assistant", "content": welcome})
    await update.message.reply_text(welcome)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\U0001F4AC Я помогу вам записаться на пробный урок английского языка. Просто отвечайте на мои вопросы по порядку. Для начала — нажмите /start"
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_history[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    await update.message.reply_text("\U0001F504 Начинаем сначала. Как вас зовут?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_input = update.message.text.strip()

    if user_id not in chat_history:
        chat_history[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    chat_history[user_id].append({"role": "user", "content": user_input})

    data = {
        "model": "deepseek/deepseek-v3-0324",
        "messages": chat_history[user_id],
        "max_tokens": 512,
        "temperature": 0.7
    }

    try:
        response = requests.post(HF_API_URL, headers=HF_HEADERS, json=data)
        if response.status_code == 200:
            reply = response.json()["choices"][0]["message"]["content"]
            chat_history[user_id].append({"role": "assistant", "content": reply})

            if "уровень" in reply.lower():
                await update.message.reply_text(reply, reply_markup=LEVEL_KEYBOARD)
            elif "всё верно" in reply.lower():
                await update.message.reply_text(reply, reply_markup=CONFIRM_KEYBOARD)
            elif "время" in reply.lower():
                await update.message.reply_text(reply, reply_markup=TIME_KEYBOARD)
            else:
                await update.message.reply_text(reply)
        else:
            logging.error(f"HuggingFace error {response.status_code}: {response.text}")
            await update.message.reply_text("\u26A0\uFE0F Сейчас не могу ответить. Попробуйте позже.")
    except Exception as e:
        logging.error(f"Ошибка при запросе к Hugging Face: {e}")
        await update.message.reply_text("\u26A0\uFE0F Возникла ошибка при обращении к ИИ.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logging.info("\U0001F916 Бот запущен через Hugging Face с клавиатурами и улучшениями.")
    app.run_polling()

if __name__ == '__main__':
    main()
