# чтобы остановить программу нажми cntrl+C, тебе действительно не нужно завершать её аварийно...# чтобы остановить программу нажми cntrl+C, тебе действительно не нужно завершать её аварийно...
#main.py

### RENDER ###
# Импортируем Flask для веб-сервера и Thread для фоновой работы бота
from flask import Flask
from threading import Thread
### RENDER ###

from dotenv import load_dotenv
import logging
import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta
import random
import asyncio
from abc import ABC, abstractmethod
from game_base import Game, UserDataManager # Если вынесли UserDataManager
from minigames import DiceGame, RouletteGame, CoinFlipGame # Если вынесли UserDataManager
from blackjack_game import BlackjackGame
from academic_race_game import AcademicRaceGame

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    TypeHandler,
    MessageHandler,
    filters,
    JobQueue
)

# --- 2. НАСТРОЙКИ И КОНФИГУРАЦИЯ ---

# Загружаем переменные окружения из .env файла
load_dotenv()

# Получаем токен бота и ID администратора из переменных окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID_TGBOT")

if not TOKEN:
    raise ValueError("Ошибка: Токен TELEGRAM_TOKEN не найден в переменных окружения.")
if not ADMIN_ID:
    raise ValueError("Ошибка: ID администратора ADMIN_ID_TGBOT не найден в переменных окружения.")

DATA_FILE = "user_data.xml"

FACTIONS = ["белые", "красные", "синие", "зеленые", "чёрные", "прозрачные"]


# --- ТЕКСТОВЫЕ КОНСТАНТЫ ---
INFO_TEXT = (
    "ℹ️ *Информация о боте*\n\n"
    "Привет! Я разработчик Гонца! 👋🏻😃\n\n"
    "Гонец моё первое детище, он прошёл такой долгий путь и ахх~ не могу сдержать слёзы гордости 😭\n"
    "Если вы хотите заказать бота - пишите мне с помощью кнопки ниже 😉\n"
    "Если вам просто понравился бот вы можете также написать мне в личные сообщения, мне будет приятно 😊\n"
    "А ещё, пожалуйста, подпишитесь на \"Кодфедраль\"! @codhedral 👈🏻👈🏻👈🏻"
)

# --- ЛОГИРОВАНИЕ ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ГЛОБАЛЬНЫЙ МЕНЕДЖЕР И ОБРАБОТЧИК АКТИВНОСТИ ---
user_manager = UserDataManager(DATA_FILE)

async def track_user_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user:
        user_manager.update_user_activity(update.effective_user.id)

# Создаем экземпляры игр и регистрируем их
GAMES = {
    "dice": DiceGame("dice", "в Кости", user_manager),
    "roulette": RouletteGame("roulette", "в Рулетку", user_manager),
    "coinflip": CoinFlipGame("coinflip", "в Монетку", user_manager),
    "blackjack": BlackjackGame("blackjack", "в Блэкджек", user_manager),
    "academic_race": AcademicRaceGame("academic_race", "в Гонки Академиков", user_manager),
}
# --- КОНЕЦ НОВОГО БЛОКА ---

# --- ГЕНЕРАТОРЫ КЛАВИАТУР ---
def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton("📰 Новости", callback_data='nav:news')],
                [InlineKeyboardButton("🎮 Игры", callback_data='nav:games')],
                [InlineKeyboardButton("ℹ️ Информация", callback_data='nav:info')]]
    return InlineKeyboardMarkup(keyboard)

def get_news_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton("🩶 (Все новости)", callback_data='sub:прозрачные')],
                [InlineKeyboardButton("❤️", callback_data='sub:красные'), InlineKeyboardButton("💚", callback_data='sub:зеленые')],
                [InlineKeyboardButton("🤍", callback_data='sub:белые'), InlineKeyboardButton("💙", callback_data='sub:синие'), InlineKeyboardButton("🖤", callback_data='sub:чёрные')],
                [InlineKeyboardButton("⬅️ Назад", callback_data='nav:main')]]
    return InlineKeyboardMarkup(keyboard)

def get_info_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton("📊 Статистика", callback_data='get_public_stats')],
                [InlineKeyboardButton("✍️ Сообщение разработчику", callback_data='contact:message')],
                [InlineKeyboardButton("🚀 Заказать бота", callback_data='contact:order')],
                [InlineKeyboardButton("⬅️ Назад", callback_data='nav:main')]]
    return InlineKeyboardMarkup(keyboard)

def get_games_keyboard(user_id: int) -> InlineKeyboardMarkup:
    balance = user_manager.get_user_balance(user_id)
    keyboard = [
        [InlineKeyboardButton(f"💰 Ваш баланс: {balance:,} дукатов", callback_data='do_nothing')],
        [InlineKeyboardButton("💪 Работать (+5,000)", callback_data='game:work')],
        [InlineKeyboardButton("🎓 Гонки академиков", callback_data='game:start:academic_race')],
        [InlineKeyboardButton("🎲 Играть в Кости", callback_data='game:start:dice')],
        [InlineKeyboardButton("🎡 Играть в Рулетку", callback_data='game:start:roulette')],
        [InlineKeyboardButton("🪙 Играть в Монетку", callback_data='game:start:coinflip')],
        [InlineKeyboardButton("🃏 Играть в Блэкджек", callback_data='game:start:blackjack')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='nav:main')]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- ГЕНЕРАТОР ОТЧЕТА ---
def generate_public_stats_report() -> str:
    users = user_manager.get_all_users()
    total_users = len(users)
    total_interactions = sum(user.get('interaction_count', 0) for user in users.values())
    faction_counts = {faction: 0 for faction in FACTIONS}
    faction_counts['Без фракции'] = 0
    for user_data in users.values():
        faction = user_data.get('faction', 'None')
        if faction in faction_counts:
            faction_counts[faction] += 1
        elif faction == 'None':
             faction_counts['Без фракции'] += 1
    report = "📊 *Общая статистика бота*\n\n"
    report += f"👥 *Всего пользователей:* {total_users}\n"
    report += f"💬 *Всего взаимодействий:* {total_interactions}\n\n"
    report += "📈 *Популярность фракций:*\n"
    sorted_factions = sorted(faction_counts.items(), key=lambda item: item[1], reverse=True)
    for faction, count in sorted_factions:
        if count > 0:
            report += f"- {faction.capitalize()}: {count} подписчиков\n"
    return report

# --- ОСНОВНЫЕ ОБРАБОТЧИКИ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_markup = get_main_keyboard()
    if update.message:
        await update.message.reply_text("Добро пожаловать! Выберите раздел:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text("Добро пожаловать! Выберите раздел:", reply_markup=reply_markup)

async def nav_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    nav_target = query.data.split(':')[1]

    if nav_target != 'games':
        context.user_data.pop('game_state', None)
    elif nav_target == 'games':
        if user_manager.check_and_apply_bankruptcy(user_id):
            await query.answer(
                "Ваш баланс был слишком мал и был восстановлен до 100 дукатов по программе банкротства.",
                show_alert=True)

    text, keyboard = "", None
    if nav_target == 'main': text, keyboard = "Главное меню. Выберите раздел:", get_main_keyboard()
    elif nav_target == 'games': text, keyboard = "Добро пожаловать в Игровой Клуб!", get_games_keyboard(user_id)
    elif nav_target == 'news': text, keyboard = "Выберите фракцию для подписки:", get_news_keyboard()
    elif nav_target == 'info': text, keyboard = INFO_TEXT, get_info_keyboard()

    await query.edit_message_text(text, reply_markup=keyboard, parse_mode='Markdown', disable_web_page_preview=True)

async def subscription_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    faction = query.data.split(':')[1]
    user_manager.set_user_faction(user_id, faction)
    await query.message.delete()
    menu_button = InlineKeyboardButton("⬅️ Назад к новостям", callback_data='nav:news')
    reply_markup = InlineKeyboardMarkup([[menu_button]])
    await context.bot.send_message(
        chat_id=user_id,
        text=f"Вы успешно подписались на новости фракции: {faction.capitalize()}.",
        reply_markup=reply_markup
    )

async def show_public_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    is_allowed, time_left = user_manager.check_stats_cooldown(user_id)

    if not is_allowed:
        minutes, seconds = divmod(int(time_left.total_seconds()), 60)
        await query.answer(f"Запрашивать статистику можно раз в час. Осталось: {minutes} мин {seconds} сек.", show_alert=True)
        return

    await query.answer()
    report = generate_public_stats_report()
    menu_button = InlineKeyboardButton("⬅️ Назад", callback_data='nav:info')
    reply_markup = InlineKeyboardMarkup([[menu_button]])
    await query.edit_message_text(text=report, parse_mode='Markdown', reply_markup=reply_markup)

# ... (Остальные обработчики без изменений) ...
async def stata_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if str(user_id) == ADMIN_ID: # Сравнение строк, так как getenv возвращает строку
        period_arg = context.args[0].lower() if context.args else 'вся'
        now = datetime.now()
        period_map = {
            'день': (now - timedelta(days=1), "за последний день"),
            'неделя': (now - timedelta(weeks=1), "за последнюю неделю"),
            'месяц': (now - timedelta(days=30), "за последний месяц"),
            'вся': (datetime(2000, 1, 1), "за всё время")
        }
        if period_arg not in period_map:
            await update.message.reply_text("Неверный период. Используйте: день, неделя, месяц, вся.")
            return

        start_date, period_text = period_map[period_arg]
        users = user_manager.get_all_users()
        total_users = len(users)
        new_users_in_period = sum(1 for u in users.values() if datetime.fromisoformat(u['first_seen']) >= start_date)
        active_users_in_period = sum(1 for u in users.values() if datetime.fromisoformat(u['last_seen']) >= start_date)
        total_interactions = sum(u.get('interaction_count', 0) for u in users.values())

        faction_counts = {faction: 0 for faction in FACTIONS + ['Без фракции']}
        for user_data in users.values():
            faction = user_data.get('faction', 'None')
            key = 'Без фракции' if faction == 'None' else faction
            if key in faction_counts: faction_counts[key] += 1

        report = f"📊 *Админская статистика {period_text}*\n\n"
        report += f"👤 *Новые пользователи:* {new_users_in_period}\n"
        report += f"🔥 *Активные пользователи:* {active_users_in_period}\n\n"
        report += f"👥 *Всего пользователей в базе:* {total_users}\n"
        report += f"💬 *Всего взаимодействий за всё время:* {total_interactions}\n\n"
        report += "📈 *Распределение по фракциям:*\n"
        for faction, count in faction_counts.items():
            if count > 0: report += f"- {faction.capitalize()}: {count}\n"
        await update.message.reply_text(report, parse_mode='Markdown')

    else:
        is_allowed, time_left = user_manager.check_stats_cooldown(user_id)
        if not is_allowed:
            minutes, seconds = divmod(int(time_left.total_seconds()), 60)
            await update.message.reply_text(f"Запрашивать статистику можно раз в час. Попробуйте снова через {minutes} мин {seconds} сек.")
            return

        report = generate_public_stats_report()
        await update.message.reply_text(report, parse_mode='Markdown')

async def say_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("Эта команда доступна только администратору.")
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /say <фракция|все> <ваше сообщение>\nФракции: прозрачные, белые, красные, синие, зеленые, чёрные.")
        return
    target_faction = args[0].lower()
    message_to_send = " ".join(args[1:])
    all_users = user_manager.get_all_users()
    recipients = set()
    if target_faction == "все":
        recipients = set(all_users.keys())
    elif target_faction in FACTIONS:
        for sub_id, user_data in all_users.items():
            if user_data.get('faction') in [target_faction, 'прозрачные']:
                recipients.add(sub_id)
    else:
        await update.message.reply_text(f"Неизвестная фракция: {target_faction}")
        return

    successful_sends = 0
    for recipient_id in recipients:
        try:
            await context.bot.send_message(chat_id=recipient_id, text=message_to_send)
            successful_sends += 1
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю {recipient_id}: {e}")
    await update.message.reply_text(f"Сообщение успешно отправлено {successful_sends} из {len(recipients)} получателей.")

async def contact_admin_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    contact_type = query.data.split(':')[1]
    context.user_data['contact_state'] = 'awaiting_admin_message'
    context.user_data['contact_type'] = contact_type

    prompt_text = ("Напишите ваше сообщение для разработчика." if contact_type == 'message'
                   else "Пожалуйста, в двух словах опишите ваш заказ. Разработчик скоро с вами свяжется.")

    cancel_button = InlineKeyboardButton("⬅️ Назад", callback_data='nav:info')
    reply_markup = InlineKeyboardMarkup([[cancel_button]])
    await query.edit_message_text(
        text=f"{prompt_text}\n\nОтправьте свой текст следующим сообщением.",
        reply_markup=reply_markup
    )


# --- ИГРОВЫЕ ОБРАБОТЧИКИ ---
async def work_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    is_allowed, time_left = user_manager.check_work_cooldown(user_id)
    if is_allowed:
        work_bonus = 5000
        user_manager.update_user_balance(user_id, work_bonus)
        await query.answer(f"Вы славно потрудились и заработали {work_bonus:,} дукатов!", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=get_games_keyboard(user_id))
    else:
        minutes, seconds = divmod(int(time_left.total_seconds()), 60)
        await query.answer(f"Вы слишком устали. Возвращайтесь через {minutes} мин {seconds} сек.", show_alert=True)

async def game_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split(':')
    game_id = parts[2]
    game = GAMES.get(game_id)
    if len(parts) > 3 and parts[3] == 'new':
        context.user_data.pop('current_bet', None)
    if game.requires_bet:
        context.user_data['game_state'] = f'awaiting_bet:{game_id}'
        balance = user_manager.get_user_balance(user_id)
        current_bet = context.user_data.get('current_bet', 0)
        text = game.get_rules_text(balance, current_bet)
        keyboard = game.get_game_keyboard(context)
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode='Markdown')
        if current_bet == 0:
            sent_message = await query.get_message()
            context.user_data['prompt_message_id'] = sent_message.message_id
    else:
        context.user_data['game_state'] = f'in_game_menu:{game_id}'
        balance = user_manager.get_user_balance(user_id)
        text = game.get_rules_text(balance, 0)
        keyboard = game.get_game_keyboard(context)
        await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode='Markdown')

async def game_modify_bet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    parts = query.data.split(':')
    game_id, action = parts[2], parts[3]
    game = GAMES.get(game_id)
    current_bet = context.user_data.get('current_bet', 0)
    if current_bet <= 0:
        await query.answer("Сначала нужно сделать ставку!", show_alert=True)
        return
    balance = user_manager.get_user_balance(user_id)
    new_bet = 0
    if action == 'multiply':
        multiplier = int(parts[4])
        new_bet = current_bet * multiplier
    elif action == 'allin':
        new_bet = balance
    if new_bet > balance:
        await query.answer(f"Недостаточно средств. Ваш баланс: {balance:,}", show_alert=True)
        new_bet = current_bet
    if new_bet == current_bet and action != 'allin':
         await query.answer("Ставка не изменилась.", show_alert=True)
         return
    context.user_data['current_bet'] = new_bet
    await query.answer(f"Ставка изменена на {new_bet:,}")
    await query.edit_message_reply_markup(reply_markup=game.get_game_keyboard(context))

async def game_play_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    game_id = query.data.split(':')[2]
    game = GAMES.get(game_id)
    if game:
        await game.play(update, context)
    else:
        logger.warning(f"Получен вызов для несуществующей игры: {game_id}")

# --- УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ТЕКСТА ---
async def text_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    game_state = context.user_data.get('game_state', '')
    contact_state = context.user_data.get('contact_state')

    if game_state.startswith('awaiting_answer:'):
        game_id = game_state.split(':')[1]
        game = GAMES.get(game_id)
        if game and hasattr(game, 'handle_answer'):
            await game.handle_answer(update, context)
        return

    elif game_state.startswith('awaiting_bet:'):
        game_id = game_state.split(':')[1]
        game = GAMES.get(game_id)
        if not game: return
        prompt_message_id = context.user_data.pop('prompt_message_id', None)
        try: bet_amount = int(''.join(filter(str.isdigit, update.message.text)))
        except (ValueError, TypeError):
            await update.message.reply_text("Пожалуйста, введите ставку в виде числа.")
            return
        balance = user_manager.get_user_balance(user_id)
        if not (0 < bet_amount <= balance):
            await update.message.reply_text(f"Ставка должна быть больше нуля и не превышать ваш баланс ({balance:,} дукатов).")
            return
        context.user_data['current_bet'] = bet_amount
        context.user_data['game_state'] = 'bet_placed'
        await context.bot.delete_message(chat_id=user_id, message_id=update.message.message_id)
        if prompt_message_id:
            try: await context.bot.delete_message(chat_id=user_id, message_id=prompt_message_id)
            except Exception as e: logger.warning(f"Не удалось удалить сообщение {prompt_message_id}: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text=game.get_rules_text(balance, bet_amount),
            reply_markup=game.get_game_keyboard(context),
            parse_mode='Markdown'
        )
        return

    elif contact_state == 'awaiting_admin_message':
        user = update.effective_user
        user_text = update.message.text
        contact_type = context.user_data.get('contact_type', 'message')
        username_str = f"@{user.username}" if user.username else f"ID: `{user.id}`"
        header = "❗️ *Заказ!*\n\n" if contact_type == 'order' else "✉️ *Письмо!*\n\n"
        admin_message = f"{header}Пользователь {username_str} пишет:\n\n*{user_text}*"
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_message, parse_mode='Markdown')
            menu_button = InlineKeyboardButton("⬅️ Вернуться в меню", callback_data='nav:main')
            await update.message.reply_text("✅ Ваше сообщение успешно отправлено!", reply_markup=InlineKeyboardMarkup([[menu_button]]))
        except Exception as e:
            logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось переслать сообщение от {user.id} админу {ADMIN_ID}: {e}")
            await update.message.reply_text("❌ Произошла ошибка при отправке. Разработчик уже уведомлен.")
        finally:
            context.user_data.pop('contact_state', None)
            context.user_data.pop('contact_type', None)
        return

    else:
        context.user_data.pop('game_state', None)
        context.user_data.pop('current_bet', None)
        await update.message.reply_text(
            "🤖 Я не совсем понимаю, что вы имеете в виду. "
            "Возможно, вы хотели вернуться в главное меню?",
            reply_markup=get_main_keyboard()
        )

### RENDER ###
app = Flask('')

@app.route('/')
def home():
    """Эта функция будет отвечать на HTTP-запросы Render."""
    return "I'm alive"

def run_server():
    """Запускает веб-сервер."""
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def main() -> None:
    # --- ШАГ 1: Запускаем веб-сервер в фоновом потоке ---
    # Он простой и не требует быть главным.
    # daemon=True означает, что этот поток автоматически завершится, когда завершится основной.
    server_thread = Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    print("Веб-сервер для Render запущен в фоновом потоке...")

    # --- ШАГ 2: Запускаем бота в основном (главном) потоке ---
    # Теперь он может делать всё, что ему нужно, включая обработку сигналов.
    try:
        print("Инициализация приложения Telegram в основном потоке...")
        request = HTTPXRequest(connect_timeout=10.0, read_timeout=60.0, pool_timeout=None)
        application = (Application.builder().token(TOKEN).job_queue(JobQueue()).request(request).build())
        
        print("Добавление обработчиков...")
        # ... (здесь все ваши application.add_handler)
        application.add_handler(TypeHandler(Update, track_user_activity), group=-1)
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("say", say_command))
        application.add_handler(CommandHandler("stata", stata_command))
        application.add_handler(CallbackQueryHandler(nav_handler, pattern='^nav:'))
        application.add_handler(CallbackQueryHandler(subscription_handler, pattern='^sub:'))
        application.add_handler(CallbackQueryHandler(show_public_stats, pattern='^get_public_stats$'))
        application.add_handler(CallbackQueryHandler(contact_admin_start_handler, pattern='^contact:'))
        application.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern='^do_nothing$'))
        application.add_handler(CallbackQueryHandler(work_handler, pattern='^game:work$'))
        application.add_handler(CallbackQueryHandler(game_start_handler, pattern=r'^game:start:'))
        application.add_handler(CallbackQueryHandler(game_modify_bet_handler, pattern=r'^game:modify:'))
        application.add_handler(CallbackQueryHandler(game_play_handler, pattern=r'^game:play:'))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_router))

        print("Бот запущен в режиме polling...")
        application.run_polling()

    except Exception as e:
        print("!!! КРИТИЧЕСКАЯ ОШИБКА ПРИ ЗАПУСКЕ БОТА !!!")
        print(f"Тип ошибки: {type(e).__name__}")
        print(f"Сообщение: {e}")
        import traceback
        traceback.print_exc()

# --- Точка входа в программу ---
if __name__ == "__main__":
    main()
