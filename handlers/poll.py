from aiogram import Router
from aiogram.types import PollAnswer

from database import get_game_by_poll_id, save_poll_vote


router = Router()


@router.poll_answer()
async def on_poll_answer(poll_answer: PollAnswer) -> None:
    """Обробник голосів у Poll."""
    poll_id = poll_answer.poll_id
    user_id = poll_answer.user.id
    
    # Знаходимо гру за poll_id
    game = await get_game_by_poll_id(poll_id)
    
    if not game:
        return
    
    # Перевіряємо що гра у фазі голосування
    if game.phase != "voting":
        return
    
    # Отримуємо вибраний варіант (беремо перший, бо multiple answers = False)
    if not poll_answer.option_ids:
        return
    
    option_index = poll_answer.option_ids[0]
    
    # Зберігаємо голос
    await save_poll_vote(game.chat_id, user_id, option_index)
