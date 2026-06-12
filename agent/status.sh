#!/bin/bash
# status.sh — DacherForge SDR Agent Status with Self-Learning Intelligence
# Usage: bash /root/outreach/status.sh

OUT=/root/outreach
DB=$OUT/sdr_intelligence.db

echo "════════════════════════════════════════════════════════════════"
echo "   🤖 DACHER FORGE — SDR AGENT STATUS (Self-Learning)"
echo "   $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════════════════════"

# --- 1. Server Status ---
echo ""
echo "▶ SERVER (Flask :5000)"
if curl -s --max-time 3 http://localhost:5000/health | grep -q ok; then
  echo "  ✅ Running — responds to /health"
else
  echo "  ❌ NOT responding on :5000"
fi
SRV_PID=$(pgrep -f "server.py")
[ -n "$SRV_PID" ] && echo "  PID: $SRV_PID  (uptime: $(ps -o etime= -p $SRV_PID 2>/dev/null | tr -d ' '))" || echo "  ❌ Process not found"

# --- 2. Userbot Status ---
echo ""
echo "▶ USERBOT (Telegram + Self-Learning)"
UB_PID=$(pgrep -f "userbot.py")
if [ -n "$UB_PID" ]; then
  echo "  ✅ Running — PID: $UB_PID  (uptime: $(ps -o etime= -p $UB_PID 2>/dev/null | tr -d ' '))"
else
  echo "  ❌ NOT running"
fi

if [ -f "$OUT/userbot_session.session" ]; then
  echo "  ✅ Session file exists"
else
  echo "  ⚠️  No session file"
fi

# --- 3. Campaigns ---
echo ""
echo "▶ CAMPAIGNS"
if [ -f "$OUT/campaigns.json" ]; then
  python3 - <<'PY'
import json
try:
    c = json.load(open("/root/outreach/campaigns.json"))
    active = [v for v in c.values() if v.get("status") == "active"]
    print(f"  Total: {len(c)} | Active: {len(active)}")
    for v in active[:3]:
        kw = ", ".join(v.get("search_keywords", [])[:3])
        gr = len(v.get("groups", []))
        print(f"   • ID #{v.get('id')} | Groups: {gr} | Keywords: {kw}")
    if not active:
        print("  ⚠️  NO active campaigns")
except Exception as e:
    print(f"  ❌ campaigns.json error: {e}")
PY
else
  echo "  ⚠️  campaigns.json missing"
fi

# --- 4. Self-Learning Intelligence ---
echo ""
echo "▶ SELF-LEARNING INTELLIGENCE"
if [ -f "$DB" ]; then
  python3 - <<'PY'
import sqlite3
from datetime import datetime, timedelta

db = "/root/outreach/sdr_intelligence.db"
try:
    conn = sqlite3.connect(db)
    c = conn.cursor()

    # Total leads
    c.execute("SELECT COUNT(*) FROM leads")
    total_leads = c.fetchone()[0]

    # Total messages
    c.execute("SELECT COUNT(*) FROM messages")
    total_messages = c.fetchone()[0]

    # Outcomes
    c.execute("SELECT outcome_type, COUNT(*) FROM outcomes GROUP BY outcome_type")
    outcomes = dict(c.fetchall())

    print(f"  📊 Leads Collected: {total_leads}")
    print(f"  💬 Messages Sent: {total_messages}")
    print(f"  ✉️  Replies: {outcomes.get('reply', 0)}")
    print(f"  🤝 Meetings: {outcomes.get('meeting_booked', 0)}")
    print(f"  💰 Deal Won: {outcomes.get('deal_won', 0)}")

    # Best performing strategy
    c.execute('''
        SELECT strategy_id, total_sent, total_replies, total_meetings
        FROM strategy_performance
        ORDER BY (total_meetings * 10 + total_replies) DESC
        LIMIT 1
    ''')
    result = c.fetchone()
    if result:
        strategy, sent, replies, meetings = result
        reply_rate = round(replies / sent * 100, 1) if sent > 0 else 0
        print(f"  🏆 Best Strategy: {strategy} ({reply_rate}% reply rate)")

    # Yesterday's activity
    yesterday = (datetime.now() - timedelta(days=1)).date()
    c.execute('''
        SELECT COUNT(*) FROM messages
        WHERE DATE(sent_at) = ?
    ''', (yesterday,))
    yesterday_count = c.fetchone()[0]
    print(f"  📈 Yesterday Activity: {yesterday_count} messages")

    conn.close()
except Exception as e:
    print(f"  ❌ Database error: {e}")
PY
else
  echo "  ⚠️  Database not initialized (will be created on first run)"
fi

# --- 5. DM Queue ---
echo ""
echo "▶ OUTBOUND DM QUEUE"
if [ -f "$OUT/send_queue.json" ]; then
  python3 - <<'PY'
import json
from collections import Counter
try:
    q = json.load(open("/root/outreach/send_queue.json"))
    cnt = Counter(v.get("status","?") for v in q.values())
    total = len(q)
    pending = cnt.get('pending', 0)
    sent = cnt.get('sent', 0)
    error = cnt.get('error', 0)

    print(f"  Total: {total} | Pending: {pending} | Sent: {sent} | Error: {error}")

    if error > 0:
        print(f"  ⚠️  {error} messages with errors (possible Telegram flood-limit)")
except Exception as e:
    print(f"  ❌ Queue error: {e}")
PY
else
  echo "  ℹ️  Queue empty (no file)"
fi

# --- 6. System Resources ---
echo ""
echo "▶ SYSTEM RESOURCES"
python3 - <<'PY'
import psutil
import os

# Memory
mem = psutil.virtual_memory()
print(f"  Memory: {mem.percent}% used ({mem.used // (1024**2)}MB / {mem.total // (1024**2)}MB)")

# Disk
disk = psutil.disk_usage('/root/outreach')
print(f"  Disk: {disk.percent}% used ({disk.used // (1024**2)}MB / {disk.total // (1024**2)}MB)")

# CPU
cpu = psutil.cpu_percent(interval=1)
print(f"  CPU: {cpu}% usage")

# DB size
db_path = "/root/outreach/sdr_intelligence.db"
if os.path.exists(db_path):
    db_size = os.path.getsize(db_path) / (1024**2)
    print(f"  Intelligence DB: {db_size:.2f}MB")
PY

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════════════════════════════"
