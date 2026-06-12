import asyncio
import json
import logging
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import Channel, Chat
from telethon.errors import UserAlreadyParticipantError, FloodWaitError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/root/outreach/userbot.log')
    ]
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIG
# =============================================================================
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
BOT_USERNAME = "@CowDacherRonaldoBot"
SHARED_SECRET = "dK9mX2vL8nP4qR7wT1uY5cF3hJ6bN0eA_Ronaldu+Danya+CR7+Gol"
SESSION_NAME = "/root/outreach/userbot_session"
DB_FILE = "/root/outreach/sdr.db"
CAMPAIGNS_FILE = "/root/outreach/campaigns.json"
SEND_QUEUE_FILE = "/root/outreach/send_queue.json"

MAX_PER_HOUR = 15
MAX_PER_DAY = 40
WORK_HOUR_START = 9
WORK_HOUR_END = 21

# =============================================================================
# DATABASE
# =============================================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Campaigns with ICP
    c.execute('''CREATE TABLE IF NOT EXISTS campaigns (
        id TEXT PRIMARY KEY,
        name TEXT,
        status TEXT DEFAULT 'active',
        product_name TEXT,
        product_description TEXT,
        icp_description TEXT,
        icp_keywords TEXT,
        icp_negative_keywords TEXT,
        geo TEXT,
        cta TEXT DEFAULT 'встреча 15 минут',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # Groups discovered via SERP
    c.execute('''CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id TEXT,
        group_link TEXT UNIQUE,
        group_id INTEGER,
        group_title TEXT,
        status TEXT DEFAULT 'pending',
        joined_at TIMESTAMP,
        FOREIGN KEY(campaign_id) REFERENCES campaigns(id)
    )''')

    # Every lead analyzed
    c.execute('''CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id TEXT,
        user_id TEXT,
        username TEXT,
        full_name TEXT,
        group_id INTEGER,
        group_title TEXT,
        icp_score INTEGER DEFAULT 0,
        icp_match_reason TEXT,
        context_messages TEXT,
        status TEXT DEFAULT 'new',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, campaign_id)
    )''')

    # All outbound messages
    c.execute('''CREATE TABLE IF NOT EXISTS outbound_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        campaign_id TEXT,
        strategy_id TEXT,
        message_text TEXT,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(lead_id) REFERENCES leads(id)
    )''')

    # All conversation history (inbound + outbound)
    c.execute('''CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        direction TEXT,
        message_text TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(lead_id) REFERENCES leads(id)
    )''')

    # Outcomes for self-learning
    c.execute('''CREATE TABLE IF NOT EXISTS outcomes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        campaign_id TEXT,
        strategy_id TEXT,
        outcome_type TEXT,
        reward INTEGER DEFAULT 0,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(lead_id) REFERENCES leads(id)
    )''')

    # Strategy performance per segment
    c.execute('''CREATE TABLE IF NOT EXISTS strategy_performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        strategy_id TEXT,
        campaign_id TEXT,
        total_sent INTEGER DEFAULT 0,
        total_replies INTEGER DEFAULT 0,
        total_meetings INTEGER DEFAULT 0,
        total_reward INTEGER DEFAULT 0,
        UNIQUE(strategy_id, campaign_id)
    )''')

    conn.commit()
    conn.close()
    logger.info("Database initialized: %s", DB_FILE)


# =============================================================================
# STRATEGIES
# =============================================================================
STRATEGIES = {
    "direct_value": {
        "id": "direct_value",
        "name": "Direct Value",
        "build_message": lambda name, product, cta, context: (
            f"Привет {name}! Вижу ты занимаешься {context}. "
            f"Мы помогаем именно таким бизнесам через {product}. "
            f"Открыт на {cta}?"
        ),
    },
    "problem_first": {
        "id": "problem_first",
        "name": "Problem First",
        "build_message": lambda name, product, cta, context: (
            f"Привет {name}! Часто вижу что бизнесы вроде твоего теряют клиентов из-за отсутствия {product}. "
            f"Готов показать как исправить — займёт всего {cta}?"
        ),
    },
    "social_proof": {
        "id": "social_proof",
        "name": "Social Proof",
        "build_message": lambda name, product, cta, context: (
            f"Привет {name}! Недавно помогли похожему бизнесу через {product} — результат за месяц. "
            f"Могу рассказать подробнее, если интересно ({cta})?"
        ),
    },
    "curiosity": {
        "id": "curiosity",
        "name": "Curiosity",
        "build_message": lambda name, product, cta, context: (
            f"Привет {name}! У меня есть идея конкретно для твоего бизнеса по поводу {product}. "
            f"Можем созвониться на {cta}?"
        ),
    },
    "compliment": {
        "id": "compliment",
        "name": "Compliment + Offer",
        "build_message": lambda name, product, cta, context: (
            f"Привет {name}! Увидел твои сообщения — чувствуется что ты серьёзно подходишь к делу. "
            f"Как раз работаю с такими через {product}. Интересно обсудить ({cta})?"
        ),
    },
}

REWARD_MAP = {
    "no_reply": 0,
    "reply": 1,
    "conversation": 3,
    "meeting": 10,
    "proposal": 20,
    "deal": 50,
}


# =============================================================================
# ICP ANALYZER
# Scores how well a person matches the Ideal Customer Profile
# =============================================================================
class ICPAnalyzer:
    def score(self, messages: list[str], campaign: dict) -> tuple[int, str]:
        """
        Returns (score 0-100, reason string).
        score >= 40 → send DM
        """
        if not messages:
            return 0, "no messages to analyze"

        icp_kw = [k.lower() for k in campaign.get("icp_keywords", [])]
        neg_kw = [k.lower() for k in campaign.get("icp_negative_keywords", [])]
        combined = " ".join(messages).lower()

        # Hard veto — negative keywords
        for kw in neg_kw:
            if kw in combined:
                return 0, f"negative keyword: {kw}"

        # Score positive keywords
        matched = [kw for kw in icp_kw if kw in combined]
        if not matched:
            return 10, "no icp keywords matched"

        score = min(100, 30 + len(matched) * 15)

        # Geo signal
        geo = campaign.get("geo", "").lower()
        if geo and geo in combined:
            score = min(100, score + 20)

        reason = f"matched: {', '.join(matched[:5])}"
        if geo and geo in combined:
            reason += f"; geo: {geo}"

        return score, reason


# =============================================================================
# STRATEGY ENGINE (Multi-Armed Bandit 80/20)
# =============================================================================
class StrategyEngine:
    EXPLORATION_RATE = 0.20

    def pick(self, campaign_id: str) -> dict:
        if random.random() < self.EXPLORATION_RATE:
            choice = random.choice(list(STRATEGIES.keys()))
            logger.info("Explore → %s", choice)
            return STRATEGIES[choice]

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            SELECT strategy_id,
                   CAST(total_replies AS FLOAT) / NULLIF(total_sent, 0) AS reply_rate
            FROM strategy_performance
            WHERE campaign_id = ?
            ORDER BY reply_rate DESC
            LIMIT 1
        ''', (campaign_id,))
        row = c.fetchone()
        conn.close()

        if row:
            logger.info("Exploit → %s (reply_rate=%.2f)", row[0], row[1] or 0)
            return STRATEGIES.get(row[0], random.choice(list(STRATEGIES.values())))

        return random.choice(list(STRATEGIES.values()))

    def record_sent(self, strategy_id: str, campaign_id: str):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            INSERT INTO strategy_performance (strategy_id, campaign_id, total_sent)
            VALUES (?, ?, 1)
            ON CONFLICT(strategy_id, campaign_id)
            DO UPDATE SET total_sent = total_sent + 1
        ''', (strategy_id, campaign_id))
        conn.commit()
        conn.close()

    def record_reply(self, strategy_id: str, campaign_id: str):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            UPDATE strategy_performance
            SET total_replies = total_replies + 1
            WHERE strategy_id = ? AND campaign_id = ?
        ''', (strategy_id, campaign_id))
        conn.commit()
        conn.close()


# =============================================================================
# CONVERSATION MANAGER
# =============================================================================
class ConversationManager:
    def store_outbound(self, lead_id: int, text: str):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            'INSERT INTO conversations (lead_id, direction, message_text) VALUES (?,?,?)',
            (lead_id, 'out', text)
        )
        conn.commit()
        conn.close()

    def store_inbound(self, lead_id: int, text: str):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            'INSERT INTO conversations (lead_id, direction, message_text) VALUES (?,?,?)',
            (lead_id, 'in', text)
        )
        conn.commit()
        conn.close()

    def get_history(self, lead_id: int, limit: int = 20) -> list[dict]:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            SELECT direction, message_text, timestamp
            FROM conversations
            WHERE lead_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (lead_id, limit))
        rows = c.fetchall()
        conn.close()
        return [{"dir": r[0], "text": r[1], "ts": r[2]} for r in reversed(rows)]

    def get_lead_id_by_user(self, user_id: str) -> int | None:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id FROM leads WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', (user_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None


# =============================================================================
# GROUP RESOLVER
# =============================================================================
def normalize_group_link(link: str):
    if not link:
        return None
    link = link.strip()
    if link.startswith("@"):
        name = link[1:]
        return ("username", name) if re.fullmatch(r"[A-Za-z0-9_]{4,}", name) else None
    m = re.match(r"^https?://", link)
    rest = link[m.end():] if m else link
    if not (rest.startswith("t.me/") or rest.startswith("telegram.me/")):
        if re.fullmatch(r"[A-Za-z0-9_]{4,}", rest):
            return ("username", rest)
        return None
    path = rest.split("/", 1)[1] if "/" in rest else ""
    path = path.split("?", 1)[0].split("#", 1)[0].strip("/")
    if not path:
        return None
    parts = path.split("/")
    first = parts[0]
    if first.startswith("+"):
        return ("invite", first[1:])
    if first == "joinchat" and len(parts) > 1:
        return ("invite", parts[1])
    if first == "s" and len(parts) > 1:
        first = parts[1]
    return ("username", first) if re.fullmatch(r"[A-Za-z0-9_]{4,}", first) else None


def is_real_group(entity) -> bool:
    if isinstance(entity, Chat):
        return True
    if isinstance(entity, Channel):
        return bool(getattr(entity, "megagroup", False))
    return False


# =============================================================================
# GLOBALS
# =============================================================================
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
icp_analyzer = ICPAnalyzer()
strategy_engine = StrategyEngine()
conv_manager = ConversationManager()

sent_today = 0
sent_hour = 0
last_reset_day = datetime.now().day
last_reset_hour = datetime.now().hour

# group_id → campaign_id mapping
ACTIVE_GROUPS: dict[int, str] = {}


# =============================================================================
# CAMPAIGN LOADER
# =============================================================================
def load_campaigns() -> dict:
    if not os.path.exists(CAMPAIGNS_FILE):
        return {}
    with open(CAMPAIGNS_FILE) as f:
        return json.load(f)


def save_campaigns(data: dict):
    with open(CAMPAIGNS_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =============================================================================
# JOIN GROUP
# =============================================================================
async def join_group(link: str, campaign_id: str) -> int | None:
    parsed = normalize_group_link(link)
    if not parsed:
        logger.warning("Invalid group link: %s", link)
        return None

    kind, value = parsed
    try:
        if kind == "invite":
            try:
                updates = await client(ImportChatInviteRequest(value))
                entity = updates.chats[0]
            except UserAlreadyParticipantError:
                entity = await client.get_entity(value)
        else:
            entity = await client.get_entity(value)
            try:
                await client(JoinChannelRequest(entity))
            except Exception as e:
                logger.info("Join %s: %s", link, e)
    except FloodWaitError as e:
        logger.warning("FloodWait %ds", e.seconds)
        await asyncio.sleep(e.seconds)
        return None
    except Exception as e:
        logger.error("Error joining %s: %s", link, e)
        return None

    if not is_real_group(entity):
        logger.info("Skipping channel (not group): %s", link)
        return None

    ACTIVE_GROUPS[entity.id] = campaign_id
    logger.info("Joined group: %s id=%d", entity.title, entity.id)
    return entity.id


async def join_groups_loop():
    while True:
        try:
            campaigns = load_campaigns()
            for cid, camp in campaigns.items():
                if camp.get("status") != "active":
                    continue
                for link in camp.get("groups", []):
                    if not any(True for gid, gcid in ACTIVE_GROUPS.items() if gcid == cid):
                        await join_group(link, cid)
                        await asyncio.sleep(random.uniform(10, 20))
        except Exception as e:
            logger.error("join_groups_loop error: %s", e)
        await asyncio.sleep(300)


# =============================================================================
# ANALYZE + SEND
# =============================================================================
async def get_user_recent_messages(group_entity, user_id: int, limit: int = 10) -> list[str]:
    messages = []
    try:
        async for msg in client.iter_messages(group_entity, from_user=user_id, limit=limit):
            if msg.text:
                messages.append(msg.text[:500])
    except Exception as e:
        logger.warning("Error reading messages: %s", e)
    return messages


async def process_potential_lead(event, campaign_id: str, campaign: dict):
    global sent_today, sent_hour

    sender = await event.get_sender()
    if not sender or sender.bot:
        return

    group = await event.get_chat()
    user_id = str(sender.id)
    username = sender.username or ""
    full_name = ((sender.first_name or "") + " " + (sender.last_name or "")).strip()

    # Check if already contacted in this campaign
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, status FROM leads WHERE user_id = ? AND campaign_id = ?', (user_id, campaign_id))
    existing = c.fetchone()
    conn.close()

    if existing and existing[1] in ("contacted", "replied", "meeting", "deal"):
        return

    # Collect recent messages for ICP analysis
    context_msgs = await get_user_recent_messages(group, sender.id, limit=10)
    context_msgs.append(event.message.text or "")

    # ICP score
    score, reason = icp_analyzer.score(context_msgs, campaign)
    logger.info("ICP score for %s: %d (%s)", full_name or user_id, score, reason)

    if score < 40:
        return

    # Save/update lead
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO leads
        (campaign_id, user_id, username, full_name, group_id, group_title, icp_score, icp_match_reason, context_messages, status)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id, campaign_id) DO UPDATE SET
            icp_score=excluded.icp_score,
            icp_match_reason=excluded.icp_match_reason,
            context_messages=excluded.context_messages
    ''', (
        campaign_id, user_id, username, full_name,
        group.id, group.title,
        score, reason,
        json.dumps(context_msgs[:5], ensure_ascii=False),
        "pending"
    ))
    lead_id = c.lastrowid or existing[0] if existing else c.lastrowid
    conn.commit()

    # Re-fetch lead_id if needed
    c.execute('SELECT id FROM leads WHERE user_id = ? AND campaign_id = ?', (user_id, campaign_id))
    lead_row = c.fetchone()
    lead_id = lead_row[0] if lead_row else lead_id
    conn.close()

    # Pick strategy and build message
    strategy = strategy_engine.pick(campaign_id)

    product = campaign.get("product", "нашим решением")
    cta = campaign.get("cta", "встреча 15 минут")
    name = full_name.split()[0] if full_name else "привет"

    # Build context summary for message
    context_hint = campaign.get("icp_description", "бизнесом")
    if context_msgs:
        last = context_msgs[-1][:80]
        context_hint = last if last else context_hint

    message_text = strategy["build_message"](name, product, cta, context_hint)

    # Send DM
    try:
        target = sender.username or sender.id
        await client.send_message(target, message_text)

        # Store in DB
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute(
            'INSERT INTO outbound_messages (lead_id, campaign_id, strategy_id, message_text) VALUES (?,?,?,?)',
            (lead_id, campaign_id, strategy["id"], message_text)
        )
        c.execute('UPDATE leads SET status = ? WHERE id = ?', ("contacted", lead_id))
        conn.commit()
        conn.close()

        conv_manager.store_outbound(lead_id, message_text)
        strategy_engine.record_sent(strategy["id"], campaign_id)

        sent_today += 1
        sent_hour += 1

        logger.info("DM sent → %s | strategy=%s | score=%d", full_name or user_id, strategy["id"], score)

        # Notify owner bot
        await notify_bot(campaign_id, full_name, username, score, reason, message_text)

        await asyncio.sleep(random.uniform(90, 180))

    except FloodWaitError as e:
        logger.warning("FloodWait %ds — pausing", e.seconds)
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logger.error("DM error to %s: %s", user_id, e)


async def notify_bot(campaign_id, name, username, score, reason, message):
    """Notify the control bot when a lead is found and messaged."""
    text = json.dumps({
        "event": "lead_contacted",
        "campaign_id": campaign_id,
        "name": name,
        "username": username,
        "icp_score": score,
        "reason": reason,
        "message_sent": message[:200],
        "secret": SHARED_SECRET
    }, ensure_ascii=False)
    try:
        await client.send_message(BOT_USERNAME, "LEAD_EVENT::" + text[:4000])
    except Exception as e:
        logger.error("notify_bot error: %s", e)


# =============================================================================
# MAIN MESSAGE HANDLER
# =============================================================================
@client.on(events.NewMessage())
async def handle_message(event):
    global sent_today, sent_hour, last_reset_day, last_reset_hour

    # Rate limit reset
    now = datetime.now()
    if now.day != last_reset_day:
        sent_today = 0
        last_reset_day = now.day
    if now.hour != last_reset_hour:
        sent_hour = 0
        last_reset_hour = now.hour

    # -----------------------------------------------------------------------
    # Handle commands from control bot
    # -----------------------------------------------------------------------
    if event.message.out:
        return

    # Commands sent TO us from the main bot
    if event.is_private:
        sender = await event.get_sender()
        text = event.message.text or ""

        # New groups from SERP (Make.com sends this)
        if text.startswith("ADD_GROUPS::"):
            await handle_add_groups(text[12:])
            return

        # Outcome tracking (Make.com sends when reply/meeting happens)
        if text.startswith("OUTCOME::"):
            await handle_outcome(text[9:])
            return

        # Campaign update
        if text.startswith("UPDATE_CAMPAIGN::"):
            await handle_campaign_update(text[17:])
            return

        # Track replies from leads
        if sender and not sender.bot:
            user_id = str(sender.id)
            lead_id = conv_manager.get_lead_id_by_user(user_id)
            if lead_id:
                conv_manager.store_inbound(lead_id, text)
                await handle_reply(lead_id, user_id, text)
        return

    # -----------------------------------------------------------------------
    # Group message monitoring
    # -----------------------------------------------------------------------
    if not event.is_group:
        return

    if not event.message.from_id:
        return

    group = await event.get_chat()
    campaign_id = ACTIVE_GROUPS.get(group.id)
    if not campaign_id:
        return

    # Work hours check
    if now.hour < WORK_HOUR_START or now.hour >= WORK_HOUR_END:
        return

    # Rate limit check
    if sent_today >= MAX_PER_DAY or sent_hour >= MAX_PER_HOUR:
        return

    text = event.message.text or ""
    if not text or len(text) < 10:
        return

    campaigns = load_campaigns()
    campaign = campaigns.get(campaign_id)
    if not campaign or campaign.get("status") != "active":
        return

    # Quick keyword pre-filter before heavy analysis
    icp_kw = [k.lower() for k in campaign.get("icp_keywords", [])]
    if icp_kw and not any(kw in text.lower() for kw in icp_kw):
        return

    await process_potential_lead(event, campaign_id, campaign)


# =============================================================================
# COMMAND HANDLERS (from Make.com via bot)
# =============================================================================
async def handle_add_groups(payload_str: str):
    """
    Make.com sends: ADD_GROUPS::{"campaign_id": "...", "groups": ["link1", ...]}
    """
    try:
        payload = json.loads(payload_str)
        campaign_id = payload["campaign_id"]
        new_groups = payload["groups"]

        campaigns = load_campaigns()
        if campaign_id not in campaigns:
            logger.warning("Unknown campaign: %s", campaign_id)
            return

        existing = campaigns[campaign_id].get("groups", [])
        added = 0
        for link in new_groups:
            if link not in existing:
                existing.append(link)
                added += 1
                await join_group(link, campaign_id)
                await asyncio.sleep(random.uniform(5, 15))

        campaigns[campaign_id]["groups"] = existing
        save_campaigns(campaigns)
        logger.info("Added %d groups to campaign %s", added, campaign_id)

    except Exception as e:
        logger.error("handle_add_groups error: %s", e)


async def handle_outcome(payload_str: str):
    """
    Make.com sends: OUTCOME::{"user_id": "...", "outcome": "reply|meeting|deal", "campaign_id": "..."}
    """
    try:
        payload = json.loads(payload_str)
        user_id = payload["user_id"]
        outcome = payload["outcome"]
        campaign_id = payload.get("campaign_id", "")
        reward = REWARD_MAP.get(outcome, 0)

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT id FROM leads WHERE user_id = ? AND campaign_id = ?', (user_id, campaign_id))
        row = c.fetchone()
        if row:
            lead_id = row[0]
            c.execute(
                'INSERT INTO outcomes (lead_id, campaign_id, outcome_type, reward) VALUES (?,?,?,?)',
                (lead_id, campaign_id, outcome, reward)
            )
            c.execute('UPDATE leads SET status = ? WHERE id = ?', (outcome, lead_id))

            # Update strategy performance
            c.execute('SELECT strategy_id FROM outbound_messages WHERE lead_id = ? LIMIT 1', (lead_id,))
            strat_row = c.fetchone()
            if strat_row:
                strategy_id = strat_row[0]
                c.execute('''
                    UPDATE strategy_performance
                    SET total_reward = total_reward + ?,
                        total_replies = total_replies + CASE WHEN ? = 'reply' THEN 1 ELSE 0 END,
                        total_meetings = total_meetings + CASE WHEN ? = 'meeting' THEN 1 ELSE 0 END
                    WHERE strategy_id = ? AND campaign_id = ?
                ''', (reward, outcome, outcome, strategy_id, campaign_id))

        conn.commit()
        conn.close()
        logger.info("Outcome recorded: %s → %s (reward=%d)", user_id, outcome, reward)

    except Exception as e:
        logger.error("handle_outcome error: %s", e)


async def handle_campaign_update(payload_str: str):
    """
    Make.com sends: UPDATE_CAMPAIGN::{"id": "...", "product": "...", "icp_keywords": [...], ...}
    Updates or creates a campaign config.
    """
    try:
        payload = json.loads(payload_str)
        campaign_id = payload["id"]
        campaigns = load_campaigns()
        if campaign_id not in campaigns:
            campaigns[campaign_id] = {"id": campaign_id, "status": "active", "groups": []}
        campaigns[campaign_id].update(payload)
        save_campaigns(campaigns)
        logger.info("Campaign updated: %s", campaign_id)
    except Exception as e:
        logger.error("handle_campaign_update error: %s", e)


async def handle_reply(lead_id: int, user_id: str, text: str):
    """When a lead replies to our DM — record it and update strategy."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT campaign_id FROM leads WHERE id = ?', (lead_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return
    campaign_id = row[0]

    # Get which strategy was used
    c.execute('SELECT strategy_id FROM outbound_messages WHERE lead_id = ? ORDER BY sent_at DESC LIMIT 1', (lead_id,))
    strat_row = c.fetchone()
    conn.close()

    if strat_row:
        strategy_engine.record_reply(strat_row[0], campaign_id)

    # Record outcome
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        'INSERT INTO outcomes (lead_id, campaign_id, outcome_type, reward) VALUES (?,?,?,?)',
        (lead_id, campaign_id, "reply", REWARD_MAP["reply"])
    )
    c.execute('UPDATE leads SET status = ? WHERE id = ?', ("replied", lead_id))
    conn.commit()
    conn.close()

    logger.info("Reply received from lead_id=%d: %s", lead_id, text[:100])


# =============================================================================
# SEND QUEUE (manual DMs added externally)
# =============================================================================
async def process_send_queue():
    while True:
        try:
            if os.path.exists(SEND_QUEUE_FILE):
                with open(SEND_QUEUE_FILE) as f:
                    queue = json.load(f)
                for key, item in list(queue.items()):
                    if item.get("status") == "pending":
                        try:
                            target = item.get("username") or int(item.get("user_id"))
                            await client.send_message(target, item["text"])
                            queue[key]["status"] = "sent"
                            logger.info("Queue DM sent to %s", target)
                            await asyncio.sleep(random.uniform(60, 120))
                        except Exception as e:
                            queue[key]["status"] = "error"
                            logger.error("Queue send error: %s", e)
                with open(SEND_QUEUE_FILE, "w") as f:
                    json.dump(queue, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Queue loop error: %s", e)
        await asyncio.sleep(15)


# =============================================================================
# DAILY REPORT
# =============================================================================
async def daily_report_loop():
    while True:
        now = datetime.now()
        if now.hour == 22 and now.minute < 5:
            try:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                yesterday = (now - timedelta(days=1)).date()

                c.execute('''
                    SELECT COUNT(*) FROM leads
                    WHERE DATE(created_at) = ? AND status = 'contacted'
                ''', (yesterday,))
                contacted = c.fetchone()[0]

                c.execute('''
                    SELECT COUNT(*) FROM outcomes
                    WHERE DATE(recorded_at) = ? AND outcome_type = 'reply'
                ''', (yesterday,))
                replies = c.fetchone()[0]

                c.execute('''
                    SELECT strategy_id, total_sent, total_replies,
                           ROUND(CAST(total_replies AS FLOAT)/NULLIF(total_sent,0)*100,1) as rr
                    FROM strategy_performance
                    ORDER BY rr DESC LIMIT 3
                ''')
                top = c.fetchall()
                conn.close()

                report = (
                    f"DAILY_REPORT::{json.dumps({'date': str(yesterday), 'contacted': contacted, 'replies': replies, 'top_strategies': top}, ensure_ascii=False)}"
                )
                await client.send_message(BOT_USERNAME, report)
                logger.info("Daily report sent")
            except Exception as e:
                logger.error("Daily report error: %s", e)

            await asyncio.sleep(600)
        else:
            await asyncio.sleep(60)


# =============================================================================
# MAIN
# =============================================================================
async def main():
    init_db()
    await client.start()
    logger.info("Userbot started!")
    logger.info("Groups to watch: %d", len(ACTIVE_GROUPS))

    # Pre-load groups from campaigns
    campaigns = load_campaigns()
    for cid, camp in campaigns.items():
        if camp.get("status") == "active":
            for link in camp.get("groups", []):
                await join_group(link, cid)
                await asyncio.sleep(random.uniform(5, 15))

    await asyncio.gather(
        client.run_until_disconnected(),
        process_send_queue(),
        join_groups_loop(),
        daily_report_loop(),
    )


if __name__ == "__main__":
    asyncio.run(main())
