#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$HOME/nova-voice-frontend"
VENV_DIR="$HOME/venvs/nova-voice"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN} AWS Strands Nova Voice Assistant${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"

# --- Check & refresh AWS credentials ---
echo -e "${YELLOW}Checking AWS credentials...${NC}"
if ! aws sts get-caller-identity --region us-east-1 > /dev/null 2>&1; then
    echo -e "${RED}Token expired. Logging in...${NC}"
    aws sso login
fi

# Export credentials as env vars (required for Nova Sonic SDK)
eval $(aws configure export-credentials --format env)

if [ -z "$AWS_ACCESS_KEY_ID" ]; then
    echo -e "${RED}❌ Failed to export credentials. Run 'aws sso login' manually.${NC}"
    exit 1
fi
echo -e "✅ AWS credentials OK (${AWS_ACCESS_KEY_ID:0:10}...)"

# --- Start backend ---
echo -e "${YELLOW}Starting backend on 0.0.0.0:8080...${NC}"
cd "$BACKEND_DIR"
source "$VENV_DIR/bin/activate"
export PYTHONPATH=$PYTHONPATH:$(pwd)
export BYPASS_TOOL_CONSENT=true
python -m src.voice_based_aws_agent.main --profile default --region us-east-1 --port 8080 --host 0.0.0.0 &
BACKEND_PID=$!
echo "✅ Backend PID: $BACKEND_PID"

sleep 3

# --- Start frontend ---
echo -e "${YELLOW}Starting frontend on port 3001...${NC}"
cd "$FRONTEND_DIR"
DISABLE_ESLINT_PLUGIN=true PORT=3001 npx react-scripts start &
FRONTEND_PID=$!
echo "✅ Frontend PID: $FRONTEND_PID"

echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN} 🎙️  Ready!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "  WebSocket: ws://<WSL-IP>:8080"
echo -e "  Frontend:  http://localhost:3001"
echo -e "  Ctrl+C to stop"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
