import re
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.enums import ChatType

from database import (
    get_game_by_chat_id,
    get_participant,
    add_participant,
    get_participants_count,
    get_leaderboard,
    get_daily_top_players
)

RULES_TEXT = """🎮 <b>Правила гри "Варіанти"</b>

1️⃣ Хтось пише /game — бот задає питання на основі цікавого факту

2️⃣ Кожен учасник натискає "Дати відповідь" і пише боту в особисті свій <b>неправильний, але правдоподібний</b> варіант відповіді

3️⃣ Після збору відповідей бот створює опитування, де всі варіанти перемішані з правильною відповіддю

4️⃣ Голосуйте за те, що вважаєте правильним!

<b>📊 Бали:</b>
• +2 — якщо вгадали правильну відповідь
• +1 — за кожного гравця, якого обдурив ваш варіант

<b>⏱ Тайминги:</b>
• 70 сек — на збір відповідей
• 30 сек — на голосування

💡 <b>Мета:</b> вигадати такий варіант, щоб інші повірили, що він правильний!"""

router = Router()

MAX_PARTICIPANTS = 9  # 10 варіантів в poll - 1 правильна відповідь


@router.message(CommandStart(deep_link=True), F.chat.type == ChatType.PRIVATE)
async def cmd_start_with_game(message: Message, command: CommandObject) -> None:
    """Обробник команди /start {chat_id} - приєднання до гри."""
    user_id = message.from_user.id
    args = command.args
    
    # Перевіряємо що args - це chat_id (число, можливо від'ємне)
    if not args or not re.match(r"^-?\d+$", args):
        await message.answer(
            "Привіт! Я бот для гри Варіанти.\n\n"
            "Щоб почати гру, додай мене до групи і напиши там /game"
        )
        return
    
    game_chat_id = args
    
    # Перевіряємо чи гра існує та активна (фаза збору відповідей)
    game = await get_game_by_chat_id(game_chat_id)
    
    if not game or game.phase != "collecting":
        await message.answer("Активну гру не знайдено або час на відповіді вийшов :(")
        return
    
    # Перевіряємо чи користувач вже брав участь
    participant = await get_participant(game_chat_id, user_id)
    
    if participant:
        if participant.answer:
            await message.answer("Здається ти вже дав свій варіант...")
        else:
            # Вже зареєстрований, але ще не відповів - нагадуємо питання
            await message.answer(
                f"Дай свій правдоподібний але неправильний варіант відповіді на запитання:\n\n"
                f"_{game.question}_",
                parse_mode="Markdown"
            )
        return
    
    # Перевіряємо ліміт учасників
    participants_count = await get_participants_count(game_chat_id)
    if participants_count >= MAX_PARTICIPANTS:
        await message.answer("Вибачте, всі місця зайняті (максимум 9 учасників)")
        return
    
    # Додаємо учасника
    added = await add_participant(game_chat_id, user_id)
    
    if not added:
        await message.answer("Здається ти вже дав свій варіант...")
        return
    
    # Відправляємо питання
    await message.answer(
        f"Дай свій правдоподібний але неправильний варіант відповіді на запитання:\n\n"
        f"_{game.question}_",
        parse_mode="Markdown"
    )


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message) -> None:
    """Обробник простої команди /start без параметрів."""
    await message.answer(
        "Привіт! Я бот для гри Варіанти.\n\n"
        "Щоб почати гру, додай мене до групи і напиши там /game\n\n"
        "Напиши /rules щоб дізнатися правила"
    )


@router.message(Command("rules"))
async def cmd_rules(message: Message) -> None:
    """Обробник команди /rules - показує правила гри."""
    await message.answer(RULES_TEXT)


async def get_user_mention(bot: Bot, user_id: int) -> str:
    """Отримує inline mention користувача за ID."""
    try:
        chat = await bot.get_chat(user_id)
        name = chat.first_name or f"User{user_id}"
        return f"[{name}](tg://user?id={user_id})"
    except Exception:
        return f"[User{user_id}](tg://user?id={user_id})"


@router.message(Command("scores"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_scores(message: Message) -> None:
    """Обробник команди /scores - показує рейтинг гравців."""
    chat_id = str(message.chat.id)
    bot = message.bot
    
    # Отримуємо топ 3 гравців за день
    daily_top = await get_daily_top_players(chat_id, limit=3)
    
    # Отримуємо загальний топ 10
    leaderboard = await get_leaderboard(chat_id, limit=10)
    
    if not leaderboard:
        await message.answer("📊 Ще немає результатів. Почніть гру командою /game")
        return
    
    result_text = ""
    
    # Топ 3 гравців за день
    if daily_top:
        result_text += "🌟 *Топ гравці за сьогодні:*\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, player in enumerate(daily_top):
            mention = await get_user_mention(bot, player.user_id)
            result_text += f"{medals[i]} {mention} — {player.score}\n"
        result_text += "\n"
    
    # Загальний рейтинг
    result_text += "🏆 *Загальний рейтинг (топ 10):*\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    for i, player in enumerate(leaderboard):
        mention = await get_user_mention(bot, player.user_id)
        prefix = medals[i] if i < 3 else f"{i + 1}."
        result_text += f"{prefix} {mention} — {player.score}\n"
    
    await message.answer(result_text, parse_mode="Markdown")
