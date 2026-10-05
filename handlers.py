import asyncio
import logging
import re
from datetime import date
from io import BytesIO

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ai import AIService
from config import settings
from db import Database

router = Router()
logger = logging.getLogger(__name__)

START_TEXT = """Привет! Я бот для быстрого составления жалоб на форум Black Russia.

Как пользоваться (всё одним сообщением):

1. Сделай скриншот нарушения (обязательно с /time)

2. Залей его на фотохостинг (Imgur, Yapx, iBB и т.д.)

3. Отправь мне одним сообщением:

• Прикреплённое фото
• В подписи к фото напиши строго:

Nickname:твой_ник
Link:https://ссылка-на-фотохостинг

Пример:
Nickname:мяу_мяу
Link:https://ibb.co/abc123

Важно:
• Ник только в формате имя_фамилия (обе части с БОЛЬШОЙ буквы)
• Лимит — 5 жалоб в сутки
• Без даты и времени на скрине жалоба не пройдёт

Кидай скрин — я составлю жалобу."""

NICK_RE = re.compile(r"^[A-Z][a-z]*_[A-Z][a-z]*$")
CAPTION_RE = re.compile(
    r"^\s*Nickname\s*:\s*(?P<nickname>[^\n]+?)\s*\n\s*Link\s*:\s*(?P<link>https?://\S+)\s*$",
    re.IGNORECASE,
)


class AdminStates(StatesGroup):
    waiting_user_limit = State()
    waiting_global_limit = State()


def parse_caption(caption: str | None) -> tuple[str, str] | None:
    if not caption:
        return None
    match = CAPTION_RE.match(caption)
    if not match:
        return None
    return match.group("nickname").strip(), match.group("link").strip()


def valid_nickname(nickname: str) -> bool:
    return bool(NICK_RE.fullmatch(nickname))


def is_admin(message: Message | CallbackQuery) -> bool:
    user = message.from_user
    return user is not None and user.id == settings.admin_id


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Статус", callback_data="admin:status"),
                InlineKeyboardButton(text="📥 Экспорт .md", callback_data="admin:export"),
            ],
            [
                InlineKeyboardButton(text="👤 Лимит пользователя", callback_data="admin:user_limit"),
                InlineKeyboardButton(text="🌐 Общий лимит", callback_data="admin:global_limit"),
            ],
        ]
    )


@router.message(Command("start"))
async def start_handler(message: Message) -> None:
    await message.answer(START_TEXT)


@router.message(Command("admin_panel"))
async def admin_panel_handler(message: Message) -> None:
    if not is_admin(message):
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer(
        "🛠 <b>Админ-панель</b>\n\nВыбери действие:",
        reply_markup=admin_keyboard(),
    )


@router.callback_query(F.data == "admin:status")
async def admin_status(callback: CallbackQuery, db: Database) -> None:
    if not is_admin(callback):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    limit = await db.get_limit(-1, settings.default_daily_limit)
    logs = await db.count_logs()
    last_error = await db.get_last_ai_error()
    api_status = (
        f"🔴 Последняя ошибка API:\n<code>{last_error}</code>"
        if last_error
        else "🟢 Ошибок API в журнале нет."
    )
    await callback.answer()
    await callback.message.answer(
        "🟢 <b>Бот жив</b>\n"
        f"{api_status}\n"
        f"📏 Общий лимит: <b>{limit}</b>\n"
        f"📝 Записей AI-журнала: <b>{logs}</b>"
    )


@router.callback_query(F.data == "admin:export")
async def admin_export(callback: CallbackQuery, db: Database) -> None:
    if not is_admin(callback):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    await callback.answer("Готовлю файл…")
    content = await db.export_logs_markdown()
    file = BufferedInputFile(content.encode("utf-8"), filename="ai_logs.md")
    await callback.message.answer_document(file, caption="📥 Полный журнал обращений к ИИ.")


@router.callback_query(F.data == "admin:user_limit")
async def admin_user_limit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.waiting_user_limit)
    await callback.message.answer(
        "Отправь две строки:\n<code>user_id limit</code>\n\n"
        "Например: <code>123456789 10</code>\n"
        "Лимит 0 означает запрет новых запросов."
    )


@router.message(AdminStates.waiting_user_limit)
async def admin_set_user_limit(message: Message, state: FSMContext, db: Database) -> None:
    if not is_admin(message):
        await state.clear()
        await message.answer("⛔ Доступ запрещён.")
        return

    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Формат: <code>user_id limit</code>, например <code>123456789 10</code>.")
        return

    try:
        user_id, limit = int(parts[0]), int(parts[1])
        if user_id <= 0 or limit < 0:
            raise ValueError
    except ValueError:
        await message.answer("user_id должен быть положительным числом, limit — целым числом от 0.")
        return

    await db.set_user_limit(user_id, limit)
    await state.clear()
    await message.answer(f"✅ Для <code>{user_id}</code> установлен лимит <b>{limit}</b> в сутки.")


@router.callback_query(F.data == "admin:global_limit")
async def admin_global_limit_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AdminStates.waiting_global_limit)
    await callback.message.answer("Отправь новый общий лимит в сутки, например: <code>5</code>.")


@router.message(AdminStates.waiting_global_limit)
async def admin_set_global_limit(message: Message, state: FSMContext, db: Database) -> None:
    if not is_admin(message):
        await state.clear()
        await message.answer("⛔ Доступ запрещён.")
        return

    try:
        limit = int((message.text or "").strip())
        if limit < 0:
            raise ValueError
    except ValueError:
        await message.answer("Лимит должен быть целым числом от 0.")
        return

    await db.set_global_limit(limit)
    await state.clear()
    await message.answer(f"✅ Общий лимит установлен: <b>{limit}</b> в сутки.")


@router.message(F.photo)
async def complaint_handler(message: Message, bot, db: Database) -> None:
    user = message.from_user
    if user is None:
        await message.answer("Не удалось определить отправителя.")
        return

    parsed = parse_caption(message.caption)
    if parsed is None:
        await message.answer(
            "❌ Неверная подпись. Отправь <b>одно фото</b> с подписью ровно в формате:\n\n"
            "<code>Nickname:Abc_Dfs\nLink:https://example.com/...</code>"
        )
        return

    nickname, link = parsed
    if not valid_nickname(nickname):
        await message.answer(
            "❌ Некорректный Nickname. Нужен только латинский формат "
            "<code>Abc_Dfs</code>: ровно одна нижняя черта, две части, "
            "каждая начинается с заглавной буквы."
        )
        return

    admin = user.id == settings.admin_id
    today = date.today().isoformat()
    reserved = False

    if not admin:
        limit = await db.get_limit(user.id, settings.default_daily_limit)
        reserved = await db.reserve_slot(user.id, limit, today)
        if not reserved:
            count = await db.get_successful_count(user.id, today)
            await message.answer(
                f"❌ Дневной лимит исчерпан: <b>{count}/{limit}</b>. "
                "Новые успешные жалобы будут доступны завтра."
            )
            return

    request_text = (
        f"Telegram user: {user.full_name} | id={user.id}\n"
        f"Nickname: {nickname}\n"
        f"Link: {link}\n"
        "Image: attached Telegram photo"
    )

    status = await message.answer("⏳ Проверяю скриншот и составляю жалобу…")
    try:
        photo = message.photo[-1]
        image = await bot.download(photo)
        if image is None:
            raise RuntimeError("Не удалось скачать изображение из Telegram.")

        image_bytes = image.getvalue() if isinstance(image, BytesIO) else image.read()

        ai = AIService(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            model=settings.openai_model,
        )
        response = await ai.analyze(image_bytes, nickname, link)

        await db.log_ai_call(
            user_id=user.id,
            telegram_name=user.full_name,
            nickname=nickname,
            link=link,
            request_text=request_text,
            response_text=response,
            error_text=None,
        )

        # Лимит считается именно по успешным обращениям, а не по попыткам.
        # Для админа счётчик намеренно не увеличивается.
        if reserved:
            await db.finalize_success(user.id, today)

        await status.delete()
        for offset in range(0, len(response), 4000):
            await message.answer(response[offset : offset + 4000])
    except Exception as exc:
        logger.exception("AI request failed for user %s", user.id)
        if reserved:
            await db.release_slot(user.id, today)

        await db.log_ai_call(
            user_id=user.id,
            telegram_name=user.full_name,
            nickname=nickname,
            link=link,
            request_text=request_text,
            response_text=None,
            error_text=str(exc),
        )
        await status.edit_text(
            "⚠️ Не удалось обработать скриншот из-за технической ошибки. "
            "Попробуй ещё раз позже. Твоя попытка не списана."
        )


@router.message()
async def unsupported_message_handler(message: Message) -> None:
    if message.text and message.text.startswith("/"):
        await message.answer("Неизвестная команда. Используй /start.")
        return

    await message.answer(
        "Я принимаю только <b>одно фото с подписью</b> в формате:\n\n"
        "<code>Nickname:Abc_Dfs\nLink:https://example.com/...</code>"
    )
