# Nova Voice Assistant — Project Context

## What is this

A speech-to-speech voice assistant using Amazon Nova Sonic + AWS Strands multi-agent framework.
Forked from `aws-samples/sample-aws-strands-nova-voice-assistant`.

## Architecture

```
User (mic) → React Frontend (WebSocket) → Python Backend → Amazon Nova Sonic (Bedrock)
                                                         → Strands Supervisor Agent → EC2/SSM/Backup Agents
                                                         → Audio response → User (speakers)
```

## Key Fixes Applied (vs original sample)

1. **SDK v0.11.0 migration**: `BedrockRuntimeClient` → `AsyncBedrockRuntimeClient` + `AsyncBedrockRuntimeConfig.resolve()` + `AWSCRTHTTPClient` transport
2. **ESLint**: Removed `react-app/jest` from eslintConfig (incompatible)
3. **crypto.randomUUID**: Added fallback for non-secure contexts (HTTP over IP)
4. **WebSocket host**: Backend binds to `0.0.0.0` (not just `127.0.0.1`) for WSL→Windows access
5. **WebSocket URL default**: Frontend defaults to `ws://172.29.21.117:8080` (WSL IP)

## Running

### Prerequisites
- Python 3.12+ with venv at `~/venvs/nova-voice`
- Node 16+ with frontend at `~/nova-voice-frontend` (Linux FS — NTFS can't symlink)
- AWS credentials with Bedrock access in us-east-1
- Microphone + speakers

### Quick Start
```bash
./start.sh
```

### Manual Start
**Terminal 1 — Backend:**
```bash
cd backend
source ~/venvs/nova-voice/bin/activate
export PYTHONPATH=$PYTHONPATH:$(pwd)
export BYPASS_TOOL_CONSENT=true
eval $(aws configure export-credentials --format env)
python -m src.voice_based_aws_agent.main --profile default --region us-east-1 --port 8080 --host 0.0.0.0
```

**Terminal 2 — Frontend:**
```bash
cd ~/nova-voice-frontend
DISABLE_ESLINT_PLUGIN=true PORT=3001 npx react-scripts start
```

Open `http://localhost:3001` in Chrome.

## WSL Specifics

- Backend runs in WSL, frontend in WSL, browser in Windows
- `localhost:3001` (frontend) works via WSL port forwarding
- WebSocket needs WSL IP (`172.29.21.117`) — localhost doesn't forward port 8080 reliably
- venv must be in Linux FS (`~/venvs/`) — NTFS doesn't support symlinks
- `node_modules` must be in Linux FS (`~/nova-voice-frontend/`)

## AWS Auth

- Uses SSO profile `default` → account `747814092865` / role `AWSAdministratorAccess`
- Nova Sonic SDK needs env vars: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`
- `eval $(aws configure export-credentials --format env)` exports them from SSO
- Token expires every ~8-12h — re-run `aws sso login` when needed

## Cost

Light usage (~50 conversations/week): **~$8-15/month**

## Next Steps

- [ ] Replace EC2/SSM/Backup agents with custom MCP-connected agents
- [ ] Connect to Notion, GitHub, Memory via Strands tools
- [ ] Test French/Arabic voice support
- [ ] Evaluate latency for real-time conversation
