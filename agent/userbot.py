import asyncio
import json
import logging
import os
import random
import re
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import Channel, Chat
from telethon.errors import UserAlreadyParticipantError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
BOT_USERNAME = "@CowDacherRonaldoBot"
SHARED_SECRET = "dK9mX2vL8nP4qR7wT1uY5cF3hJ6bN0eA_Ronaldu+Danya+CR7+Gol"
SESSION_NAME = "/root/outreach/userbot_session"
CAMPAIGNS_FILE = "/root/outreach/campaigns.json"
SEND_QUEUE_FILE = "/root/outreach/send_queue.json"
SENT_FILE = "/root/outreach/sent.json"
DB_FILE = "/root/outreach/sdr_intelligence.db"

MAX_PER_HOUR = 15
MAX_PER_DAY = 40
RATE_LIMITS = True

# =============================================================================
# STRATEGIES - SDR Outreach Strategies
# =============================================================================
STRATEGIES = {
    "short_direct": {
        "id": "short_direct",
        "name": "Short Direct Outreach",
        "description": "Direct, concise message focusing on value",
        "template": "Hi {name}, I noticed {company}. Quick question: {question}",
        "length": "short",
        "tone": "professional",
    },
    "case_study": {
        "id": "case_study",
        "name": "Case Study Based",
        "description": "Reference successful case studies in similar industry",
        "template": "Hi {name}, similar companies like {company} have achieved {result}. Would you be open to a brief chat?",
        "length": "medium",
        "tone": "credible",
    },
    "roi_focused": {
        "id": "roi_focused",
        "name": "ROI Focused Outreach",
        "description": "Focus on specific financial benefits",
        "template": "Hi {name}, companies in {industry} are seeing {roi_metric} improvement. Worth 15 min to discuss?",
        "length": "short",
        "tone": "data_driven",
    },
    "problem_agitation": {
        "id": "problem_agitation",
        "name": "Problem Agitation",
        "description": "Acknowledge pain points then offer solution",
        "template": "Hi {name}, I see {problem}. Most teams in {industry} struggle with this. We've helped solve it for {similar_company}.",
        "length": "medium",
        "tone": "empathetic",
    },
    "personalized_research": {
        "id": "personalized_research",
        "name": "Personalized Research",
        "description": "Deep research-based personalization",
        "template": "Hi {name}, I found your {achievement}. Impressed by {specific_detail}. Let's connect.",
        "length": "short",
        "tone": "personalized",
    },
}

REWARD_SYSTEM = {
    "no_reply": 0,
    "reply": 1,
    "conversation_started": 3,
    "meeting_booked": 10,
    "proposal_sent": 20,
    "deal_won": 50,
    "deal_lost": 0,
}

# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================
def init_database():
    """Initialize SQLite database for lead intelligence and strategy tracking."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Leads table
    c.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT UNIQUE NOT NULL,
            username TEXT,
            full_name TEXT,
            company TEXT,
            industry TEXT,
            country TEXT,
            company_size TEXT,
            job_title TEXT,
            company_website TEXT,
            technology_stack TEXT,
            growth_signals TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Messages table
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            strategy_id TEXT NOT NULL,
            message_text TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(lead_id) REFERENCES leads(id)
        )
    ''')

    # Outcomes table
    c.execute('''
        CREATE TABLE IF NOT EXISTS outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            lead_id INTEGER NOT NULL,
            outcome_type TEXT NOT NULL,
            reward INTEGER DEFAULT 0,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(message_id) REFERENCES messages(id),
            FOREIGN KEY(lead_id) REFERENCES leads(id)
        )
    ''')

    # Strategy performance table
    c.execute('''
        CREATE TABLE IF NOT EXISTS strategy_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT NOT NULL,
            industry TEXT,
            company_size TEXT,
            total_sent INTEGER DEFAULT 0,
            total_replies INTEGER DEFAULT 0,
            total_meetings INTEGER DEFAULT 0,
            total_reward INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Experiments table (for A/B testing)
    c.execute('''
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id TEXT UNIQUE NOT NULL,
            strategy_id TEXT NOT NULL,
            segment TEXT,
            allocation REAL DEFAULT 0.0,
            performance REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()

# =============================================================================
# LEAD INTELLIGENCE MODULE
# =============================================================================
class LeadIntelligence:
    """Collect, store, and analyze lead information."""

    def __init__(self):
        self.db_file = DB_FILE

    def store_lead(self, user_id, username, full_name, company=None,
                   industry=None, country=None, source="telegram_groups"):
        """Store lead with all available information."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        try:
            c.execute('''
                INSERT OR REPLACE INTO leads
                (user_id, username, full_name, company, industry, country, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, full_name, company, industry, country, source))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Lead storage error: {e}")
            return False
        finally:
            conn.close()

    def get_lead(self, user_id):
        """Retrieve lead information."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute('SELECT * FROM leads WHERE user_id = ?', (user_id,))
        lead = c.fetchone()
        conn.close()
        return lead

    def analyze_lead(self, lead_data):
        """Extract industry, company size, and other signals from lead data."""
        analysis = {
            "industry": None,
            "company_size": "unknown",
            "growth_signals": [],
            "technology_stack": [],
        }
        # This would be enhanced with NLP/LLM analysis
        return analysis

# =============================================================================
# STRATEGY ENGINE - Multi-Armed Bandit
# =============================================================================
class StrategyEngine:
    """Select best strategy for each lead based on historical performance."""

    def __init__(self, exploration_rate=0.2):
        self.db_file = DB_FILE
        self.exploration_rate = exploration_rate  # 20% for experimentation

    def get_best_strategy(self, lead_id, industry=None, company_size=None):
        """
        Select strategy using 80/20 rule:
        - 80%: Use best performing strategy for segment
        - 20%: Explore alternative strategies
        """
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        # If random <= exploration_rate, explore
        if random.random() < self.exploration_rate:
            # Select random strategy for exploration
            strategy_id = random.choice(list(STRATEGIES.keys()))
            logger.info(f"Exploration: Selected strategy {strategy_id}")
        else:
            # Get best performing strategy
            c.execute('''
                SELECT strategy_id FROM strategy_performance
                WHERE (industry = ? OR industry IS NULL)
                AND (company_size = ? OR company_size IS NULL)
                ORDER BY (total_meetings * 10 + total_replies) / NULLIF(total_sent, 0) DESC
                LIMIT 1
            ''', (industry, company_size))

            result = c.fetchone()
            strategy_id = result[0] if result else random.choice(list(STRATEGIES.keys()))
            logger.info(f"Exploitation: Selected strategy {strategy_id}")

        conn.close()
        return STRATEGIES.get(strategy_id)

    def update_strategy_performance(self, strategy_id, industry, company_size,
                                   outcome_type):
        """Update strategy performance metrics."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        reward = REWARD_SYSTEM.get(outcome_type, 0)

        c.execute('''
            INSERT INTO strategy_performance
            (strategy_id, industry, company_size, total_sent, total_replies, total_meetings, total_reward)
            VALUES (?, ?, ?, 1, 0, 0, ?)
            ON CONFLICT DO UPDATE SET
                total_sent = total_sent + 1,
                total_reward = total_reward + ?
        ''', (strategy_id, industry, company_size, reward, reward))

        if outcome_type == "reply":
            c.execute('''
                UPDATE strategy_performance
                SET total_replies = total_replies + 1
                WHERE strategy_id = ? AND industry = ? AND company_size = ?
            ''', (strategy_id, industry, company_size))

        if outcome_type == "meeting_booked":
            c.execute('''
                UPDATE strategy_performance
                SET total_meetings = total_meetings + 1
                WHERE strategy_id = ? AND industry = ? AND company_size = ?
            ''', (strategy_id, industry, company_size))

        conn.commit()
        conn.close()

# =============================================================================
# MESSAGE GENERATION
# =============================================================================
class MessageGenerator:
    """Generate personalized messages based on strategy and lead context."""

    def generate_message(self, lead_info, strategy):
        """Generate message using strategy template."""
        # Extract placeholders
        template = strategy.get("template", "Hi {name}, let's connect")

        # Prepare substitutions
        substitutions = {
            "name": lead_info.get("full_name", "there").split()[0] if lead_info.get("full_name") else "there",
            "company": lead_info.get("company", "your company"),
            "industry": lead_info.get("industry", "your industry"),
            "question": "are you open to exploring new opportunities?",
            "result": "20-40% efficiency gains",
            "roi_metric": "revenue growth of 25%",
            "problem": "manual processes",
            "similar_company": "companies like yours",
            "achievement": "your recent growth",
            "specific_detail": "your team's innovative approach",
        }

        # Generate message
        message = template.format(**substitutions)
        return message

# =============================================================================
# OUTCOME TRACKING
# =============================================================================
class OutcomeTracker:
    """Track outcomes and assign rewards."""

    def __init__(self):
        self.db_file = DB_FILE

    def record_outcome(self, message_id, lead_id, outcome_type):
        """Record outcome and assign reward."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        reward = REWARD_SYSTEM.get(outcome_type, 0)

        c.execute('''
            INSERT INTO outcomes (message_id, lead_id, outcome_type, reward)
            VALUES (?, ?, ?, ?)
        ''', (message_id, lead_id, outcome_type, reward))

        conn.commit()
        conn.close()

        logger.info(f"Outcome recorded: {outcome_type} (reward: {reward})")

    def get_lead_history(self, lead_id, limit=10):
        """Get interaction history for a lead."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute('''
            SELECT m.message_text, m.strategy_id, o.outcome_type, m.sent_at
            FROM messages m
            LEFT JOIN outcomes o ON m.id = o.message_id
            WHERE m.lead_id = ?
            ORDER BY m.sent_at DESC
            LIMIT ?
        ''', (lead_id, limit))

        history = c.fetchall()
        conn.close()
        return history

# =============================================================================
# SALES BRAIN - Intelligence Layer
# =============================================================================
class SalesBrain:
    """Analyze patterns and generate insights."""

    def __init__(self):
        self.db_file = DB_FILE

    def get_strategy_performance_by_industry(self, industry):
        """Get performance statistics by industry."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute('''
            SELECT strategy_id,
                   total_sent,
                   total_replies,
                   total_meetings,
                   ROUND(CAST(total_replies AS FLOAT) / NULLIF(total_sent, 0) * 100, 2) as reply_rate,
                   ROUND(CAST(total_meetings AS FLOAT) / NULLIF(total_sent, 0) * 100, 2) as meeting_rate
            FROM strategy_performance
            WHERE industry = ?
            ORDER BY total_meetings DESC
        ''', (industry,))

        results = c.fetchall()
        conn.close()
        return results

    def get_best_performing_segments(self, limit=5):
        """Identify segments with highest conversion rates."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        c.execute('''
            SELECT industry, company_size,
                   COUNT(*) as total_leads,
                   SUM(total_reward) as total_reward,
                   AVG(CAST(total_meetings AS FLOAT) / NULLIF(total_sent, 0)) as avg_meeting_rate
            FROM strategy_performance
            WHERE total_sent > 10
            GROUP BY industry, company_size
            ORDER BY total_reward DESC
            LIMIT ?
        ''', (limit,))

        results = c.fetchall()
        conn.close()
        return results

    def generate_daily_report(self):
        """Generate daily performance report."""
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()

        yesterday = datetime.now() - timedelta(days=1)

        c.execute('''
            SELECT
                COUNT(DISTINCT m.lead_id) as unique_leads,
                COUNT(m.id) as messages_sent,
                SUM(CASE WHEN o.outcome_type = 'reply' THEN 1 ELSE 0 END) as replies,
                SUM(CASE WHEN o.outcome_type = 'meeting_booked' THEN 1 ELSE 0 END) as meetings,
                SUM(o.reward) as total_reward
            FROM messages m
            LEFT JOIN outcomes o ON m.id = o.message_id
            WHERE DATE(m.sent_at) = DATE(?)
        ''', (yesterday,))

        report = c.fetchone()
        conn.close()
        return report

# =============================================================================
# TELEGRAM CLIENT & MAIN LOGIC
# =============================================================================
sent_today = 0
sent_hour = 0
last_reset_day = datetime.now().day
last_reset_hour = datetime.now().hour
ACTIVE_GROUP_IDS = set()

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
lead_intel = LeadIntelligence()
strategy_engine = StrategyEngine()
message_gen = MessageGenerator()
outcome_tracker = OutcomeTracker()
sales_brain = SalesBrain()

def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_active_keywords():
    campaigns = load_json(CAMPAIGNS_FILE)
    keywords = []
    for c in campaigns.values():
        if c.get("status") == "active":
            keywords.extend(c.get("search_keywords", []))
    return [k.lower() for k in keywords]

def get_active_groups():
    campaigns = load_json(CAMPAIGNS_FILE)
    groups = []
    for c in campaigns.values():
        if c.get("status") == "active":
            groups.extend(c.get("groups", []))
    return groups

def normalize_group_link(link):
    """Parse and normalize Telegram group links."""
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

def is_real_group(entity):
    """Check if entity is a real group (not a broadcast channel)."""
    if isinstance(entity, Chat):
        return True
    if isinstance(entity, Channel):
        return bool(getattr(entity, "megagroup", False))
    return False

async def resolve_and_join(link):
    """Join group by link and return group id."""
    parsed = normalize_group_link(link)
    if parsed is None:
        logger.warning("Invalid link: %s", link)
        return None
    kind, value = parsed
    try:
        if kind == "invite":
            try:
                updates = await client(ImportChatInviteRequest(value))
                entity = updates.chats[0]
            except UserAlreadyParticipantError:
                logger.info("Already in group: %s", link)
                return None
        else:
            entity = await client.get_entity(value)
            try:
                await client(JoinChannelRequest(entity))
            except Exception as e:
                logger.info("Join %s (already member?): %s", link, e)
    except Exception as e:
        logger.error("Join error %s: %s", link, e)
        return None
    if not is_real_group(entity):
        logger.warning("Not a real group: %s", link)
        return None
    logger.info("Joined group: %s (id=%s)", link, entity.id)
    return entity.id

async def process_send_queue():
    """Process DM queue with rate limiting."""
    while True:
        try:
            queue = load_json(SEND_QUEUE_FILE)
            for key, item in list(queue.items()):
                if item.get("status") == "pending":
                    try:
                        target = item.get("username") or int(item.get("user_id"))
                        await client.send_message(target, item["text"])
                        queue[key]["status"] = "sent"
                        save_json(SEND_QUEUE_FILE, queue)
                        logger.info("DM sent to %s", target)
                        await asyncio.sleep(random.uniform(60, 120))
                    except Exception as e:
                        logger.error("Send error: %s", e)
                        queue[key]["status"] = "error"
                        save_json(SEND_QUEUE_FILE, queue)
        except Exception as e:
            logger.error("Queue error: %s", e)
        await asyncio.sleep(10)

async def join_new_groups():
    """Join configured groups."""
    while True:
        try:
            for group in get_active_groups():
                gid = await resolve_and_join(group)
                if gid is not None:
                    ACTIVE_GROUP_IDS.add(gid)
                await asyncio.sleep(random.uniform(5, 15))
        except Exception as e:
            logger.error("Join loop error: %s", e)
        await asyncio.sleep(300)

@client.on(events.NewMessage())
async def handle_message(event):
    """Main handler: detect leads, select strategy, send message."""
    global sent_today, sent_hour, last_reset_day, last_reset_hour

    if event.message.out or not event.message.from_id:
        return
    if not event.is_group:
        return

    text = event.message.text or ""
    if not text or not check_triggers(text):
        return

    # Rate limiting
    now = datetime.now()
    if now.day != last_reset_day:
        sent_today = 0
        last_reset_day = now.day
    if now.hour != last_reset_hour:
        sent_hour = 0
        last_reset_hour = now.hour

    if RATE_LIMITS:
        if sent_today >= MAX_PER_DAY or sent_hour >= MAX_PER_HOUR:
            return
        if now.hour < 9 or now.hour > 21:
            return

    group = await event.get_chat()
    if ACTIVE_GROUP_IDS and group.id not in ACTIVE_GROUP_IDS:
        return

    sender = await event.get_sender()
    if not sender or sender.bot:
        return

    # =========================================================================
    # SELF-LEARNING FLOW
    # =========================================================================

    # 1. LEAD INTELLIGENCE
    user_id = str(sender.id)
    username = sender.username or ""
    full_name = ((sender.first_name or "") + " " + (sender.last_name or "")).strip()

    lead_intel.store_lead(
        user_id=user_id,
        username=username,
        full_name=full_name,
        company=None,
        industry=None,
        country=None,
        source="telegram_groups"
    )

    # 2. STRATEGY SELECTION
    strategy = strategy_engine.get_best_strategy(
        lead_id=user_id,
        industry=None,
        company_size=None
    )

    # 3. MESSAGE GENERATION
    lead_info = {
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
    }
    message_text = message_gen.generate_message(lead_info, strategy)

    # 4. MESSAGE DELIVERY
    payload = {
        "platform": "telegram_groups",
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
        "trigger_message": text[:300],
        "message": message_text,
        "strategy_id": strategy.get("id"),
        "group_name": group.title,
        "group_username": "@" + group.username if getattr(group, "username", None) else str(group.id),
        "timestamp": now.isoformat(),
        "secret": SHARED_SECRET
    }

    await send_lead_to_bot(payload)

    # 5. UPDATE METRICS
    sent_today += 1
    sent_hour += 1

    logger.info(f"Lead detected: {full_name} | Strategy: {strategy.get('name')}")

async def send_lead_to_bot(payload):
    """Send lead to central bot."""
    text = "LEAD_EVENT::" + json.dumps(payload, ensure_ascii=False)
    if len(text) > 4000:
        text = text[:4000]
    await client.send_message(BOT_USERNAME, text)
    logger.info("Lead sent: %s", payload.get("full_name"))

def check_triggers(text):
    return any(kw in text.lower() for kw in get_active_keywords())

async def daily_intelligence_report():
    """Generate and log daily intelligence report."""
    while True:
        now = datetime.now()
        # Run at 23:00 every day
        if now.hour == 23 and now.minute == 0:
            report = sales_brain.generate_daily_report()
            logger.info(f"Daily Report: {report}")

            # Best performing segments
            segments = sales_brain.get_best_performing_segments(limit=3)
            logger.info(f"Top Segments: {segments}")

            await asyncio.sleep(60)
        else:
            await asyncio.sleep(300)

async def main():
    """Start userbot with all modules."""
    init_database()
    logger.info("Database initialized")

    await client.start()
    logger.info("Userbot started with Self-Learning SDR Architecture!")
    logger.info(f"Session: {SESSION_NAME}")

    await asyncio.gather(
        client.run_until_disconnected(),
        process_send_queue(),
        join_new_groups(),
        daily_intelligence_report()
    )

if __name__ == "__main__":
    asyncio.run(main())
