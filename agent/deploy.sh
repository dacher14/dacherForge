#!/bin/bash
# deploy.sh — Deploy DacherForge to European VPS
# Usage: bash deploy.sh <VPS_IP> <ROOT_PASSWORD> [SESSION_FILE]

VPS_IP="${1:-85.192.26.36}"
VPS_PASS="${2:-wZ400iqbkb60}"
VPS_USER="root"
SESSION_FILE="${3:-}"
LOCAL_OUTREACH_DIR="/root/outreach"
REMOTE_OUTREACH_DIR="/root/outreach"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "════════════════════════════════════════════════════════════════"
echo -e "${GREEN}🚀 DacherForge Deployment to VPS${NC}"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "📍 Target: $VPS_USER@$VPS_IP"
echo "🔐 Using password authentication"
echo ""

# --- 1. Setup VPS with sshpass ---
echo -e "${YELLOW}[1/5] Setting up VPS...${NC}"
sshpass -p "$VPS_PASS" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_IP << 'SETUP'
set -e
mkdir -p /root/outreach
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git curl jq sqlite3 openssh-client openssh-server
python3 -m venv /root/outreach/venv
source /root/outreach/venv/bin/activate
pip install --upgrade pip -q
pip install telethon flask psutil requests -q
echo "✅ VPS setup complete"
SETUP

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ VPS setup failed${NC}"
    exit 1
fi

# --- 2. Copy agent code ---
echo -e "${YELLOW}[2/5] Uploading agent code...${NC}"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

sshpass -p "$VPS_PASS" scp -o StrictHostKeyChecking=no \
    "$SCRIPT_DIR/userbot.py" \
    "$SCRIPT_DIR/status.sh" \
    "$SCRIPT_DIR/README.md" \
    $VPS_USER@$VPS_IP:$REMOTE_OUTREACH_DIR/

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Failed to upload code${NC}"
    exit 1
fi

# --- 3. Copy Telegram session if provided ---
if [ -n "$SESSION_FILE" ] && [ -f "$SESSION_FILE" ]; then
    echo -e "${YELLOW}[3/5] Uploading Telegram session...${NC}"
    sshpass -p "$VPS_PASS" scp -o StrictHostKeyChecking=no \
        "$SESSION_FILE" \
        $VPS_USER@$VPS_IP:$REMOTE_OUTREACH_DIR/userbot_session.session
else
    echo -e "${YELLOW}[3/5] No session file provided (will authenticate on first run)${NC}"
fi

# --- 4. Copy configuration files if they exist locally ---
echo -e "${YELLOW}[4/5] Uploading configuration files...${NC}"
for file in campaigns.json send_queue.json sent.json; do
    if [ -f "$LOCAL_OUTREACH_DIR/$file" ]; then
        echo "  📄 Uploading $file..."
        sshpass -p "$VPS_PASS" scp -o StrictHostKeyChecking=no \
            "$LOCAL_OUTREACH_DIR/$file" \
            $VPS_USER@$VPS_IP:$REMOTE_OUTREACH_DIR/
    else
        echo "  ⚠️  $file not found locally (will be created on demand)"
    fi
done

# --- 5. Start userbot ---
echo -e "${YELLOW}[5/5] Starting userbot...${NC}"
sshpass -p "$VPS_PASS" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_IP << 'START'
cd /root/outreach
chmod +x agent/status.sh agent/userbot.py
source venv/bin/activate

# Kill any existing processes
pkill -f userbot.py || true
sleep 1

# Start in background
nohup python3 agent/userbot.py > userbot.log 2>&1 &
sleep 2

# Verify
if pgrep -f userbot.py > /dev/null; then
    echo "✅ Userbot started successfully"
    echo ""
    echo "Process ID: $(pgrep -f userbot.py)"
else
    echo "⚠️  Userbot may not have started. Check log:"
    echo "ssh root@85.192.26.36 'tail userbot.log'"
fi
START

echo ""
echo "════════════════════════════════════════════════════════════════"
echo -e "${GREEN}✅ DEPLOYMENT COMPLETE!${NC}"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "📋 Quick commands:"
echo ""
echo "🔍 Check status:"
echo "   sshpass -p '$VPS_PASS' ssh root@$VPS_IP 'bash /root/outreach/agent/status.sh'"
echo ""
echo "📊 View logs (real-time):"
echo "   sshpass -p '$VPS_PASS' ssh root@$VPS_IP 'tail -f /root/outreach/userbot.log'"
echo ""
echo "🔄 Restart userbot:"
echo "   sshpass -p '$VPS_PASS' ssh root@$VPS_IP 'pkill -9 -f userbot.py && sleep 1 && cd /root/outreach && source venv/bin/activate && nohup python3 agent/userbot.py > userbot.log 2>&1 &'"
echo ""
echo "🗄️  View database:"
echo "   sshpass -p '$VPS_PASS' ssh root@$VPS_IP 'sqlite3 /root/outreach/sdr_intelligence.db \".tables\"'"
echo ""
echo "════════════════════════════════════════════════════════════════"
