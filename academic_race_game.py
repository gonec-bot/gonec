# Файл: academic_race_game.py
"""
Содержит реализацию игры "Гонки академиков".

Эта игра не требует ставки и основана на скорости решения математических задач.
Ключевые особенности:
- Временное ограничение на каждый ответ.
- Динамически растущая награда.
- Автоматический перезапуск при тайм-ауте.
- Полное прекращение игры после нескольких тайм-аутов подряд для предотвращения "зависания" игры.
"""

# --- 1. ИМПОРТЫ ---

import random
from datetime import datetime, timedelta

# Импорты для тайп-хинтинга
from typing import Tuple

# Импорты Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Импорты из нашего проекта
from game_base import Game, UserDataManager


# --- 2. КЛАСС ИГРЫ ---

class AcademicRaceGame(Game):
    """
    Класс, реализующий логику игры "Гонки академиков".
    """
    # Атрибут базового класса: эта игра не требует предварительной ставки.
    requires_bet = False
    
    # Константа, определяющая все ключи, которые эта игра хранит в context.user_data.
    # Используется для надёжной очистки состояния после завершения игры.
    _RACE_STATE_KEYS = [
        'game_state',
        'race_answer',
        'race_deadline',
        'race_reward',
        'race_message_id',
        'race_timeout_count'
    ]

    def __init__(self, game_id: str, name: str, user_manager_instance: UserDataManager):
        """
        Инициализатор игры "Гонки академиков".
        """
        super().__init__(game_id, name, user_manager_instance)
        # Настраиваемые параметры игры
        self.initial_reward = 100
        self.time_limit_seconds = 10
        self.max_timeouts = 3

    # --- 3. МЕТОДЫ ГЕНЕРАЦИИ ИНТЕРФЕЙСА ---

    @staticmethod
    def generate_academic_problem() -> Tuple[str, int]:
        """
        Создает случайную математическую задачу и её решение.
        Статический метод, так как не зависит от состояния конкретной игры.

        Returns:
            tuple[str, int]: Кортеж, содержащий текст задачи и правильный ответ.
        """
        pattern = random.randint(1, 4)
        # Неразрывный пробел `\u00A0` используется для лучшего отображения в Telegram.
        if pattern == 1: # (a + b) * c
            a, b, c = random.randint(10, 50), random.randint(10, 50), random.randint(2, 9)
            problem_str = f"({a}\u00A0+\u00A0{b})\u00A0х\u00A0{c}"
            answer = (a + b) * c
        elif pattern == 2: # a * b - c
            a, b, c = random.randint(20, 60), random.randint(2, 9), random.randint(10, 100)
            problem_str = f"{a}\u00A0х\u00A0{b}\u00A0−\u00A0{c}"
            answer = a * b - c
        elif pattern == 3: # sqrt(a) + b
            a = random.choice([4, 9, 16, 25, 36, 49, 64, 81, 100, 121, 144, 169, 196, 225])
            b = random.randint(10, 30)
            problem_str = f"√{a}\u00A0+\u00A0{b}"
            answer = int(a**0.5 + b)
        else: # x * a = result
            a, b = random.randint(2, 10), random.randint(10, 50)
            result = a * b
            problem_str = f"х\u00A0·\u00A0{a}\u00A0=\u00A0{result}"
            answer = b
            
        question = f"Чему равен **х** в уравнении: **{problem_str}**?" if pattern == 4 else f"Решите пример: **{problem_str}**"
        return question, answer

    def get_rules_text(self, balance: int, bet: int) -> str:
        """
        Возвращает текст с правилами игры перед её началом.
        Реализует абстрактный метод из базового класса Game.
        """
        return (
            f"🎓 *Бесконечная гонка академиков!*\n\n"
            f"Вам даётся *{self.time_limit_seconds} секунд* на решение каждой задачи. "
            f"Если вы не успеваете, гонка начинается заново.\n\n"
            f"⚠️ *Внимание:* После *{self.max_timeouts}* пропущенных примеров подряд гонка будет автоматически остановлена.\n\n"
            "После каждого правильного ответа награда увеличивается. Гонка закончится, как только вы ошибётесь. Удачи!\n\n"
            "Нажмите 'Начать!', чтобы получить первое задание."
        )
    
    def get_game_keyboard(self, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
        """
        Возвращает клавиатуру для старта игры.
        Реализует абстрактный метод из базового класса Game.
        """
        keyboard = [
            [InlineKeyboardButton("🏁 Начать!", callback_data=f'game:play:{self.id}')],
            [InlineKeyboardButton("⬅️ Вернуться в Игровой Клуб", callback_data='nav:games')]
        ]
        return InlineKeyboardMarkup(keyboard)

    # --- 4. ОСНОВНАЯ ИГРОВАЯ ЛОГИКА ---

    async def play(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Основной метод, запускающий игру. Вызывается по нажатию кнопки "Начать!".
        Реализует абстрактный метод из базового класса Game.
        """
        query = update.callback_query
        await query.answer("Приготовьтесь...")
        
        # Инициализируем начальное состояние гонки
        context.user_data['game_state'] = f'awaiting_answer:{self.id}'
        context.user_data['race_reward'] = self.initial_reward
        context.user_data['race_timeout_count'] = 0 # Счётчик пропущенных ответов
        
        # Формируем текст для первого раунда
        text = (
            f"🎓 *Гонка академиков!*\n\n"
            f"Награда за правильный ответ: *{self.initial_reward:,}* дукатов!\n\n"
            f"У вас есть *{self.time_limit_seconds} секунд*, чтобы решить задачу:"
        )
        
        # Запускаем первый раунд
        await self._start_or_continue_round(context, query.message.chat_id, text, query.message.message_id)

    async def handle_answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обрабатывает текстовое сообщение от пользователя с ответом на задачу.
        """
        user_id = update.effective_user.id
        correct_answer = context.user_data.get('race_answer')
        deadline = context.user_data.get('race_deadline')
        current_reward = context.user_data.get('race_reward')

        # Проверка 1: не устарел ли ответ (пользователь мог ответить на уже просроченную задачу)
        if not deadline or datetime.now() > deadline:
            await update.message.reply_text("⌛️ Вы опоздали. Этот раунд уже завершён. Решайте новый пример, который появился выше.")
            return
        
        # Проверка 2: является ли ответ числом
        try:
            user_answer = int(update.message.text.strip())
        except (ValueError, TypeError):
            self._cleanup_race_state(context)
            await update.message.reply_text(
                f"❌ *Неверный формат!* Ответ должен быть целым числом. Правильный ответ был: **{correct_answer}**. Гонка окончена.",
                reply_markup=self.get_replay_keyboard(), parse_mode='Markdown'
            )
            return

        # Проверка 3: правильный ли ответ
        if user_answer == correct_answer:
            # Правильный ответ!
            context.user_data['race_timeout_count'] = 0 # Сбрасываем счётчик бездействия
            self.user_manager.update_user_balance(user_id, current_reward)
            
            # Увеличиваем награду и готовим текст для следующего раунда
            new_reward = int(current_reward * 3.14)
            context.user_data['race_reward'] = new_reward
            text = (
                f"✅ *Верно!* Вы заработали *{current_reward:,}* дукатов. Продолжаем!\n\n"
                f"🎓 *Следующий раунд!*\nНовая награда: *{new_reward:,}* дукатов!\n\n"
                f"У вас есть *{self.time_limit_seconds} секунд*:"
            )
            await self._start_or_continue_round(context, update.effective_chat.id, text)
        else:
            # Неправильный ответ!
            self._cleanup_race_state(context)
            await update.message.reply_text(
                f"❌ *Неправильно!* Верный ответ был: **{correct_answer}**. Гонка окончена.",
                reply_markup=self.get_replay_keyboard(), parse_mode='Markdown'
            )

    # --- 5. ЛОГИКА ТАЙМЕРА И УПРАВЛЕНИЯ СОСТОЯНИЕМ ---

    async def timeout_new_problem(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Вызывается по таймеру, если пользователь не ответил вовремя.
        Увеличивает счётчик бездействия и либо перезапускает гонку, либо завершает её.
        """
        job_data = context.job.data
        chat_id = job_data['chat_id']

        # Проверяем, актуальна ли еще игра (пользователь мог уже проиграть)
        if context.user_data.get('game_state') != f'awaiting_answer:{self.id}':
            return
            
        context.user_data['race_timeout_count'] += 1
        
        # Проверяем, не достигнут ли лимит бездействия
        if context.user_data['race_timeout_count'] >= self.max_timeouts:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=job_data['message_id'],
                text="🏁 *Гонка остановлена из-за неактивности.*\n\nВы можете начать заново в любой момент.",
                reply_markup=self.get_replay_keyboard(),
                parse_mode='Markdown'
            )
            self._cleanup_race_state(context)
            return

        # Если лимит не достигнут, начинаем гонку заново с начальной наградой
        context.user_data['race_reward'] = self.initial_reward
        text = (
            f"⌛️ *Время вышло! Начинаем заново.* (Бездействие: {context.user_data['race_timeout_count']}/{self.max_timeouts})\n\n"
            f"🎓 *Гонка академиков!*\nНаграда: *{self.initial_reward:,}* дукатов!\n\n"
            f"У вас есть *{self.time_limit_seconds} секунд*:"
        )
        await self._start_or_continue_round(context, chat_id, text)

    def _cleanup_race_state(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Полностью очищает состояние гонки: удаляет все ключи из user_data и отменяет таймер.
        """
        # Отменяем запланированный таймер
        job_name = f'race_timeout_{context._chat_id}_{context._user_id}'
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()
            
        # Удаляем все связанные с гонкой данные пользователя
        for key in self._RACE_STATE_KEYS:
            context.user_data.pop(key, None)
            
    async def _start_or_continue_round(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, message_id: int = None) -> None:
        """
        Приватный helper-метод для запуска нового раунда.
        Инкапсулирует общую логику: генерация задачи, обновление user_data,
        отправка/редактирование сообщения и запуск таймера.
        """
        # Получаем ID сообщения, которое нужно редактировать
        # Если оно не передано, берем из user_data (для последующих раундов)
        if message_id is None:
            message_id = context.user_data.get('race_message_id')
        if message_id is None:
            logger.error(f"Не удалось найти message_id для чата {chat_id}, чтобы продолжить гонку.")
            return

        # Генерируем новую задачу
        problem, answer = self.generate_academic_problem()
        
        # Обновляем состояние игры в user_data
        context.user_data['race_answer'] = answer
        context.user_data['race_deadline'] = datetime.now() + timedelta(seconds=self.time_limit_seconds)
        
        # Редактируем сообщение, добавляя к нему новую задачу
        full_text = f"{text}\n\n{problem}\n\nОтправьте ответ следующим сообщением."
        msg = await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=full_text,
            parse_mode='Markdown'
        )
        # Сохраняем ID сообщения на случай, если оно изменилось
        context.user_data['race_message_id'] = msg.message_id
        
        # Планируем задачу на случай, если пользователь не ответит вовремя
        job_name = f'race_timeout_{chat_id}_{context._user_id}'
        # Сначала удаляем старый таймер, чтобы избежать дублирования
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
        # Создаем новый таймер
        context.job_queue.run_once(
            self.timeout_new_problem,
            self.time_limit_seconds,
            chat_id=chat_id,
            user_id=context._user_id,
            name=job_name,
            data={'chat_id': chat_id, 'message_id': msg.message_id}
        )