#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$HOME/nova-voice-frontend"
VENV_DIR="$HOME/venvs/nova-voice"
WSL_IP=$(hostname -I | awk '{print $1}')

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN} 🎙️  AWS Strands Nova Voice Assistant${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"

# --- Sync frontend source if changed ---
echo -e "${YELLOW}Syncing frontend source...${NC}"
rsync -a --exclude node_modules --exclude build "$PROJECT_DIR/frontend/" "$FRONTEND_DIR/"
echo "✅ Frontend synced"

# --- Check & refresh AWS credentials ---
echo -e "${YELLOW}Checking AWS credentials...${NC}"
if ! aws sts get-caller-identity --region us-east-1 > /dev/null 2>&1; then
    echo -e "${RED}Token expired or invalid. Logging in...${NC}"
    rm -rf ~/.aws/sso/cache/*
    aws sso login --profile default
fi

eval $(aws configure export-credentials --format env)

if [ -z "$AWS_ACCESS_KEY_ID" ]; then
    echo -e "${RED}❌ Failed to export credentials.${NC}"
    exit 1
fi

# Verify credentials actually work
if ! aws sts get-caller-identity --region us-east-1 > /dev/null 2>&1; then
    echo -e "${RED}❌ Credentials exported but still invalid. Try: rm -rf ~/.aws/sso/cache/* && aws sso login${NC}"
    exit 1
fi

echo -e "✅ AWS credentials OK (${AWS_ACCESS_KEY_ID:0:12}...)"

# --- Kill any existing processes on our ports ---
pkill -f "voice_based_aws_agent.main" 2>/dev/null || true
pkill -f "react-scripts start" 2>/dev/null || true
sleep 1

# --- Start backend ---
echo -e "${YELLOW}Starting backend on 0.0.0.0:8080...${NC}"
cd "$BACKEND_DIR"
source "$VENV_DIR/bin/activate"
export PYTHONPATH=$PYTHONPATH:$(pwd)
export BYPASS_TOOL_CONSENT=true
python -m src.voice_based_aws_agent.main --profile default --region us-east-1 --port 8080 --host 0.0.0.0 &
BACKEND_PID=$!

# Wait for backend to be ready
sleep 3
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${RED}❌ Backend failed to start. Check logs above.${NC}"
    exit 1
fi
echo "✅ Backend running (PID: $BACKEND_PID)"

# --- Start frontend ---
echo -e "${YELLOW}Starting frontend on port 3001...${NC}"
cd "$FRONTEND_DIR"
DISABLE_ESLINT_PLUGIN=true BROWSER=none PORT=3001 npx react-scripts start &
FRONTEND_PID=$!
sleep 5
echo "✅ Frontend running (PID: $FRONTEND_PID)"

# --- Done ---
echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN} ✅ All systems running!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo -e "  🌐 Open in Chrome:  ${GREEN}http://localhost:3001${NC}"
echo -e "  🔌 WebSocket URL:   ${GREEN}ws://${WSL_IP}:8080${NC}"
echo ""
echo -e "  Press Ctrl+C to stop everything"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"

# --- Cleanup on exit ---
trap "echo ''; echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; wait 2>/dev/null; echo 'Done.'; exit 0" SIGINT SIGTERM
wait
