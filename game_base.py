# Файл: game_base.py
"""
Содержит базовые классы для управления данными пользователей и игровой логикой.

- UserDataManager: Класс для чтения, записи и управления данными пользователей в XML-файле.
- Game: Абстрактный базовый класс, определяющий "контракт" для всех мини-игр.
"""

# --- 1. ИМПОРТЫ ---

import logging
import random
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

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
    'faction': 'None',
    'first_seen': '',
    'last_seen': '',
    'interaction_count': 0,
    'balance': 10000,
    'last_stats_request_time': None,
    'last_work_time': None,
    'last_race_time': None
}


# --- 3. КЛАСС УПРАВЛЕНИЯ ДАННЫМИ ---

class UserDataManager:
    """
    Управляет всеми операциями с данными пользователей (загрузка, сохранение, обновление).
    Работает с XML-файлом для постоянного хранения информации.
    Этот класс вынесен в game_base.py, чтобы избежать циклических импортов,
    но в крупных проектах может находиться в отдельном файле (например, data_manager.py).
    """
    def __init__(self, file_path: str):
        """
        Инициализирует менеджер данных.

        Args:
            file_path (str): Путь к XML-файлу для хранения данных.
        """
        self.file_path = file_path
        self.users = self._load()

    def _load(self) -> Dict[int, Dict[str, Any]]:
        """
        Загружает данные пользователей из XML-файла.
        Безопасно обрабатывает отсутствующие поля для старых данных.
        """
        try:
            tree = ET.parse(self.file_path)
            root = tree.getroot()
            loaded_users = {}
            for user_elem in root.findall('user'):
                user_id = int(user_elem.get('id'))
                user_data = {}
                # Динамически загружаем все поля из нашей структуры
                for key, default_value in DEFAULT_USER_STRUCTURE.items():
                    node = user_elem.find(key)
                    if node is not None and node.text is not None:
                        # Пытаемся привести тип к тому, который указан в дефолтной структуре
                        value_type = type(default_value)
                        if value_type == bool:
                            user_data[key] = node.text.lower() in ('true', '1', 'yes')
                        elif value_type == int:
                             user_data[key] = int(node.text)
                        else:
                             user_data[key] = node.text
                    else:
                        # Если поля нет в XML, берем значение по умолчанию
                        user_data[key] = default_value
                loaded_users[user_id] = user_data

            logger.info(f"Успешно загружено {len(loaded_users)} пользователей из {self.file_path}")
            return loaded_users
        except (FileNotFoundError, ET.ParseError) as e:
            logger.warning(f"Файл {self.file_path} не найден или поврежден ({e}). Будет создан новый.")
            return {}

    def _save(self) -> None:
        """
        Сохраняет текущие данные всех пользователей в XML-файл.
        Данные сохраняются в "красивом" виде с отступами.
        """
        root = ET.Element("users")
        for user_id, data in self.users.items():
            user_elem = ET.SubElement(root, "user", id=str(user_id))
            # Динамически сохраняем все поля
            for key, value in data.items():
                # Пропускаем пустые значения (None), чтобы не засорять XML
                if value is not None:
                    ET.SubElement(user_elem, key).text = str(value)

        # Преобразование в строку с форматированием
        xml_str = ET.tostring(root, 'utf-8')
        pretty_xml_str = minidom.parseString(xml_str).toprettyxml(indent="   ")
        
        try:
            with open(self.file_path, "w", encoding='utf-8') as f:
                f.write(pretty_xml_str)
        except IOError as e:
             logger.error(f"Не удалось сохранить данные в файл {self.file_path}: {e}")

    def update_user_activity(self, user_id: int) -> None:
        """
        Обновляет данные о последней активности пользователя.
        Если пользователь новый, создает для него запись.
        """
        current_time_iso = datetime.now().isoformat()
        if user_id not in self.users:
            self.users[user_id] = DEFAULT_USER_STRUCTURE.copy()
            self.users[user_id]['first_seen'] = current_time_iso
            self.users[user_id]['interaction_count'] = 1
            logger.info(f"Зарегистрирован новый пользователь: {user_id}")
        else:
            # Увеличиваем счетчик взаимодействий, даже если его не было
            self.users[user_id]['interaction_count'] = self.users[user_id].get('interaction_count', 0) + 1
        
        self.users[user_id]['last_seen'] = current_time_iso
        self._save()

    def get_user_balance(self, user_id: int) -> int:
        """Возвращает баланс пользователя. Если пользователя нет, вернет 0."""
        return self.users.get(user_id, {}).get('balance', 0)

    def update_user_balance(self, user_id: int, amount_change: int) -> None:
        """
        Изменяет баланс пользователя на указанную величину (может быть отрицательной).
        
        Args:
            user_id (int): ID пользователя.
            amount_change (int): Сумма, на которую нужно изменить баланс.
        """
        if user_id in self.users:
            # Убедимся, что поле баланса существует, перед тем как его менять
            current_balance = self.users[user_id].get('balance', DEFAULT_USER_STRUCTURE['balance'])
            self.users[user_id]['balance'] = current_balance + amount_change
            logger.info(f"Баланс пользователя {user_id} изменен на {amount_change}. Новый баланс: {self.users[user_id]['balance']}")
            self._save()
        else:
            logger.warning(f"Попытка обновить баланс несуществующего пользователя: {user_id}")


    def check_and_apply_bankruptcy(self, user_id: int) -> bool:
        """
        Проверяет, не является ли пользователь банкротом (баланс < 100).
        Если да, восстанавливает его баланс до 100 дукатов.

        Returns:
            bool: True, если банкротство было применено, иначе False.
        """
        user_data = self.users.get(user_id)
        if user_data and user_data.get('balance', 0) < 100:
            self.users[user_id]['balance'] = 100
            logger.info(f"Применена программа банкротства для пользователя {user_id}. Новый баланс: 100.")
            self._save()
            return True
        return False

    def _check_and_update_cooldown(self, user_id: int, cooldown_key: str, cooldown_duration: timedelta) -> Tuple[bool, Optional[timedelta]]:
        """
        Универсальный метод для проверки и обновления временных ограничений (кулдаунов).

        Args:
            user_id (int): ID пользователя.
            cooldown_key (str): Ключ в словаре пользователя для хранения времени (e.g., 'last_work_time').
            cooldown_duration (timedelta): Длительность кулдауна.

        Returns:
            tuple[bool, timedelta | None]: (True, None) если действие разрешено,
                                            (False, time_left) если действие запрещено.
        """
        user_data = self.users.get(user_id, {})
        last_action_str = user_data.get(cooldown_key)

        if last_action_str:
            last_action_time = datetime.fromisoformat(last_action_str)
            if datetime.now() < last_action_time + cooldown_duration:
                time_left = (last_action_time + cooldown_duration) - datetime.now()
                return False, time_left

        # Убедимся, что пользователь существует, перед тем как записывать кулдаун
        if user_id not in self.users:
             self.update_user_activity(user_id)
             
        self.users[user_id][cooldown_key] = datetime.now().isoformat()
        self._save()
        return True, None

    # --- Публичные методы для проверки конкретных кулдаунов ---
    
    def check_work_cooldown(self, user_id: int) -> Tuple[bool, Optional[timedelta]]:
        """Проверяет кулдаун для работы (1 час)."""
        return self._check_and_update_cooldown(user_id, 'last_work_time', timedelta(hours=1))

    def check_stats_cooldown(self, user_id: int) -> Tuple[bool, Optional[timedelta]]:
        """Проверяет кулдаун для запроса статистики (1 час)."""
        return self._check_and_update_cooldown(user_id, 'last_stats_request_time', timedelta(hours=1))

    def check_race_cooldown(self, user_id: int) -> Tuple[bool, Optional[timedelta]]:
        """Проверяет кулдаун для участия в гонках (2 часа)."""
        return self._check_and_update_cooldown(user_id, 'last_race_time', timedelta(hours=2))

    def set_user_faction(self, user_id: int, faction: str) -> None:
        """Устанавливает фракцию для пользователя."""
        if user_id in self.users:
            self.users[user_id]['faction'] = faction
            logger.info(f"Пользователь {user_id} выбрал фракцию '{faction}'.")
            self._save()

    def get_all_users(self) -> Dict[int, Dict[str, Any]]:
        """Возвращает словарь со всеми пользователями и их данными."""
        return self.users


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