from aiogram import Router

from .game import router as game_router
from .start import router as start_router
from .variant import router as variant_router
from .poll import router as poll_router


def setup_routers() -> Router:
    """Створює головний роутер та підключає всі хендлери."""
    router = Router()
    router.include_router(game_router)
    router.include_router(start_router)
    router.include_router(variant_router)
    router.include_router(poll_router)
    return router
