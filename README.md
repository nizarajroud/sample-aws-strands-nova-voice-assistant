# AWS Strands Nova Voice Assistant

> A real-time speech-to-speech voice assistant powered by Amazon Nova Sonic and AWS Strands multi-agent framework.

Forked from [aws-samples/sample-aws-strands-nova-voice-assistant](https://github.com/aws-samples/sample-aws-strands-nova-voice-assistant) with fixes for SDK v0.11.0 compatibility and WSL2 environment.

---

## 🏗️ Architecture

```
┌──────────────┐     WebSocket      ┌──────────────────┐     Bidirectional     ┌─────────────────┐
│   Browser    │◄──────────────────►│  Python Backend   │◄─────Stream──────────►│  Amazon Nova    │
│  (React UI)  │   ws://WSL:8080    │  (WebSocket srv)  │                       │  Sonic (Bedrock)│
│              │                     │                   │                       │                 │
│  🎤 Mic In   │                     │  S2sSessionMgr    │                       │  STT + LLM +    │
│  🔊 Audio Out│                     │  SupervisorAgent  │                       │  TTS (unified)  │
└──────────────┘                     │  Integration      │                       └────────┬────────┘
                                     └────────┬──────────┘                                │
                                              │                                           │
                                              │ Tool Use                                  │
                                              ▼                                           │
                                     ┌──────────────────┐                                 │
                                     │  Strands Agents   │◄────────────────────────────────┘
                                     │                   │    (toolUse / toolResult events)
                                     │  ┌─────────────┐ │
                                     │  │ Supervisor  │ │  Routes queries to specialists
                                     │  └──────┬──────┘ │
                                     │         │        │
                                     │  ┌──────┼──────┐ │
                                     │  │      │      │ │
                                     │  ▼      ▼      ▼ │
                                     │ EC2   SSM   Backup│  Specialized agents w/ use_aws tool
                                     └──────────────────┘
```

### Data Flow

1. **User speaks** → Browser captures audio via Web Audio API (16kHz PCM16)
2. **Audio chunks** → Sent as base64 over WebSocket to Python backend
3. **Backend forwards** → Audio events streamed to Nova Sonic via Bedrock bidirectional stream
4. **Nova Sonic processes** → Speech-to-text, LLM reasoning, text-to-speech (all in one model)
5. **Tool calls** → If Nova Sonic decides to use a tool, it emits `toolUse` events
6. **Agent routing** → SupervisorAgent routes to EC2/SSM/Backup specialist agents
7. **Tool results** → Sent back to Nova Sonic as `toolResult` events
8. **Audio response** → Nova Sonic generates speech, sent back as `audioOutput` events
9. **Playback** → Frontend decodes base64 audio and plays via Web Audio API

---

## 📋 Prerequisites

| Requirement | Details |
|---|---|
| **Python** | 3.12+ (tested with 3.13) |
| **Node.js** | 16+ (tested with 22) |
| **AWS Account** | With Bedrock access in `us-east-1` |
| **AWS CLI** | v2 configured with SSO |
| **OS** | WSL2 on Windows (tested) or Linux |
| **Hardware** | Microphone + speakers |
| **Browser** | Chrome (for Web Audio API + mic access) |

### AWS Permissions Required

- `bedrock:InvokeModel`
- `bedrock:InvokeModelWithResponseStream`
- `bedrock:InvokeModelWithBidirectionalStream` (Nova Sonic)
- `ec2:Describe*`, `ec2:Start*`, `ec2:Stop*`
- `ssm:*` (Systems Manager operations)
- `backup:*` (AWS Backup operations)

---

## 🚀 Quick Start

```bash
./start.sh
```

This single command:
1. Syncs frontend source
2. Checks AWS credentials (auto SSO login if expired)
3. Starts backend (port 8080)
4. Starts frontend (port 3001)

Then open **http://localhost:3001** in Chrome and click **"Start Conversation"**.

---

## 🔧 Manual Setup (First Time)

### 1. Python Virtual Environment

```bash
# Create venv in Linux filesystem (NTFS doesn't support symlinks)
python3 -m venv ~/venvs/nova-voice

# Install dependencies
source ~/venvs/nova-voice/bin/activate
pip install -r requirements.txt
```

> **Note:** `pyaudio` requires `python3-dev` and `portaudio19-dev`:
> ```bash
> sudo apt-get install -y python3.13-dev portaudio19-dev
> ```

### 2. Frontend (Node.js)

```bash
# Install in Linux filesystem (NTFS can't create symlinks for node_modules)
mkdir -p ~/nova-voice-frontend
cp -r frontend/* ~/nova-voice-frontend/
cd ~/nova-voice-frontend
npm install
```

### 3. AWS Credentials

```bash
# Configure SSO (one-time)
aws configure sso

# Login
aws sso login --profile default

# Verify
aws sts get-caller-identity --region us-east-1
```

---

## 🖥️ Manual Start

### Terminal 1 — Backend

```bash
cd backend
source ~/venvs/nova-voice/bin/activate
export PYTHONPATH=$PYTHONPATH:$(pwd)
export BYPASS_TOOL_CONSENT=true
eval $(aws configure export-credentials --format env)
python -m src.voice_based_aws_agent.main --profile default --region us-east-1 --port 8080 --host 0.0.0.0
```

### Terminal 2 — Frontend

```bash
cd ~/nova-voice-frontend
DISABLE_ESLINT_PLUGIN=true PORT=3001 npx react-scripts start
```

### Open Browser

Navigate to `http://localhost:3001`. The WebSocket URL field should show `ws://172.29.21.117:8080` (your WSL IP).

---

## 📁 Project Structure

```
├── backend/
│   ├── src/voice_based_aws_agent/
│   │   ├── agents/
│   │   │   ├── orchestrator.py          # Creates and manages all agents
│   │   │   ├── supervisor_agent.py      # Routes queries to specialists
│   │   │   ├── ec2_agent.py             # EC2 operations (Strands Agent + use_aws)
│   │   │   ├── ssm_agent.py             # SSM operations
│   │   │   └── backup_agent.py          # AWS Backup operations
│   │   ├── config/
│   │   │   ├── config.py                # BedrockModel creation, AgentConfig
│   │   │   ├── conversation_config.py   # Sliding window conversation managers
│   │   │   └── tool_config.py           # BYPASS_TOOL_CONSENT setup
│   │   ├── utils/
│   │   │   ├── aws_auth.py              # AWS session helper
│   │   │   ├── prompt_consent.py        # Consent instructions for agents
│   │   │   └── voice_integration/
│   │   │       ├── server.py            # WebSocket server (frontend ↔ backend)
│   │   │       ├── s2s_session_manager.py  # Bedrock stream (backend ↔ Nova Sonic)
│   │   │       ├── s2s_events.py        # Event format definitions
│   │   │       └── supervisor_agent_integration.py  # Bridge to Strands agents
│   │   └── main.py                      # Entry point
│   └── tools/
│       └── supervisor_tool.py           # @tool decorator for Nova Sonic tool use
├── frontend/
│   ├── src/
│   │   ├── VoiceAgent.js                # Main React component (mic, WS, playback)
│   │   ├── helper/
│   │   │   ├── s2sEvents.js             # Event builders (JS side)
│   │   │   ├── audioHelper.js           # Base64 ↔ Float32 conversion
│   │   │   └── audioPlayer.js           # Web Audio API playback
│   │   └── components/
│   │       └── EventDisplay.js          # Events panel UI
│   └── package.json
├── .kiro/steering.md                    # Project context for Kiro CLI
├── start.sh                             # One-command launcher
└── README.md                            # This file
```

---

## 🔌 Key Components

### S2sSessionManager (`s2s_session_manager.py`)

Manages the bidirectional stream to Nova Sonic:
- Opens stream with `AsyncBedrockRuntimeClient` + CRT transport
- Forwards audio chunks from frontend to Nova Sonic
- Processes responses (text, audio, tool use) from Nova Sonic
- Handles tool use → routes to SupervisorAgentIntegration → returns results

### SupervisorAgentIntegration (`supervisor_agent_integration.py`)

Bridge between Nova Sonic tool calls and Strands agents:
- Receives tool queries from Nova Sonic
- Routes through AgentOrchestrator → SupervisorAgent → Specialized agents
- Returns text results (max 800 chars for voice)

### WebSocket Server (`server.py`)

Relays events between frontend and Nova Sonic:
- Frontend → Backend: session setup events + audio chunks
- Backend → Frontend: text output + audio output + usage events

---

## 🎯 Supported Voice Commands

| Domain | Example Commands |
|---|---|
| **EC2** | "List all EC2 instances", "Start instance i-abc123", "What instances are stopped?" |
| **SSM** | "Run a command on my instance", "Check patch compliance" |
| **Backup** | "List backup jobs", "What's in my backup vault?" |

---

## 🐛 Troubleshooting

### "ExpiredTokenException" in backend logs
```bash
# Re-authenticate
rm -rf ~/.aws/sso/cache/*
aws sso login --profile default
eval $(aws configure export-credentials --format env)
# Restart backend
```

### No audio input detected (Events panel shows no audioInput)
- Check Chrome mic permissions: `chrome://settings/content/microphone`
- Must access via `http://localhost:3001` (not an IP address) for mic access
- Or add the IP to Chrome's secure origins: `chrome://flags/#unsafely-treat-insecure-origin-as-secure`

### WebSocket connection failed
- Backend must bind to `0.0.0.0` (not `localhost`) for WSL→Windows access
- Use `--host 0.0.0.0` flag
- WebSocket URL in frontend must use WSL IP (not `localhost` for port 8080)

### "Role is required" error from Nova Sonic
- The `contentStart` event for audio must include `"role": "USER"`
- Already fixed in this fork

### CRT InvalidStateError on End Conversation
- Cosmetic error from `awscrt` library when stream closes
- Does not affect functionality — ignore it

### Frontend build fails (ESLint)
- Use `DISABLE_ESLINT_PLUGIN=true` when starting
- Already removed `react-app/jest` from eslintConfig

### npm install fails (symlinks)
- Must install in Linux filesystem, not NTFS (`~/nova-voice-frontend/`)
- WSL2 NTFS mounts don't support symlinks

---

## 💰 Cost Estimate

| Usage Level | Conversations/week | Monthly Cost |
|---|---|---|
| Light (dev/testing) | ~50 | $8-15 |
| Moderate | ~200 | $25-45 |
| Heavy | ~500+ | $60-100+ |

Costs are primarily Nova Sonic tokens (speech I/O) + Claude 3 Haiku (agent reasoning).

---

## 🔄 Fixes Applied (vs original aws-samples)

1. **SDK v0.11.0 migration**: `BedrockRuntimeClient` → `AsyncBedrockRuntimeClient`, `Config` → `await AsyncBedrockRuntimeConfig.resolve()`, added `AWSCRTHTTPClient` transport for duplex streaming
2. **ESLint**: Removed `react-app/jest` (incompatible with newer eslint-plugin-jest)
3. **crypto.randomUUID**: Added fallback for non-secure HTTP contexts
4. **WebSocket host**: Backend binds `0.0.0.0` for WSL-to-Windows access
5. **WebSocket URL**: Frontend defaults to WSL IP instead of localhost
6. **Stream close**: Suppressed cosmetic CRT InvalidStateError

---

## 📝 Next Steps

- [ ] Replace EC2/SSM/Backup agents with custom MCP-connected agents
- [ ] Connect to Notion, GitHub, Memory via Strands tools
- [ ] Test French/Arabic voice support
- [ ] Evaluate latency for real-time conversation
- [ ] Add conversation persistence

---

## 📄 License

MIT-0 (inherited from aws-samples)
