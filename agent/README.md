# 🤖 DacherForge — Self-Learning SDR Agent

A Telegram-based lead generation bot with self-improving AI strategy engine. The system continuously learns from outcomes and optimizes messaging strategies without retraining the model.

## 📋 Table of Contents

- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Self-Learning System](#self-learning-system)
- [Monitoring](#monitoring)

## 🏗️ Architecture

### Core Modules

1. **Lead Intelligence Module**
   - Collects lead information from Telegram groups
   - Stores user data, company info, industry signals
   - Never discards data — builds historical context

2. **Strategy Engine (Multi-Armed Bandit)**
   - 80% exploitation: Uses best-performing strategy for segment
   - 20% exploration: Tests alternative strategies
   - Adapts by industry, company size, lead source

3. **Message Generation**
   - Selects from 5 pre-trained strategies:
     - `short_direct`: Direct, concise messages
     - `case_study`: References successful examples
     - `roi_focused`: Financial benefit focused
     - `problem_agitation`: Problem-aware approach
     - `personalized_research`: Deep personalization

4. **Outcome Tracking**
   - Records all interactions: replies, meetings, deals
   - Assigns rewards: reply=1pt, meeting=10pts, deal=50pts
   - Full conversation history per lead

5. **Sales Brain Intelligence**
   - Analyzes strategy performance by:
     - Industry
     - Company size
     - Lead source
   - Identifies best-performing segments
   - Generates daily performance reports

## 🚀 Installation

### On European VPS

```bash
# SSH into VPS
ssh root@85.192.26.36

# Download and run setup script
curl -O https://raw.githubusercontent.com/dacher14/dacherforge/main/agent/setup-vps.sh
bash setup-vps.sh
```

### Manual Setup

```bash
# Create directory
mkdir -p /root/outreach
cd /root/outreach

# Install dependencies
apt-get update
apt-get install -y python3 python3-pip
pip3 install telethon flask psutil requests

# Activate virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate
```

## ⚙️ Configuration

### API Credentials

Edit `userbot.py` to configure:

```python
API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"
BOT_USERNAME = "@CowDacherRonaldoBot"
SHARED_SECRET = "dK9mX2vL8nP4qR7wT1uY5cF3hJ6bN0eA_Ronaldu+Danya+CR7+Gol"
```

### Rate Limits

```python
MAX_PER_HOUR = 15    # Max 15 DMs per hour
MAX_PER_DAY = 40     # Max 40 DMs per day
RATE_LIMITS = True   # Enable rate limiting
```

### Campaigns Configuration

`campaigns.json`:

```json
{
  "campaign_1": {
    "id": "campaign_1",
    "status": "active",
    "search_keywords": ["crypto", "web3", "blockchain"],
    "groups": [
      "https://t.me/crypto_dev_community",
      "@python_developers"
    ]
  }
}
```

## 🎯 Usage

### Start Userbot

```bash
# Background execution
nohup python3 agent/userbot.py > userbot.log 2>&1 &

# Or with supervisor for auto-restart
supervisord -c /root/outreach/supervisord.conf
```

### Check Status

```bash
bash agent/status.sh
```

### View Logs

```bash
tail -f /root/outreach/userbot.log
tail -f /root/outreach/sdr_intelligence.db
```

## 🧠 Self-Learning System

### How It Works

1. **Lead Detection**
   - Bot monitors configured Telegram groups
   - Detects messages matching active campaign keywords
   - Stores lead information in database

2. **Strategy Selection**
   ```
   if random() < 0.20:
       strategy = random_strategy  # Explore (20%)
   else:
       strategy = best_strategy_for_segment  # Exploit (80%)
   ```

3. **Message Generation**
   - Uses selected strategy template
   - Personalizes with lead context
   - Sends via Telegram DM

4. **Outcome Tracking**
   - No reply: 0 reward
   - Reply: 1 point
   - Conversation started: 3 points
   - Meeting booked: 10 points
   - Deal won: 50 points

5. **Continuous Learning**
   - Updates strategy performance metrics
   - Recalculates best strategies by segment
   - Never stops exploring alternatives

### Database Schema

```sql
leads                    -- All collected leads
├── user_id
├── username
├── full_name
├── company
├── industry
└── created_at

messages                 -- All sent messages
├── lead_id
├── strategy_id
├── message_text
└── sent_at

outcomes                 -- Lead responses & results
├── message_id
├── lead_id
├── outcome_type
├── reward
└── recorded_at

strategy_performance     -- Strategy effectiveness by segment
├── strategy_id
├── industry
├── company_size
├── total_sent
├── total_replies
├── total_meetings
└── total_reward

experiments              -- A/B testing data
├── experiment_id
├── strategy_id
├── segment
├── allocation
└── performance
```

## 📊 Monitoring

### Daily Intelligence Report

Run automatically at 23:00:

```bash
# View report in logs
grep "Daily Report" /root/outreach/userbot.log
```

### Manual Queries

```bash
# Top strategies by performance
sqlite3 /root/outreach/sdr_intelligence.db
SELECT strategy_id, total_sent, total_replies, total_meetings
FROM strategy_performance
ORDER BY total_meetings DESC;

# Best performing segments
SELECT industry, company_size, SUM(total_reward) as reward
FROM strategy_performance
WHERE total_sent > 10
GROUP BY industry, company_size
ORDER BY reward DESC;
```

## 🔒 Security Notes

- Never commit `userbot_session.session` to git
- Store credentials securely (use environment variables in production)
- Rate limiting prevents Telegram account suspension
- Only targets groups where bot successfully joined (allowlist)
- Operating hours: 9:00 - 21:00 (prevents spam appearance)

## 📈 Expected Improvements Over Time

**Week 1:** Initial strategy performance baseline
**Week 2-4:** Identify best strategies per industry
**Month 2-3:** Optimize by company size and region
**Month 4+:** Industry-specific templates and personalization

With 500k+ messages and 10k+ replies, enable:
- Policy optimization without retraining
- Predictive lead scoring
- Automatic segment discovery
- Dynamic strategy allocation

## 🛠️ Troubleshooting

### Userbot not responding

```bash
# Check if running
ps aux | grep userbot.py

# Force restart
pkill -9 -f userbot.py
nohup python3 /root/outreach/agent/userbot.py > /root/outreach/userbot.log 2>&1 &
```

### Telegram connection issues

- Verify Telegram not blocked by ISP (European VPS required)
- Check rate limits: not more than 15 DMs/hour
- Review `userbot.log` for specific errors

### Database corruption

```bash
# Backup and recreate
cp /root/outreach/sdr_intelligence.db /root/outreach/sdr_intelligence.db.backup
sqlite3 /root/outreach/sdr_intelligence.db ".schema" > schema.sql
rm /root/outreach/sdr_intelligence.db
# Restart userbot to recreate
```

## 📞 Support

For issues:
1. Check logs: `tail -f userbot.log`
2. Verify configuration: check campaigns.json
3. Review database: `sqlite3 sdr_intelligence.db ".tables"`
4. Contact: daniilbaranok@gmail.com

---

**DacherForge** — Self-Improving AI Sales Development Representative
