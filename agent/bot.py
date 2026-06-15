"""
DacherForge — Control Bot
Красивый управляющий бот для AI SDR агента.

Функции:
  • Настройка ICP через пошаговую анкету (кнопка "🎯 Настроить ICP")
  • Гайд "❓ Как пользоваться агентом?"
  • Статистика и метрики
  • Управление группами и кампаниями
  • Просмотр найденных лидов

Бот пишет конфиг в campaigns.json (его читает userbot.py)
и читает метрики из sdr.db.

Запуск:  python3 bot.py
Зависимости:  pip install python-telegram-bot
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# =============================================================================
# CONFIG
# =============================================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
CAMPAIGNS_FILE = "/root/outreach/campaigns.json"
DB_FILE = "/root/outreach/sdr.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# Conversation states для ICP-анкеты
(
    Q_COMPANY,
    Q_NICHE,
    Q_PRODUCT,
    Q_AUDIENCE,
    Q_PAIN,
    Q_VALUE,
    Q_GEO,
    Q_PRICE,
    Q_CTA,
    Q_KEYWORDS,
    Q_NEGATIVE,
    Q_TONE,
) = range(12)

# Список вопросов анкеты: (state, ключ, текст вопроса, подсказка-пример)
ICP_QUESTIONS = [
    (Q_COMPANY, "company_name", "1/12 🏢 Как называется ваша компания?",
     "Например: <i>Dacher Digital</i>"),
    (Q_NICHE, "company_description", "2/12 💼 Чем занимается ваша компания? Опишите сферу/нишу.",
     "Например: <i>digital-агентство, делаем сайты и настраиваем рекламу</i>"),
    (Q_PRODUCT, "product", "3/12 📦 Что именно вы продаёте? Продукт или услуга.",
     "Например: <i>разработка сайтов под ключ + SMM-сопровождение</i>"),
    (Q_AUDIENCE, "target_audience", "4/12 🎯 Кто ваш идеальный клиент? Опишите портрет.",
     "Например: <i>малый бизнес, владельцы магазинов, которым нужен поток заявок</i>"),
    (Q_PAIN, "pain_points", "5/12 🔥 Какие проблемы клиента решает ваш продукт?",
     "Например: <i>мало заявок, нет сайта, сливают бюджет на рекламу</i>"),
    (Q_VALUE, "value_proposition", "6/12 ⭐ В чём ваше главное преимущество? Почему выбирают вас?",
     "Например: <i>результат за 2 недели, фикс цена, гарантия лидов</i>"),
    (Q_GEO, "geo", "7/12 📍 В каком городе/регионе ищем клиентов?",
     "Например: <i>Москва</i> (или напишите <i>СНГ</i> / <i>любой</i>)"),
    (Q_PRICE, "price_range", "8/12 💰 Какой средний чек или диапазон цен?",
     "Например: <i>от 50 000 ₽</i>"),
    (Q_CTA, "cta", "9/12 🤝 Какое целевое действие вы хотите от лида?",
     "Например: <i>15-минутный созвон</i> / <i>демо</i> / <i>заявка на сайте</i>"),
    (Q_KEYWORDS, "icp_keywords", "10/12 🔑 По каким фразам видно, что человек — ваш потенциальный клиент?",
     "Через запятую. Например: <i>ищу клиентов, нужен сайт, мало заявок, нужна реклама</i>"),
    (Q_NEGATIVE, "icp_negative_keywords", "11/12 🚫 Кому писать НЕ нужно? Стоп-слова.",
     "Через запятую. Например: <i>ищу работу, резюме, вакансия, студент</i>"),
    (Q_TONE, "tone", "12/12 🎨 В каком тоне общаться с лидами?",
     "Например: <i>дружелюбный</i> / <i>деловой</i> / <i>экспертный</i>"),
]


# =============================================================================
# ХРАНИЛИЩЕ КАМПАНИЙ
# =============================================================================
def load_campaigns() -> dict:
    if not os.path.exists(CAMPAIGNS_FILE):
        return {}
    try:
        with open(CAMPAIGNS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("load_campaigns: %s", e)
        return {}


def save_campaigns(data: dict):
    os.makedirs(os.path.dirname(CAMPAIGNS_FILE), exist_ok=True)
    with open(CAMPAIGNS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def campaign_id_for(chat_id: int) -> str:
    return f"campaign_{chat_id}"


def get_campaign(chat_id: int) -> dict | None:
    return load_campaigns().get(campaign_id_for(chat_id))


def upsert_campaign(chat_id: int, fields: dict):
    campaigns = load_campaigns()
    cid = campaign_id_for(chat_id)
    if cid not in campaigns:
        campaigns[cid] = {
            "id": cid,
            "status": "active",
            "groups": [],
            "owner_chat_id": chat_id,
        }
    campaigns[cid].update(fields)
    save_campaigns(campaigns)


# =============================================================================
# КЛАВИАТУРЫ
# =============================================================================
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎯 Настроить ICP", callback_data="icp_start")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats"),
         InlineKeyboardButton("📈 Лиды", callback_data="leads")],
        [InlineKeyboardButton("👥 Мои группы", callback_data="groups"),
         InlineKeyboardButton("🧠 Стратегии", callback_data="strategies")],
        [InlineKeyboardButton("▶️ Запустить / ⏸ Пауза", callback_data="toggle")],
        [InlineKeyboardButton("❓ Как пользоваться агентом?", callback_data="guide")],
    ])


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="menu")]
    ])


def icp_review_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Сохранить", callback_data="icp_save")],
        [InlineKeyboardButton("🔄 Заполнить заново", callback_data="icp_start")],
        [InlineKeyboardButton("⬅️ В главное меню", callback_data="menu")],
    ])


# =============================================================================
# ТЕКСТЫ
# =============================================================================
WELCOME = (
    "👋 <b>Добро пожаловать в DacherForge AI SDR</b>\n\n"
    "Я — твой автоматический менеджер по продажам. Я нахожу потенциальных "
    "клиентов в Telegram-группах, анализирую их и пишу персональные сообщения "
    "от твоего имени.\n\n"
    "Чтобы я писал <b>точные и релевантные</b> предложения, мне нужно узнать "
    "о твоём бизнесе. Нажми <b>«🎯 Настроить ICP»</b> и ответь на вопросы.\n\n"
    "Не знаешь с чего начать? Жми <b>«❓ Как пользоваться агентом?»</b>"
)

GUIDE = (
    "📖 <b>Как пользоваться агентом — за 1 минуту</b>\n\n"
    "<b>Что это?</b>\n"
    "DacherForge сам ищет клиентов в Telegram-группах и пишет им первым, "
    "предлагая твой продукт. Ты получаешь готовые тёплые диалоги.\n\n"
    "<b>Шаг 1 — Настрой ICP</b> 🎯\n"
    "Расскажи о своей компании и продукте. Это нужно один раз. На основе "
    "этих ответов агент строит персональные предложения под каждого лида.\n\n"
    "<b>Шаг 2 — Добавь группы</b> 👥\n"
    "Укажи Telegram-группы, где сидит твоя аудитория. Или подключи "
    "авто-поиск — система сама найдёт нужные группы.\n\n"
    "<b>Шаг 3 — Запусти</b> ▶️\n"
    "Агент заходит в группы, читает сообщения, находит подходящих людей "
    "(оценка 0–100 по твоему ICP) и пишет тем, кто реально может купить.\n\n"
    "<b>Шаг 4 — Получай лидов</b> 📈\n"
    "Все диалоги и ответы видны в разделе «Лиды». В «Статистике» — "
    "сколько написано, сколько ответили, какие подходы работают лучше.\n\n"
    "<b>🧠 Что важно:</b>\n"
    "Агент <u>самообучается</u>. Он пробует 5 разных стратегий общения и со "
    "временем чаще использует те, что приносят больше ответов и встреч "
    "именно в твоей нише.\n\n"
    "<b>Безопасность:</b> агент пишет максимум 40 сообщений в день "
    "(9:00–21:00), чтобы аккаунт выглядел естественно.\n\n"
    "Готов? Жми <b>«🎯 Настроить ICP»</b> 🚀"
)


# =============================================================================
# /start и главное меню
# =============================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        WELCOME, parse_mode=ParseMode.HTML, reply_markup=main_menu_kb()
    )


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        WELCOME, parse_mode=ParseMode.HTML, reply_markup=main_menu_kb()
    )


async def show_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        GUIDE, parse_mode=ParseMode.HTML, reply_markup=back_kb()
    )


# =============================================================================
# ICP АНКЕТА (ConversationHandler)
# =============================================================================
async def icp_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["icp"] = {}
    context.user_data["q_index"] = 0
    intro = (
        "🎯 <b>Настройка ICP</b> (Ideal Customer Profile)\n\n"
        "Сейчас задам 12 коротких вопросов о твоём бизнесе. Чем точнее "
        "ответишь — тем релевантнее будут сообщения лидам.\n\n"
        "Можно ответить <code>-</code> чтобы пропустить вопрос.\n"
        "Команда /cancel — выйти из анкеты.\n"
    )
    await q.edit_message_text(intro, parse_mode=ParseMode.HTML)
    await _ask_question(update, context, first=True)
    return ICP_QUESTIONS[0][0]


async def _ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE, first=False):
    idx = context.user_data["q_index"]
    _, _, text, hint = ICP_QUESTIONS[idx]
    body = f"{text}\n\n<i>{hint}</i>"
    chat = update.effective_chat
    await context.bot.send_message(chat.id, body, parse_mode=ParseMode.HTML)


async def icp_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data.get("q_index", 0)
    state, key, _, _ = ICP_QUESTIONS[idx]
    answer = (update.message.text or "").strip()

    if answer and answer != "-":
        # keywords и negative_keywords храним как списки
        if key in ("icp_keywords", "icp_negative_keywords"):
            context.user_data["icp"][key] = [
                w.strip().lower() for w in answer.split(",") if w.strip()
            ]
        else:
            context.user_data["icp"][key] = answer

    # следующий вопрос
    next_idx = idx + 1
    if next_idx >= len(ICP_QUESTIONS):
        return await icp_review(update, context)

    context.user_data["q_index"] = next_idx
    await _ask_question(update, context)
    return ICP_QUESTIONS[next_idx][0]


async def icp_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    icp = context.user_data.get("icp", {})

    def g(key, default="—"):
        v = icp.get(key, default)
        if isinstance(v, list):
            return ", ".join(v) if v else default
        return v or default

    summary = (
        "✅ <b>Проверь, всё ли верно:</b>\n\n"
        f"🏢 <b>Компания:</b> {g('company_name')}\n"
        f"💼 <b>Ниша:</b> {g('company_description')}\n"
        f"📦 <b>Продукт:</b> {g('product')}\n"
        f"🎯 <b>Целевой клиент:</b> {g('target_audience')}\n"
        f"🔥 <b>Боли клиента:</b> {g('pain_points')}\n"
        f"⭐ <b>Преимущество:</b> {g('value_proposition')}\n"
        f"📍 <b>Гео:</b> {g('geo')}\n"
        f"💰 <b>Чек:</b> {g('price_range')}\n"
        f"🤝 <b>Целевое действие:</b> {g('cta')}\n"
        f"🔑 <b>Ключевые фразы:</b> {g('icp_keywords')}\n"
        f"🚫 <b>Стоп-слова:</b> {g('icp_negative_keywords')}\n"
        f"🎨 <b>Тон:</b> {g('tone')}\n"
    )
    await context.bot.send_message(
        update.effective_chat.id, summary,
        parse_mode=ParseMode.HTML, reply_markup=icp_review_kb()
    )
    return ConversationHandler.END


async def icp_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("Сохраняю...")
    icp = context.user_data.get("icp", {})
    chat_id = update.effective_chat.id

    # icp_description собираем из ниши + аудитории для userbot
    icp_description = " / ".join(filter(None, [
        icp.get("company_description", ""),
        icp.get("target_audience", ""),
    ])) or "—"

    fields = {
        "company_name": icp.get("company_name", ""),
        "company_description": icp.get("company_description", ""),
        "product": icp.get("product", ""),
        "target_audience": icp.get("target_audience", ""),
        "pain_points": icp.get("pain_points", ""),
        "value_proposition": icp.get("value_proposition", ""),
        "geo": icp.get("geo", ""),
        "price_range": icp.get("price_range", ""),
        "cta": icp.get("cta", "15-минутный созвон"),
        "icp_keywords": icp.get("icp_keywords", []),
        "icp_negative_keywords": icp.get("icp_negative_keywords", []),
        "tone": icp.get("tone", "дружелюбный"),
        "icp_description": icp_description,
        "status": "active",
    }
    upsert_campaign(chat_id, fields)

    await q.edit_message_text(
        "🎉 <b>ICP сохранён!</b>\n\n"
        "Теперь агент знает твой бизнес и будет писать персональные "
        "предложения подходящим лидам.\n\n"
        "Дальше: добавь группы в разделе «👥 Мои группы» — и запускай! 🚀",
        parse_mode=ParseMode.HTML, reply_markup=back_kb()
    )


async def icp_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Анкета отменена.", reply_markup=ReplyKeyboardRemove()
    )
    await update.message.reply_text("Главное меню:", reply_markup=main_menu_kb())
    return ConversationHandler.END


# =============================================================================
# СТАТИСТИКА
# =============================================================================
def _db_query(query: str, params: tuple = ()):
    if not os.path.exists(DB_FILE):
        return None
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        logger.error("_db_query: %s", e)
        return None


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = campaign_id_for(update.effective_chat.id)

    leads = _db_query(
        "SELECT "
        "COUNT(*), "
        "SUM(CASE WHEN status='contacted' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN status='replied' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN status='meeting' THEN 1 ELSE 0 END) "
        "FROM leads WHERE campaign_id=?", (cid,)
    )

    if leads is None:
        text = "📊 <b>Статистика</b>\n\nБаза данных ещё пуста. Агент пока не нашёл лидов."
    else:
        total, contacted, replied, meeting = (leads[0] if leads else (0, 0, 0, 0))
        total = total or 0
        contacted = contacted or 0
        replied = replied or 0
        meeting = meeting or 0
        reply_rate = round(replied / contacted * 100, 1) if contacted else 0
        text = (
            "📊 <b>Статистика кампании</b>\n\n"
            f"👀 Найдено лидов: <b>{total}</b>\n"
            f"✉️ Написано сообщений: <b>{contacted}</b>\n"
            f"💬 Ответили: <b>{replied}</b> ({reply_rate}%)\n"
            f"🤝 Встречи: <b>{meeting}</b>\n"
        )

    await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_kb())


async def show_strategies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = campaign_id_for(update.effective_chat.id)

    rows = _db_query(
        "SELECT strategy_id, total_sent, total_replies, "
        "ROUND(CAST(total_replies AS FLOAT)/NULLIF(total_sent,0)*100,1) "
        "FROM strategy_performance WHERE campaign_id=? "
        "ORDER BY 4 DESC", (cid,)
    )

    if not rows:
        text = (
            "🧠 <b>Стратегии общения</b>\n\n"
            "Агент использует 5 подходов и сам выбирает лучший:\n\n"
            "• <b>Прямое предложение</b>\n"
            "• <b>От проблемы</b>\n"
            "• <b>Социальное доказательство</b>\n"
            "• <b>Интрига</b>\n"
            "• <b>Комплимент + оффер</b>\n\n"
            "Пока нет данных — статистика появится после первых отправок. "
            "Система автоматически чаще выбирает то, что приносит ответы (80%), "
            "и тестирует остальное (20%)."
        )
    else:
        lines = ["🧠 <b>Эффективность стратегий</b>\n"]
        for sid, sent, replies, rr in rows:
            lines.append(f"• <b>{sid}</b>: {sent} отпр. → {replies} отв. ({rr or 0}%)")
        text = "\n".join(lines)

    await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_kb())


async def show_leads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = campaign_id_for(update.effective_chat.id)

    rows = _db_query(
        "SELECT full_name, username, icp_score, status "
        "FROM leads WHERE campaign_id=? ORDER BY created_at DESC LIMIT 10", (cid,)
    )

    if not rows:
        text = "📈 <b>Лиды</b>\n\nПока нет найденных лидов. Агент ищет 🔍"
    else:
        status_emoji = {
            "contacted": "✉️", "replied": "💬", "meeting": "🤝",
            "deal": "💰", "new": "🆕", "pending": "⏳",
        }
        lines = ["📈 <b>Последние лиды</b>\n"]
        for name, username, score, status in rows:
            em = status_emoji.get(status, "•")
            handle = f"@{username}" if username else (name or "—")
            lines.append(f"{em} {handle} — score <b>{score}</b>")
        text = "\n".join(lines)

    await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_kb())


# =============================================================================
# ГРУППЫ
# =============================================================================
async def show_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    camp = get_campaign(update.effective_chat.id)
    groups = camp.get("groups", []) if camp else []

    if groups:
        lst = "\n".join(f"• {g}" for g in groups[:20])
        text = (
            f"👥 <b>Твои группы ({len(groups)})</b>\n\n{lst}\n\n"
            "Чтобы добавить ещё — отправь команду:\n"
            "<code>/addgroup ссылка</code>\n"
            "Например: <code>/addgroup https://t.me/example</code>"
        )
    else:
        text = (
            "👥 <b>Группы не добавлены</b>\n\n"
            "Добавь группу командой:\n"
            "<code>/addgroup ссылка</code>\n\n"
            "Примеры:\n"
            "<code>/addgroup https://t.me/example</code>\n"
            "<code>/addgroup @example</code>"
        )

    await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_kb())


async def add_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Укажи ссылку: <code>/addgroup https://t.me/example</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    link = context.args[0].strip()
    chat_id = update.effective_chat.id
    camp = get_campaign(chat_id) or {}
    groups = camp.get("groups", [])
    if link in groups:
        await update.message.reply_text("Эта группа уже добавлена.")
        return
    groups.append(link)
    upsert_campaign(chat_id, {"groups": groups})
    await update.message.reply_text(
        f"✅ Группа добавлена: {link}\n\nАгент зайдёт в неё в течение 5 минут.",
        reply_markup=main_menu_kb(),
    )


# =============================================================================
# ВКЛ/ВЫКЛ
# =============================================================================
async def toggle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    chat_id = update.effective_chat.id
    camp = get_campaign(chat_id)
    if not camp:
        await q.answer("Сначала настрой ICP!", show_alert=True)
        return
    new_status = "paused" if camp.get("status") == "active" else "active"
    upsert_campaign(chat_id, {"status": new_status})
    await q.answer()
    label = "▶️ Запущена" if new_status == "active" else "⏸ На паузе"
    await q.edit_message_text(
        f"Кампания: <b>{label}</b>",
        parse_mode=ParseMode.HTML, reply_markup=back_kb()
    )


# =============================================================================
# MAIN
# =============================================================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # ICP анкета
    icp_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(icp_start, pattern="^icp_start$")],
        states={
            state: [MessageHandler(filters.TEXT & ~filters.COMMAND, icp_answer)]
            for state, _, _, _ in ICP_QUESTIONS
        },
        fallbacks=[CommandHandler("cancel", icp_cancel)],
        per_message=False,
    )
    app.add_handler(icp_conv)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addgroup", add_group))

    app.add_handler(CallbackQueryHandler(show_menu, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(show_guide, pattern="^guide$"))
    app.add_handler(CallbackQueryHandler(show_stats, pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(show_strategies, pattern="^strategies$"))
    app.add_handler(CallbackQueryHandler(show_leads, pattern="^leads$"))
    app.add_handler(CallbackQueryHandler(show_groups, pattern="^groups$"))
    app.add_handler(CallbackQueryHandler(icp_save, pattern="^icp_save$"))
    app.add_handler(CallbackQueryHandler(toggle_status, pattern="^toggle$"))

    logger.info("Control bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
