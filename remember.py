import telegram
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, Filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup
from database import add_reminder, check_reminders, cursor, conn
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pytz import timezone
import calendar
import os
import logging


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
load_dotenv()
telegram_token = os.getenv("TELEGRAM_TOKEN")


def send_welcome_message(update, context: CallbackContext):

    update.message.reply_text(
        'Привет! Этот бот умеет вовремя тебе напомнить о чем-либо.\n'
        'Чтобы создать напоминание введи команду /start_remind.\n'
        'Напиши любое текстовое сообщение и он отправит тебе то, о чем ты напишешь. \n'
        'Выбери год, месяц, день и время когда тебе прислать сообщение и он тебе напомнит вовремя.\n'
        'Только не блокируй бот, он так не сможет тебя вовремя предупредить!\n'
        'Если вдруг бот перестал работать или что-то поломалось, обращайся к @just_erdni\n',
    )


def start(update, context: CallbackContext):
    chat_id = update.message.chat_id

    # Проверяем, есть ли этот пользователь в базе
    cursor.execute("SELECT has_started FROM users WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()

    # Если пользователя нет в базе или он еще не начал, отправляем приветственное сообщение
    if row is None:
        cursor.execute("INSERT INTO users (chat_id, has_started) VALUES (?, ?)", (chat_id, True))
        conn.commit()
        send_welcome_message(update, context)
    elif not row[0]:
        cursor.execute("UPDATE users SET has_started = ? WHERE chat_id = ?", (True, chat_id))
        conn.commit()
        send_welcome_message(update, context)


def start_remind(update: Update, context: CallbackContext):
    context.user_data['creating_reminder'] = True  # Устанавливаем флаг
    try:
        update.message.reply_text('Введи текст напоминания:', timeout=10)
    except telegram.error.TimedOut:
        logging.warning('Timed out while sending a message')


def build_year_menu():  # Функция для создания меню с годами
    keyboard = []
    current_year = datetime.now().year
    years_row = [InlineKeyboardButton(str(year), callback_data=f'year_{year}') for year in
                 range(current_year, current_year + 2)]
    keyboard.append(years_row)
    return InlineKeyboardMarkup(keyboard)


def build_month_menu():  # Функция для создания меню с месяцами
    keyboard = []
    for i in range(0, 12, 3):
        months_row = [InlineKeyboardButton(calendar.month_name[month], callback_data=f'month_{month}') for month in
                      range(i + 1, i + 4)]
        keyboard.append(months_row)
    return InlineKeyboardMarkup(keyboard)


def build_days_menu(selected_year, selected_month):
    last_day = 31  # Дефолтное значение, если что-то пойдет не так
    if selected_year is None or selected_month is None:
        # Логирование или сообщение об ошибке
        print(f"selected_year: {selected_year}, selected_month: {selected_month}")
    else:
        _, last_day = calendar.monthrange(selected_year, selected_month)

    # Создаем список дней на основе последнего дня
    keyboard = []
    days_row = []
    for day in range(1, last_day + 1):
        days_row.append(InlineKeyboardButton(str(day), callback_data=f'day_{day}'))
        if len(days_row) == 7:  # Например, 7 дней в строке
            keyboard.append(days_row)
            days_row = []

    if days_row:  # Если остались незаполненные дни
        keyboard.append(days_row)

    return InlineKeyboardMarkup(keyboard)


def button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data.startswith("year_"):
        selected_year = int(data.split("_")[1])
        context.user_data['year'] = selected_year
        reply_markup = build_month_menu()  # После выбора года показываем меню с месяцами
        query.message.reply_text('Выбери месяц:', reply_markup=reply_markup)

    elif data.startswith("day_"):
        selected_day = int(data.split("_")[1])
        context.user_data['day'] = selected_day
        reply_markup = build_hour_menu()  # теперь вызываем меню для выбора часа
        query.message.reply_text('Выбери час:', reply_markup=reply_markup)

    elif data.startswith("month_"):
        selected_month = int(data.split("_")[1])
        context.user_data['month'] = selected_month
        selected_year = context.user_data.get('year')
        reply_markup = build_days_menu(selected_year, selected_month)
        query.message.reply_text('Выбери день:', reply_markup=reply_markup)

    elif data.startswith("hour_"):  # новый блок для обработки часа
        selected_hour = int(data.split("_")[1])
        context.user_data['hour'] = selected_hour
        reply_markup = build_minute_menu()  # теперь вызываем меню для выбора минут
        query.message.reply_text('Выбери минуты:', reply_markup=reply_markup)

    elif data.startswith("minute_"):  # новый блок для обработки минут
        selected_minute = int(data.split("_")[1])
        context.user_data['minute'] = selected_minute

        # Собираем всю информацию в одну datetime переменную
        moscow = timezone('Europe/Moscow')
        selected_year = context.user_data.get('year')
        selected_month = context.user_data.get('month')
        selected_day = context.user_data.get('day')
        selected_hour = context.user_data.get('hour')  # забираем час из context.user_data
        reminder_datetime = datetime(year=selected_year, month=selected_month, day=selected_day,
                                     hour=selected_hour, minute=selected_minute)
        reminder_datetime = moscow.localize(reminder_datetime)

        # Сохраняем в бд
        text = context.user_data.get('text', 'Это тестовое напоминание!')
        chat_id = query.message.chat_id
        add_reminder(chat_id, text, reminder_datetime.strftime('%Y-%m-%d %H:%M:%S'))
        query.message.reply_text(f"Напоминание установлено на {reminder_datetime}")


def build_hour_menu():
    keyboard = []
    row = []
    for hour in range(0, 24):  # от 0 до 23
        hour_str = f"{hour:02d}"
        row.append(InlineKeyboardButton(hour_str, callback_data=f'hour_{hour_str}'))

        if len(row) == 6:  # Если в строке уже 6 кнопок, добавляем строку в keyboard и очищаем row
            keyboard.append(row)
            row = []

    if len(row) > 0:  # Если остались кнопки в row, добавляем их в keyboard
        keyboard.append(row)

    return InlineKeyboardMarkup(keyboard)


def build_minute_menu():
    keyboard = []
    row = []
    for minute in range(0, 60, 5):  # шаг в 5 минут
        minute_str = f"{minute:02d}"
        row.append(InlineKeyboardButton(minute_str, callback_data=f'minute_{minute_str}'))

        if len(row) == 6:  # Если в строке уже 6 кнопок, добавляем строку в keyboard и очищаем row
            keyboard.append(row)
            row = []

    if len(row) > 0:  # Если остались кнопки в row, добавляем их в keyboard
        keyboard.append(row)

    return InlineKeyboardMarkup(keyboard)


def handle_text(update: Update, context: CallbackContext):
    # Здесь сохраняем текст напоминания в context.user_data
    if not context.user_data.get('creating_reminder'):  # Проверяем флаг
        return
    context.user_data['text'] = update.message.text
    context.user_data['creating_reminder'] = False  # Сбрасываем флаг
    reply_markup = build_year_menu()  # здесь теперь только год
    update.message.reply_text('Выбери год:', reply_markup=reply_markup)


updater = Updater(telegram_token, use_context=True)
job_queue = updater.job_queue
job_queue.run_repeating(check_reminders, interval=timedelta(minutes=1))
dp = updater.dispatcher

dp.add_handler(CallbackQueryHandler(button))
dp.add_handler(CommandHandler('start', start))
dp.add_handler(CommandHandler('start_remind', start_remind))
dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
dp.add_handler(CallbackQueryHandler(button, pattern='^month_'))
dp.add_handler(CallbackQueryHandler(button, pattern='^year_'))


def error_handler(update: Update, context: CallbackContext):
    logging.error(f'Update {update} caused error {context.error}')


dp.add_error_handler(error_handler)

updater.start_polling()
updater.idle()
