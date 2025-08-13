# Файл: blackjack_game.py

import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from game_base import Game # Импортируем только базовый класс

# --- Вспомогательные элементы для Блэкджека ---
SUITS = {"hearts": "♥️", "diamonds": "♦️", "clubs": "♣️", "spades": "♠️"}
RANKS = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, 
         "10": 10, "J": 10, "Q": 10, "K": 10, "A": 11}

def _create_deck():
    """Создает стандартную перемешанную колоду из 52 карт."""
    deck = [(suit, rank) for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck

def _get_hand_properties(hand):
    """Подсчитывает стоимость руки и определяет, является ли она 'мягкой'."""
    value = sum(RANKS[card[1]] for card in hand)
    num_aces = sum(1 for card in hand if card[1] == 'A')
    
    while value > 21 and num_aces:
        value -= 10
        num_aces -= 1
    
    is_soft = num_aces > 0
    return value, is_soft

def _render_hand(hand, is_dealer_initial=False):
    """Красиво отображает карты и их сумму."""
    if is_dealer_initial:
        return f"{SUITS[hand[0][0]]}{hand[0][1]}  [?]"
    
    cards_str = "  ".join(f"{SUITS[suit]}{rank}" for suit, rank in hand)
    value, _ = _get_hand_properties(hand)
    value_str = f" (*{value}*)"
    if value > 21:
        value_str = f" (*Перебор: {value}*)"
    elif len(hand) == 2 and value == 21:
        value_str = " (*Блэкджек!*)"
        
    return f"{cards_str}{value_str}"


class BlackjackGame(Game):
    """
    Класс для игры в Блэкджек.
    """
    def get_rules_text(self, balance: int, bet: int) -> str:
        bet_text = f"Текущая ставка: *{bet:,}* дукатов." if bet > 0 else "Отправьте в чат сумму, которую хотите поставить."
        return (
            f"🃏 *Блэкджек* 🃏\n\n"
            f"Ваш баланс: *{balance:,}* дукатов.\n"
            f"{bet_text}\n\n"
            "*Цель:* набрать очков больше, чем у дилера, но не больше 21.\n"
            "- *Блэкджек* (Туз + 10) оплачивается 3 к 2.\n"
            "- Обычный выигрыш оплачивается 1 к 1.\n"
            "- Дилер обязан брать до 16 включительно и на 'мягкие 17', а останавливаться на 'жестких 17' и выше."
        )

    def get_game_keyboard(self, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
        """Возвращает клавиатуру для текущего состояния игры."""
        state = context.user_data.get('blackjack_state')

        # Если игра не началась (только сделали ставку), показываем кнопку "Раздать"
        if not state:
            current_bet = context.user_data.get('current_bet', 0)
            bet_text = f"Ставка: {current_bet:,}" if current_bet > 0 else "Сделайте ставку!"
            keyboard = [
                [InlineKeyboardButton(bet_text, callback_data='do_nothing')],
                # Эта кнопка инициирует `play` с action='start'
                [InlineKeyboardButton("🃏 Раздать карты", callback_data=f'game:play:{self.id}:start')],
                [InlineKeyboardButton("⬅️ Вернуться в Игровой Клуб", callback_data='nav:games')]
            ]
            return InlineKeyboardMarkup(keyboard)

        # Если игра завершена, показываем клавиатуру для повторной игры
        if state.get('game_over', True):
            return self.get_replay_keyboard() 
        
        # Клавиатура во время хода игрока
        buttons = [
            InlineKeyboardButton("➕ Взять ещё", callback_data=f'game:play:{self.id}:hit'),
            InlineKeyboardButton("✋ Хватит", callback_data=f'game:play:{self.id}:stand')
        ]
        if state.get('can_double'):
            buttons.append(InlineKeyboardButton("💰 Удвоить", callback_data=f'game:play:{self.id}:double'))
        
        return InlineKeyboardMarkup([buttons])

    async def _start_new_hand(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинает новый раунд блэкджека после того, как ставка сделана."""
        query = update.callback_query
        user_id = query.from_user.id
        bet = context.user_data.get('current_bet', 0)
        balance = self.user_manager.get_user_balance(user_id)

        if not bet or bet <= 0:
            await query.answer("Сначала нужно сделать ставку!", show_alert=True)
            return

        # --- ИЗМЕНЕНИЯ ЗДЕСЬ ---
        # Если баланс изменился и ставка стала недействительной
        if bet > balance:
            # 1. Формируем понятное сообщение об ошибке
            error_text = (
                f"❌ *Ошибка ставки!*\n\n"
                f"Ваш баланс (*{balance:,}*) теперь недостаточен для ранее установленной ставки в *{bet:,}* дукатов.\n\n"
                "Пожалуйста, отправьте в чат новую, корректную ставку."
            )
            # 2. Сбрасываем недействительную ставку
            context.user_data.pop('current_bet', None)
            # 3. Сбрасываем состояние игры на всякий случай
            context.user_data.pop('blackjack_state', None)
            # 4. Устанавливаем состояние ожидания новой ставки для роутера сообщений
            context.user_data['game_state'] = f'awaiting_bet:{self.id}'

            # 5. Редактируем сообщение, чтобы вернуть пользователя к этапу ввода ставки
            await query.edit_message_text(
                text=error_text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Вернуться в Игровой Клуб", callback_data='nav:games')]])
            )
            return
        # --- КОНЕЦ ИЗМЕНЕНИЙ ---

        deck = _create_deck()
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]

        # Ставка списывается только в момент раздачи
        self.user_manager.update_user_balance(user_id, -bet)
        balance_after_bet = self.user_manager.get_user_balance(user_id)

        context.user_data['blackjack_state'] = {
            'deck': deck, 'player_hand': player_hand, 'dealer_hand': dealer_hand,
            'bet': bet, 'game_over': False, 'doubled': False,
            'can_double': balance_after_bet >= bet
        }
        
        player_value, _ = _get_hand_properties(player_hand)
        
        if player_value == 21:
            await self._end_game(update, context)
        else:
            await self._render_game_state(update, context)

    async def _render_game_state(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отрисовывает текущее состояние стола."""
        query = update.callback_query
        state = context.user_data['blackjack_state']
        user_id = query.from_user.id
        current_balance = self.user_manager.get_user_balance(user_id)
        
        text = (
            f"Ваша рука: {_render_hand(state['player_hand'])}\n"
            f"Рука дилера: {_render_hand(state['dealer_hand'], is_dealer_initial=True)}\n\n"
            f"Ваша ставка: *{state['bet']:,}* дукатов.\n"
            f"Ваш баланс: *{current_balance:,}* дукатов."
        )
        await query.edit_message_text(text, reply_markup=self.get_game_keyboard(context), parse_mode='Markdown')

    async def _dealer_turn(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Логика хода дилера."""
        state = context.user_data['blackjack_state']
        while True:
            dealer_value, is_soft = _get_hand_properties(state['dealer_hand'])
            if dealer_value > 17 or (dealer_value == 17 and not is_soft):
                break
            state['dealer_hand'].append(state['deck'].pop())
        await self._end_game(update, context)

    async def _end_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Определяет победителя и завершает игру."""
        query = update.callback_query
        user_id = query.from_user.id
        state = context.user_data.get('blackjack_state')
        if not state or state.get('game_over'): return

        state['game_over'] = True
        
        player_value, _ = _get_hand_properties(state['player_hand'])
        dealer_value, _ = _get_hand_properties(state['dealer_hand'])
        player_busted = player_value > 21
        dealer_busted = dealer_value > 21
        player_has_blackjack = player_value == 21 and len(state['player_hand']) == 2 and not state['doubled']
        dealer_has_blackjack = dealer_value == 21 and len(state['dealer_hand']) == 2

        result_text = f"Ваша рука: {_render_hand(state['player_hand'])}\nРука дилера: {_render_hand(state['dealer_hand'])}\n\n"
        
        payout = 0
        bet = state['bet']
        
        if player_busted:
            result_text += "😥 *Перебор!* Вы проиграли."
            payout = 0
        elif player_has_blackjack and not dealer_has_blackjack:
            result_text += "🤑 *БЛЭКДЖЕК!* Выигрыш 3 к 2!"
            payout = bet + int(bet * 1.5) # Возврат ставки + выигрыш 1.5x
        elif dealer_busted:
            result_text += "🎉 *Победа!* У дилера перебор."
            payout = bet * 2 # Возврат ставки + выигрыш 1x
        elif dealer_has_blackjack and not player_has_blackjack:
             result_text += "😥 *Поражение!* У дилера блэкджек."
             payout = 0
        elif player_value > dealer_value:
            result_text += "🎉 *Победа!* Ваши очки выше."
            payout = bet * 2
        elif player_value < dealer_value:
            result_text += "😥 *Поражение!* Очки дилера выше."
            payout = 0
        else: # Ничья
            result_text += "😐 *Ничья (Push)!* Ставка возвращена."
            payout = bet

        if payout > 0:
            self.user_manager.update_user_balance(user_id, payout)
            
        final_balance = self.user_manager.get_user_balance(user_id)
        result_text += f"\n\nВаш итоговый баланс: *{final_balance:,}* дукатов."
        
        # Очищаем состояние для следующей игры
        context.user_data.pop('blackjack_state', None)
        context.user_data.pop('current_bet', None)

        await query.edit_message_text(result_text, reply_markup=self.get_replay_keyboard(), parse_mode='Markdown')

    async def play(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Центральный обработчик действий игрока для уже идущей игры."""
        query = update.callback_query
        user_id = query.from_user.id
        action = query.data.split(':')[-1]
        
        if action == 'start':
            await self._start_new_hand(update, context)
            return
            
        state = context.user_data.get('blackjack_state')
        if not state or state.get('game_over'):
            await query.answer("Эта игра уже завершена. Начните новую.", show_alert=True)
            return

        state['can_double'] = False

        if action == 'hit':
            state['player_hand'].append(state['deck'].pop())
            if _get_hand_properties(state['player_hand'])[0] > 21:
                await self._end_game(update, context)
            else:
                await self._render_game_state(update, context)
        
        elif action == 'stand':
            await self._dealer_turn(update, context)

        elif action == 'double':
            original_bet = state['bet']
            balance = self.user_manager.get_user_balance(user_id)
            if balance < original_bet:
                 await query.answer(f"Не хватает {original_bet:,} для удвоения!", show_alert=True)
                 state['can_double'] = True
                 return
            
            self.user_manager.update_user_balance(user_id, -original_bet)
            state['bet'] *= 2
            state['doubled'] = True
            state['player_hand'].append(state['deck'].pop())
            
            await query.answer(f"Ставка удвоена до {state['bet']:,}! Вы получаете одну карту.", show_alert=True)
            
            if _get_hand_properties(state['player_hand'])[0] > 21:
                await self._end_game(update, context)
            else:
                await self._dealer_turn(update, context)