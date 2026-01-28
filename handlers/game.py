import time
import asyncio
import random
import httpx
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.enums import ChatType

from config import BOT_USERNAME
from database import (
    upsert_game,
    get_game_by_chat_id,
    get_participants_with_answers,
    update_game_phase,
    save_game_options,
    get_game_options,
    get_poll_votes,
    add_user_score
)
from ai import generate_question


router = Router()

FACTS_API_URL = "https://uselessfacts.jsph.pl/api/v2/facts/random"
GAME_COOLDOWN = 60  # секунд між іграми
COLLECTING_DURATION = 70  # тривалість збору відповідей (1.5 хвилини)
VOTING_DURATION = 30  # тривалість голосування (1 хвилина)
UPDATE_INTERVAL = 10  # інтервал оновлення повідомлення

# Зберігаємо час останнього створення гри для кожного чату
_last_game_time: dict[str, float] = {}
# Зберігаємо активні таймери для кожного чату
_active_timers: dict[str, asyncio.Task] = {}


async def get_random_fact() -> str:
    """Отримує випадковий факт з API."""
    async with httpx.AsyncClient() as client:
        response = await client.get(FACTS_API_URL)
        response.raise_for_status()
        data = response.json()
        return data["text"]


def format_time_remaining(seconds: int) -> str:
    """Форматує залишок часу."""
    if seconds >= 60:
        minutes = seconds // 60
        secs = seconds % 60
        if secs > 0:
            return f"{minutes} хв {secs} сек"
        return f"{minutes} хв"
    return f"{seconds} сек"


def build_collecting_message(question: str, time_remaining: int) -> str:
    """Створює текст повідомлення для фази збору відповідей."""
    time_text = format_time_remaining(time_remaining)
    return (
        f"🎮 **Гра у Варіанти!**\n\n"
        f"{question}\n\n"
        f"⏱ Залишилось для відповідей: {time_text}"
    )


async def collecting_timer(bot: Bot, chat_id: str, question: str, message_id: int) -> None:
    """Таймер фази збору відповідей."""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎯 Дати відповідь",
            url=f"https://t.me/{BOT_USERNAME}?start={chat_id}"
        )]
    ])
    
    time_remaining = COLLECTING_DURATION
    
    try:
        while time_remaining > 0:
            await asyncio.sleep(UPDATE_INTERVAL)
            time_remaining -= UPDATE_INTERVAL
            
            # Перевіряємо чи гра ще у фазі збору
            game = await get_game_by_chat_id(chat_id)
            if not game or game.phase != "collecting":
                return
            
            if time_remaining > 0:
                # Оновлюємо повідомлення з новим часом
                try:
                    await bot.edit_message_text(
                        chat_id=int(chat_id),
                        message_id=message_id,
                        text=build_collecting_message(question, time_remaining),
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
        
        # Час збору вийшов - переходимо до голосування або завершуємо
        await finish_collecting_phase(bot, chat_id, message_id)
        
    except asyncio.CancelledError:
        pass
    finally:
        _active_timers.pop(chat_id, None)


async def finish_collecting_phase(bot: Bot, chat_id: str, message_id: int) -> None:
    """Завершує фазу збору та переходить до голосування."""
    game = await get_game_by_chat_id(chat_id)
    if not game:
        return
    
    # Отримуємо учасників з відповідями
    participants = await get_participants_with_answers(chat_id)
    
    # Перевіряємо чи достатньо відповідей
    if len(participants) < 2:
        # Недостатньо учасників - завершуємо гру
        await update_game_phase(chat_id, "finished")
        
        try:
            await bot.edit_message_text(
                chat_id=int(chat_id),
                message_id=message_id,
                text=(
                    f"😔 **Гра скасована**\n\n"
                    f"Недостатньо учасників (потрібно мінімум 2).\n\n"
                    f"📝 Питання було: {game.question}\n"
                    f"✅ Правильна відповідь: **{game.correct_answer}**\n\n"
                    f"💡 Факт: {game.fact}"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            await bot.send_message(
                chat_id=int(chat_id),
                text="😔 Гра скасована - недостатньо учасників.",
                parse_mode="Markdown"
            )
        return
    
    # Видаляємо повідомлення з питанням
    try:
        await bot.delete_message(chat_id=int(chat_id), message_id=message_id)
    except Exception:
        pass
    
    # Створюємо перемішаний список варіантів
    options = []
    
    # Додаємо варіанти учасників
    for p in participants:
        options.append((p.answer, p.user_id, False))
    
    # Додаємо правильну відповідь
    options.append((game.correct_answer, None, True))
    
    # Перемішуємо
    random.shuffle(options)
    
    # Зберігаємо варіанти в БД
    options_to_save = [
        (idx, text, author_id, is_correct)
        for idx, (text, author_id, is_correct) in enumerate(options)
    ]
    await save_game_options(chat_id, options_to_save)
    
    # Створюємо Poll
    poll_options = [text for text, _, _ in options]
    
    poll_msg = await bot.send_poll(
        chat_id=int(chat_id),
        question=f"🎯 {game.question}",
        options=poll_options,
        is_anonymous=False,  # Важливо! Щоб отримувати PollAnswer
        allows_multiple_answers=False
    )
    
    # Оновлюємо гру з poll_id
    await update_game_phase(
        chat_id,
        "voting",
        poll_id=poll_msg.poll.id,
        poll_message_id=poll_msg.message_id
    )
    
    # Запускаємо таймер голосування
    timer_task = asyncio.create_task(
        voting_timer(bot, chat_id, poll_msg.message_id)
    )
    _active_timers[chat_id] = timer_task


async def voting_timer(bot: Bot, chat_id: str, poll_message_id: int) -> None:
    """Таймер фази голосування."""
    try:
        await asyncio.sleep(VOTING_DURATION)
        
        # Перевіряємо чи гра ще у фазі голосування
        game = await get_game_by_chat_id(chat_id)
        if not game or game.phase != "voting":
            return
        
        # Завершуємо голосування
        await finish_voting_phase(bot, chat_id, poll_message_id)
        
    except asyncio.CancelledError:
        pass
    finally:
        _active_timers.pop(chat_id, None)


async def get_user_mention(bot: Bot, user_id: int) -> str:
    """Отримує inline mention користувача за ID."""
    try:
        chat = await bot.get_chat(user_id)
        name = chat.first_name or f"User{user_id}"
        return f"[{name}](tg://user?id={user_id})"
    except Exception:
        return f"[User{user_id}](tg://user?id={user_id})"


def format_points(points: int) -> str:
    """Форматує бали з правильним відмінюванням."""
    if points == 1:
        return "+1 бал"
    elif 2 <= points <= 4:
        return f"+{points} бали"
    else:
        return f"+{points} балів"


async def finish_voting_phase(bot: Bot, chat_id: str, poll_message_id: int) -> None:
    """Завершує голосування та показує результати."""
    game = await get_game_by_chat_id(chat_id)
    if not game:
        return
    
    # Закриваємо Poll
    try:
        await bot.stop_poll(chat_id=int(chat_id), message_id=poll_message_id)
    except Exception:
        pass
    
    # Оновлюємо фазу гри
    await update_game_phase(chat_id, "finished")
    
    # Отримуємо варіанти та голоси
    options = await get_game_options(chat_id)
    votes = await get_poll_votes(chat_id)
    
    # Створюємо мапу option_index -> option
    options_map = {opt.option_index: opt for opt in options}
    
    # Збираємо інформацію для результатів
    correct_voters: list[int] = []  # user_ids хто вгадав
    # option_index -> list of voter_ids (для варіантів гравців)
    option_voters: dict[int, list[int]] = {}
    
    for vote in votes:
        option = options_map.get(vote.option_index)
        if not option:
            continue
        
        if option.is_correct:
            correct_voters.append(vote.user_id)
        else:
            if vote.option_index not in option_voters:
                option_voters[vote.option_index] = []
            option_voters[vote.option_index].append(vote.user_id)
    
    # Підраховуємо бали
    score_changes: dict[int, int] = {}  # user_id -> points
    
    # +2 бали за правильну відповідь
    for user_id in correct_voters:
        score_changes[user_id] = score_changes.get(user_id, 0) + 2
    
    # +1 бал автору за кожен голос (крім голосу за себе)
    for option_idx, voter_ids in option_voters.items():
        option = options_map.get(option_idx)
        if option and option.author_user_id:
            author_id = option.author_user_id
            for voter_id in voter_ids:
                if voter_id != author_id:  # Не враховуємо голос за себе
                    score_changes[author_id] = score_changes.get(author_id, 0) + 1
    
    # Зберігаємо бали в БД
    for user_id, points in score_changes.items():
        await add_user_score(chat_id, user_id, points)
    
    # Формуємо повідомлення з результатами
    result_text = "🏆 Результати гри!\n"
    result_text += f"Питання: {game.question}\n\n"
    result_text += f"✅ Правильно: {game.correct_answer}\n"
    
    # Хто вгадав правильно
    if correct_voters:
        mentions = []
        for user_id in correct_voters:
            mention = await get_user_mention(bot, user_id)
            mentions.append(mention)
        result_text += f"({', '.join(mentions)}) {format_points(2)}\n\n"
    else:
        result_text += "(ніхто не вгадав)\n\n"
    
    # Інші відповіді гравців
    player_options = [opt for opt in options if not opt.is_correct and opt.author_user_id]
    for option in player_options:
        author_mention = await get_user_mention(bot, option.author_user_id)
        all_voters = option_voters.get(option.option_index, [])
        
        # Фільтруємо: не показуємо автора якщо він проголосував за себе
        voters = [v for v in all_voters if v != option.author_user_id]
        points_earned = len(voters)  # +1 бал за кожен голос від інших
        
        if voters:
            result_text += f"— {author_mention}: \"{option.option_text}\" {format_points(points_earned)}\n"
            voter_mentions = []
            for voter_id in voters:
                voter_mention = await get_user_mention(bot, voter_id)
                voter_mentions.append(voter_mention)
            result_text += f"({', '.join(voter_mentions)})\n\n"
        else:
            result_text += f"— {author_mention}: \"{option.option_text}\"\n\n"
    
    result_text += f"💡 Факт: {game.fact}"
    
    # Кнопка для нової гри
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Го ще одну", callback_data="new_game")]
    ])
    
    await bot.send_message(
        chat_id=int(chat_id),
        text=result_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )


def check_cooldown(chat_id: str) -> int | None:
    """Перевіряє cooldown. Повертає залишок секунд або None якщо можна грати."""
    current_time = time.time()
    last_time = _last_game_time.get(chat_id, 0)
    time_passed = current_time - last_time
    
    if time_passed < GAME_COOLDOWN:
        return int(GAME_COOLDOWN - time_passed)
    return None


async def start_new_game(bot: Bot, chat_id: str, status_msg: Message) -> None:
    """Створює нову гру."""
    # Скасовуємо попередній таймер якщо він існує
    if chat_id in _active_timers:
        _active_timers[chat_id].cancel()
    
    # Оновлюємо час останньої гри
    _last_game_time[chat_id] = time.time()
    
    try:
        # Отримуємо факт
        fact_text = await get_random_fact()
        
        # Генеруємо питання через AI
        question_data = await generate_question(fact_text)
        
        # Видаляємо статусне повідомлення
        await status_msg.delete()
        
        # Відправляємо повідомлення про гру
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🎯 Дати відповідь",
                url=f"https://t.me/{BOT_USERNAME}?start={chat_id}"
            )]
        ])
        
        game_msg = await bot.send_message(
            chat_id=int(chat_id),
            text=build_collecting_message(question_data.question, COLLECTING_DURATION),
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        # Зберігаємо в базу з message_id
        await upsert_game(
            chat_id=chat_id,
            question=question_data.question,
            correct_answer=question_data.answer,
            fact=question_data.fact,
            message_id=game_msg.message_id
        )
        
        # Запускаємо таймер збору відповідей
        timer_task = asyncio.create_task(
            collecting_timer(bot, chat_id, question_data.question, game_msg.message_id)
        )
        _active_timers[chat_id] = timer_task
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Помилка при створенні гри: {e}")


@router.message(Command("game"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_game(message: Message) -> None:
    """Обробник команди /game - створює нову гру."""
    chat_id = str(message.chat.id)
    bot = message.bot
    
    # Перевіряємо кулдаун
    remaining = check_cooldown(chat_id)
    if remaining:
        await message.answer(f"⏱ Зачекайте ще {remaining} сек. перед створенням нової гри.")
        return
    
    # Повідомляємо що гра створюється
    status_msg = await message.answer("⏳ Створюю нову гру...")
    await start_new_game(bot, chat_id, status_msg)


@router.callback_query(F.data == "new_game")
async def callback_new_game(callback: CallbackQuery) -> None:
    """Обробник кнопки 'Нова гра'."""
    chat_id = str(callback.message.chat.id)
    bot = callback.bot
    
    # Перевіряємо кулдаун
    remaining = check_cooldown(chat_id)
    if remaining:
        await callback.answer(f"⏱ Зачекайте ще {remaining} сек.", show_alert=True)
        return
    
    # Одразу ресетимо таймер щоб запобігти подвійному натисканню
    _last_game_time[chat_id] = time.time()
    
    await callback.answer()
    
    # Повідомляємо що гра створюється
    status_msg = await bot.send_message(
        chat_id=int(chat_id),
        text="⏳ Створюю нову гру..."
    )
    await start_new_game(bot, chat_id, status_msg)
