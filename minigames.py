from game_base import *

# --- ИГРОВЫЕ КОНСТАНТЫ ---
ROULETTE_PAYOUT_GREEN = 36
ROULETTE_PAYOUT_COLOR = 2
ROULETTE_RED_NUMBERS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
ROULETTE_BLACK_NUMBERS = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]

class DiceGame(Game):
    def get_rules_text(self, balance: int, bet: int) -> str:
        bet_text = f"Текущая ставка: *{bet:,}* дукатов." if bet > 0 else "Отправьте в чат сумму, которую хотите поставить."
        return (
            f"🎲 *Игра в кости* 🎲\n\n"
            f"Ваш баланс: *{balance:,}* дукатов.\n"
            f"{bet_text}\n\n"
            "*Правила:*\n"
            "- Сумма 3 кубиков *> 12*: выигрыш *x2*.\n"
            "- Сумма 3 кубиков *< 12*: вы теряете ставку.\n"
            "- Сумма = *12*: выигрыш *x0.5* (возврат половины ставки).\n"
            "- *2* одинаковых кубика (пара): ничья, ставка возвращается.\n"
            "- *3* одинаковых кубика (тройка): выигрыш *x10*."
        )

    def get_game_keyboard(self, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
        current_bet = context.user_data.get('current_bet', 0)
        bet_text = f"Ставка: {current_bet:,} дукатов" if current_bet > 0 else "Сделайте ставку!"
        keyboard = [
            [InlineKeyboardButton(bet_text, callback_data='do_nothing')],
            [InlineKeyboardButton("🎲 Бросить кубики!", callback_data=f'game:play:{self.id}')],
            [
                InlineKeyboardButton("x2", callback_data=f'game:modify:{self.id}:multiply:2'),
                InlineKeyboardButton("x10", callback_data=f'game:modify:{self.id}:multiply:10'),
                InlineKeyboardButton("x50", callback_data=f'game:modify:{self.id}:multiply:50'),
            ],
            [InlineKeyboardButton("💥 ALL-IN 💥", callback_data=f'game:modify:{self.id}:allin')],
            [
                InlineKeyboardButton("✏️ Новая ставка", callback_data=f'game:start:{self.id}:new'),
                InlineKeyboardButton("⬅️ Выйти", callback_data='nav:games')
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def play(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        user_id = query.from_user.id
        bet = context.user_data.get('current_bet', 0)

        self.user_manager.update_user_balance(user_id, -bet)
        d1, d2, d3 = random.randint(1, 6), random.randint(1, 6), random.randint(1, 6)
        dice_sum = d1 + d2 + d3
        dice_icons = {1: '⚀', 2: '⚁', 3: '⚂', 4: '⚃', 5: '⚄', 6: '⚅'}
        result_text = f"Ваша ставка: *{bet:,}*\nВыпало: {dice_icons[d1]} {dice_icons[d2]} {dice_icons[d3]} = *{dice_sum}*\n\n"
        
        winnings = 0
        if d1 == d2 == d3:
            winnings = bet * 10
            result_text += f"💰 *ТРОЙКА!* Выигрыш *x10*: `+{winnings:,}`"
        elif d1 == d2 or d1 == d3 or d2 == d3:
            winnings = bet
            result_text += f"😐 *ПАРА!* Ничья, ваша ставка возвращена: `+{winnings:,}`"
        elif dice_sum > 12:
            winnings = bet * 2
            result_text += f"🎉 *ПОБЕДА!* Сумма больше 12. Выигрыш *x2*: `+{winnings:,}`"
        elif dice_sum == 12:
            winnings = int(bet * 0.5)
            result_text += f"🤔 *СУММА 12!* Возврат половины ставки: `+{winnings:,}`"
        else:
            winnings = 0
            result_text += f"😥 *ПОРАЖЕНИЕ!* Вы проиграли: `0`"
        
        if winnings > 0:
            self.user_manager.update_user_balance(user_id, winnings)
        
        final_balance = self.user_manager.get_user_balance(user_id)
        result_text += f"\n\nВаш итоговый баланс: *{final_balance:,}* дукатов."
        await query.edit_message_text(result_text, reply_markup=self.get_replay_keyboard(), parse_mode='Markdown')

class RouletteGame(Game):
    def get_rules_text(self, balance: int, bet: int) -> str:
        bet_text = f"Текущая ставка: *{bet:,}* дукатов." if bet > 0 else "Отправьте в чат сумму, которую хотите поставить."
        return (
            f"🎡 *Европейская рулетка* 🎡\n\n"
            f"Ваш баланс: *{balance:,}* дукатов.\n"
            f"{bet_text}\n\n"
            f"*Правила:*\n"
            f"- *Красное* или *Чёрное*: выигрыш *x{ROULETTE_PAYOUT_COLOR}*.\n"
            f"- *Зелёное (Зеро)*: выигрыш *x{ROULETTE_PAYOUT_GREEN}*."
        )

    def get_game_keyboard(self, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
        current_bet = context.user_data.get('current_bet', 0)
        bet_text = f"Ставка: {current_bet:,}" if current_bet > 0 else "Сделайте ставку!"
        keyboard = [
            [InlineKeyboardButton(bet_text, callback_data='do_nothing')],
            [
                InlineKeyboardButton(f"🔴 Красное", callback_data=f'game:play:{self.id}:red'),
                InlineKeyboardButton(f"⚫️ Чёрное", callback_data=f'game:play:{self.id}:black')
            ],
            [InlineKeyboardButton(f"🟢 Зеро", callback_data=f'game:play:{self.id}:green')],
            [
                InlineKeyboardButton("x2", callback_data=f'game:modify:{self.id}:multiply:2'),
                InlineKeyboardButton("x10", callback_data=f'game:modify:{self.id}:multiply:10'),
                InlineKeyboardButton("x50", callback_data=f'game:modify:{self.id}:multiply:50'),
            ],
            [InlineKeyboardButton("💥 ALL-IN 💥", callback_data=f'game:modify:{self.id}:allin')],
            [InlineKeyboardButton("✏️ Новая ставка", callback_data=f'game:start:{self.id}:new')],
            [InlineKeyboardButton("⬅️ Выйти", callback_data='nav:games')]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def play(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        user_id = query.from_user.id
        bet = context.user_data.get('current_bet', 0)
        
        self.user_manager.update_user_balance(user_id, -bet)
        roll = random.randint(0, 36)
        
        winning_color, winning_color_icon = None, ""
        if roll == 0: winning_color, winning_color_icon = "green", "🟢"
        elif roll in ROULETTE_RED_NUMBERS: winning_color, winning_color_icon = "red", "🔴"
        else: winning_color, winning_color_icon = "black", "⚫️"
            
        result_text = f"Ваша ставка: *{bet:,}*\nВыпало: {winning_color_icon} *{roll} {winning_color.capitalize()}*\n\n"
        
        player_choice = query.data.split(':')[-1]
        winnings = 0
        if player_choice == winning_color:
            payout = ROULETTE_PAYOUT_GREEN if winning_color == "green" else ROULETTE_PAYOUT_COLOR
            winnings = bet * payout
            result_text += f"🎉 *ПОБЕДА!* Ваш выигрыш: `+{winnings:,}`"
        else:
            result_text += f"😥 *ПОРАЖЕНИЕ!* Увы, вы проиграли: `0`"

        if winnings > 0:
            self.user_manager.update_user_balance(user_id, winnings)
            
        final_balance = self.user_manager.get_user_balance(user_id)
        result_text += f"\n\nВаш итоговый баланс: *{final_balance:,}* дукатов."
        await query.edit_message_text(result_text, reply_markup=self.get_replay_keyboard(), parse_mode='Markdown')

class CoinFlipGame(Game):
    def get_rules_text(self, balance: int, bet: int) -> str:
        bet_text = f"Текущая ставка: *{bet:,}* дукатов." if bet > 0 else "Отправьте в чат сумму, которую хотите поставить."
        return (
            f"🪙 *Орёл или Решка* 🪙\n\n"
            f"Ваш баланс: *{balance:,}* дукатов.\n"
            f"{bet_text}\n\n"
            f"*Правила:*\n"
            f"- Ставите на одну из сторон. Угадали - выигрыш *x2*.\n"
            f"- Не угадали - теряете ставку."
        )

    def get_game_keyboard(self, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
        current_bet = context.user_data.get('current_bet', 0)
        bet_text = f"Ставка: {current_bet:,}" if current_bet > 0 else "Сделайте ставку!"
        keyboard = [
            [InlineKeyboardButton(bet_text, callback_data='do_nothing')],
            [
                InlineKeyboardButton("🦅 Орёл", callback_data=f'game:play:{self.id}:heads'),
                InlineKeyboardButton("🪙 Решка", callback_data=f'game:play:{self.id}:tails')
            ],
            [
                InlineKeyboardButton("x2", callback_data=f'game:modify:{self.id}:multiply:2'),
                InlineKeyboardButton("x10", callback_data=f'game:modify:{self.id}:multiply:10'),
                InlineKeyboardButton("x50", callback_data=f'game:modify:{self.id}:multiply:50'),
            ],
            [InlineKeyboardButton("💥 ALL-IN 💥", callback_data=f'game:modify:{self.id}:allin')],
            [InlineKeyboardButton("✏️ Новая ставка", callback_data=f'game:start:{self.id}:new')],
            [InlineKeyboardButton("⬅️ Выйти", callback_data='nav:games')]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def play(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        user_id = query.from_user.id
        bet = context.user_data.get('current_bet', 0)

        self.user_manager.update_user_balance(user_id, -bet)
        
        # Симулируем бросок
        result = random.choice(['heads', 'tails'])
        player_choice = query.data.split(':')[-1]

        result_icon = "🦅" if result == 'heads' else "🪙"
        result_word = "Орёл" if result == 'heads' else "Решка"
        result_text = f"Ваша ставка: *{bet:,}*\nМонетка подброшена... Выпал: {result_icon} *{result_word}*!\n\n"

        winnings = 0
        if player_choice == result:
            winnings = bet * 2
            result_text += f"🎉 *ПОБЕДА!* Вы угадали! Ваш выигрыш: `+{winnings:,}`"
        else:
            winnings = 0
            result_text += f"😥 *ПОРАЖЕНИЕ!* В следующий раз повезёт: `0`"
        
        if winnings > 0:
            self.user_manager.update_user_balance(user_id, winnings)
        
        final_balance = self.user_manager.get_user_balance(user_id)
        result_text += f"\n\nВаш итоговый баланс: *{final_balance:,}* дукатов."
        await query.edit_message_text(result_text, reply_markup=self.get_replay_keyboard(), parse_mode='Markdown')
