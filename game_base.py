# Файл: game_base.py
"""
Содержит базовые классы для управления данными пользователей и игровой логикой.

- UserDataManager: Класс для чтения, записи и управления данными пользователей в XML-файле.
- Game: Абстрактный базовый класс, определяющий "контракт" для всех мини-игр.
"""

# --- 1. ИМПОРТЫ ---

import logging
import random
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import requests
import json
import threading
from telegram.ext import JobQueue

# Импорты для тайп-хинтинга (не влияют на исполнение, но помогают в разработке)
from typing import Dict, Any, Tuple, Optional

# Импорты Telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes


# --- 2. НАСТРОЙКИ И КОНСТАНТЫ ---

# Настройка логирования для этого модуля
logger = logging.getLogger(__name__)

# Единый источник правды для структуры данных нового пользователя.
# Чтобы добавить новое поле (например, 'achievements'), просто добавьте его сюда
# с начальным значением. Код загрузки и сохранения подхватит его автоматически.
DEFAULT_USER_STRUCTURE = {
    'faction': 'None',                   # Тип: str. 'None' - отличное значение по умолчанию.
    'first_seen': '',                  # Тип: str. Будет установлен при первом контакте.
    'last_seen': '',                   # Тип: str. Будет обновляться при каждом контакте.
    'interaction_count': 0,              # Тип: int. Новый пользователь начинает с 0 взаимодействий.
    'balance': 10000,                        # Тип: int. Новый пользователь начинает с нулевым балансом (или установите стартовый капитал, например, 100).
    'last_stats_request_time': None,     # Тип: str. Время еще не было запрошено.
    'last_work_time': None,              # Тип: str. Еще не работал.
    'last_race_time': None               # Тип: str. Еще не участвовал в гонках.
}

# --- 3. КЛАСС УПРАВЛЕНИЯ ДАННЫМИ ---

class UserDataManager:
    """
    Управляет данными пользователей с кешированием в памяти и периодическим
    сохранением в облако JSONBin.io.
    """
    def __init__(self, api_key: str, bin_id: str):
        self._api_key = api_key
        self._bin_id = bin_id
        self._api_url = f"https://api.jsonbin.io/v3/b/{self._bin_id}"
        self._headers = {'X-Master-Key': self._api_key}

        # --- НОВЫЕ АТРИБУТЫ ДЛЯ ОТЛОЖЕННОГО СОХРАНЕНИЯ ---
        self._is_dirty = False  # Флаг, который показывает, были ли изменения
        self._save_lock = threading.Lock() # Замок, чтобы избежать гонки данных при сохранении

        # Загружаем данные при старте
        self._full_data_cache = self._load_bin()
        self.users = self._full_data_cache.get('users', {})
        logger.info(f"UserDataManager инициализирован. Загружено {len(self.users)} пользователей.")

    def _load_bin(self) -> Dict[str, Any]:
        """Загружает ВСЁ содержимое "бина" из JSONBin.io при старте."""
        try:
            response = requests.get(f"{self._api_url}/latest", headers=self._headers, timeout=10)
            response.raise_for_status()
            data = response.json().get('record', {})
            if 'users' in data and isinstance(data['users'], dict):
                data['users'] = {int(k): v for k, v in data['users'].items()}
            logger.info(f"Успешно загружены данные из JSONBin (ID: {self._bin_id})")
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Сетевая ошибка при загрузке данных: {e}. Бот не может запуститься.")
            raise ConnectionError("Не удалось загрузить данные из облака.")
        except (json.JSONDecodeError, KeyError, ValueError):
            logger.warning(f"Данные в JSONBin повреждены или пусты. Начинаем с пустой базы.")
            return {}

    def _mark_as_dirty(self) -> None:
        """
        Приватный метод. Просто помечает данные как "измененные".
        Теперь это будет вызываться вместо прямого сохранения.
        """
        self._is_dirty = True

    def force_save(self) -> None:
        """
        Принудительно сохраняет данные в JSONBin.io, если они были изменены.
        Этот метод будет вызываться по таймеру и при выключении бота.
        """
        # Блокируем, чтобы избежать ситуации, когда бот выключается
        # прямо во время планового сохранения.
        with self._save_lock:
            if not self._is_dirty:
                # Если изменений не было, ничего не делаем
                return

            logger.info("Обнаружены изменения. Начинаю синхронизацию с JSONBin.io...")
            try:
                self._full_data_cache['users'] = self.users
                headers = {**self._headers, 'Content-Type': 'application/json'}
                response = requests.put(self._api_url, headers=headers, json=self._full_data_cache, timeout=10)
                response.raise_for_status()

                # Если сохранение прошло успешно, сбрасываем флаг
                self._is_dirty = False
                logger.info("Синхронизация с JSONBin.io успешно завершена.")
            except requests.exceptions.RequestException as e:
                logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось сохранить данные в JSONBin: {e}")

    def start_autosave(self, job_queue: JobQueue, interval_seconds: int = 3600) -> None:
        """
        Запускает повторяющуюся задачу для автоматического сохранения данных.
        """
        # Важно! Мы передаем МЕТОД, а не его вызов. `force_save`, а не `force_save()`.
        job_queue.run_repeating(
            callback=lambda _: self.force_save(), # Используем лямбду, чтобы job_queue не передавал аргументы
            interval=interval_seconds,
            name="hourly_data_save"
        )
        logger.info(f"Автосохранение данных в облако настроено с интервалом {interval_seconds} секунд.")

    # --- ТЕПЕРЬ ВСЕ МЕТОДЫ, МЕНЯЮЩИЕ ДАННЫЕ, ВЫЗЫВАЮТ _mark_as_dirty ---

    def update_user_activity(self, user_id: int) -> None:
        current_time_iso = datetime.now().isoformat()
        made_changes = False
        if user_id not in self.users:
            self.users[user_id] = DEFAULT_USER_STRUCTURE.copy()
            self.users[user_id]['first_seen'] = current_time_iso
            self.users[user_id]['interaction_count'] = 1
            made_changes = True
        else:
            for key, default_value in DEFAULT_USER_STRUCTURE.items():
                if key not in self.users[user_id]:
                    self.users[user_id][key] = default_value
                    made_changes = True # Обнаружили, что нужно было добавить поле
            self.users[user_id]['interaction_count'] += 1
        
        self.users[user_id]['last_seen'] = current_time_iso
        # Помечаем, что данные изменились
        self._mark_as_dirty()
    
    def update_user_balance(self, user_id: int, amount_change: int) -> None:
        if user_id in self.users:
            current_balance = self.users[user_id].get('balance', DEFAULT_USER_STRUCTURE['balance'])
            self.users[user_id]['balance'] = current_balance + amount_change
            self._mark_as_dirty() # <-- ИЗМЕНЕНИЕ
        else:
            logger.warning(f"Попытка обновить баланс несуществующего пользователя: {user_id}")
    
    # ...и так далее для ВСЕХ методов, которые раньше вызывали _save()
    def check_and_apply_bankruptcy(self, user_id: int) -> bool:
        user_data = self.users.get(user_id)
        if user_data and user_data.get('balance', 0) < 100:
            self.users[user_id]['balance'] = 100
            self._mark_as_dirty() # <-- ИЗМЕНЕНИЕ
            return True
        return False

    def _check_and_update_cooldown(self, user_id: int, cooldown_key: str, cooldown_duration: timedelta) -> Tuple[bool, Optional[timedelta]]:
        # ... (логика проверки кулдауна остается той же)
        user_data = self.users.get(user_id, {})
        last_action_str = user_data.get(cooldown_key)
        if last_action_str:
            last_action_time = datetime.fromisoformat(last_action_str)
            if datetime.now() < last_action_time + cooldown_duration:
                time_left = (last_action_time + cooldown_duration) - datetime.now()
                return False, time_left
        
        if user_id not in self.users:
             self.update_user_activity(user_id) # Этот метод уже вызывает _mark_as_dirty
        
        self.users[user_id][cooldown_key] = datetime.now().isoformat()
        self._mark_as_dirty() # <-- ИЗМЕНЕНИЕ
        return True, None

    def set_user_faction(self, user_id: int, faction: str) -> None:
        if user_id in self.users:
            self.users[user_id]['faction'] = faction
            self._mark_as_dirty() # <-- ИЗМЕНЕНИЕ
    
    # Методы, которые только читают данные, не меняются
    def get_user_balance(self, user_id: int) -> int:
        return self.users.get(user_id, {}).get('balance', 0)

    def get_all_users(self) -> Dict[int, Dict[str, Any]]:
        return self.users
    
    def check_work_cooldown(self, user_id: int) -> Tuple[bool, Optional[timedelta]]:
        return self._check_and_update_cooldown(user_id, 'last_work_time', timedelta(hours=1))

    def check_stats_cooldown(self, user_id: int) -> Tuple[bool, Optional[timedelta]]:
        return self._check_and_update_cooldown(user_id, 'last_stats_request_time', timedelta(hours=1))

    def check_race_cooldown(self, user_id: int) -> Tuple[bool, Optional[timedelta]]:
        return self._check_and_update_cooldown(user_id, 'last_race_time', timedelta(hours=2))


# --- 4. АБСТРАКТНЫЙ КЛАСС ИГРЫ ---

class Game(ABC):
    """
    Абстрактный базовый класс для всех игр.
    Определяет общий интерфейс, который должна реализовывать каждая игра.
    Это гарантирует, что главный обработчик сможет единообразно вызывать
    начало игры, показ правил и основной игровой процесс.
    """
    # Атрибут класса, показывающий, требует ли игра предварительной ставки.
    # Может быть переопределен в дочерних классах (например, для Гонки Академиков).
    requires_bet: bool = True
    
    def __init__(self, game_id: str, name: str, user_manager_instance: UserDataManager):
        """
        Инициализатор базового класса игры.

        Args:
            game_id (str): Уникальный идентификатор игры (e.g., "dice", "roulette").
            name (str): Человекочитаемое название игры (e.g., "в Кости").
            user_manager_instance (UserDataManager): Экземпляр менеджера данных для доступа к балансу и т.д.
        """
        self.id = game_id
        self.name = name
        self.user_manager = user_manager_instance

    @abstractmethod
    def get_rules_text(self, balance: int, bet: int) -> str:
        """
        Должен возвращать форматированный текст с правилами игры и текущим статусом.

        Args:
            balance (int): Текущий баланс игрока.
            bet (int): Текущая ставка игрока.

        Returns:
            str: Текст для отправки пользователю.
        """
        pass

    @abstractmethod
    def get_game_keyboard(self, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
        """
        Должен возвращать клавиатуру с кнопками для управления игрой (сделать ставку, удвоить и т.д.).
        
        Args:
            context (ContextTypes.DEFAULT_TYPE): Контекст пользователя для доступа к user_data.

        Returns:
            InlineKeyboardMarkup: Клавиатура для сообщения.
        """
        pass

    @abstractmethod
    async def play(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Должен содержать основную логику игры:
        1. Проверить условия (хватает ли баланса, сделана ли ставка).
        2. Рассчитать результат (выигрыш/проигрыш).
        3. Обновить баланс пользователя через self.user_manager.
        4. Отправить пользователю сообщение с результатом и клавиатурой для повторной игры.
        
        Args:
            update (Update): Входящее обновление от Telegram.
            context (ContextTypes.DEFAULT_TYPE): Контекст пользователя.
        """
        pass
    
    def get_replay_keyboard(self) -> InlineKeyboardMarkup:
        """
        Возвращает стандартную клавиатуру после окончания раунда.
        Позволяет сыграть еще раз или вернуться в игровое меню.
        """
        keyboard = [
            [InlineKeyboardButton(f"🎮 Сыграть ещё раз", callback_data=f'game:start:{self.id}:new')], # 'new' сбрасывает ставку
            [InlineKeyboardButton("⬅️ Вернуться в Игровой Клуб", callback_data='nav:games')]
        ]
        return InlineKeyboardMarkup(keyboard)