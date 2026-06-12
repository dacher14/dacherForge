#!/bin/bash
# setup-vps.sh — Auto-deploy DacherForge SDR Agent on European VPS
# Run this on the VPS after ssh login

set -e

echo "════════════════════════════════════════════════════════════════"
echo "🚀 DacherForge SDR Agent — VPS Setup"
echo "════════════════════════════════════════════════════════════════"

# --- Create directories ---
echo "📁 Creating directories..."
mkdir -p /root/outreach
cd /root/outreach

# --- Update system ---
echo "🔄 Updating system..."
apt-get update -qq
apt-get upgrade -y -qq

# --- Install dependencies ---
echo "📦 Installing dependencies..."
apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    jq \
    sqlite3

# --- Create virtual environment ---
echo "🐍 Setting up Python virtual environment..."
python3 -m venv /root/outreach/venv
source /root/outreach/venv/bin/activate

# --- Install Python packages ---
echo "📚 Installing Python packages..."
pip install --upgrade pip -q
pip install \
    telethon \
    flask \
    psutil \
    requests \
    -q

# --- Display instructions ---
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✅ SETUP COMPLETE!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "📋 NEXT STEPS:"
echo ""
echo "1️⃣  Copy files to VPS:"
echo "   scp -r agent/ root@85.192.26.36:/root/outreach/"
echo ""
echo "2️⃣  Copy Telegram session (if exists):"
echo "   scp userbot_session.session root@85.192.26.36:/root/outreach/"
echo ""
echo "3️⃣  Copy JSON configs:"
echo "   scp campaigns.json send_queue.json sent.json root@85.192.26.36:/root/outreach/"
echo ""
echo "4️⃣  Make scripts executable:"
echo "   ssh root@85.192.26.36 'chmod +x /root/outreach/agent/status.sh /root/outreach/agent/userbot.py'"
echo ""
echo "5️⃣  Start userbot in background:"
echo "   ssh root@85.192.26.36 'cd /root/outreach && source venv/bin/activate && nohup python3 agent/userbot.py > userbot.log 2>&1 &'"
echo ""
echo "6️⃣  Check status anytime:"
echo "   ssh root@85.192.26.36 'bash /root/outreach/agent/status.sh'"
echo ""
echo "════════════════════════════════════════════════════════════════"
