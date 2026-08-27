import asyncio
import json
import base64
import warnings
import uuid
from .s2s_events import S2sEvent
import time
from aws_sdk_bedrock_runtime.config import AsyncBedrockRuntimeConfig
from aws_sdk_bedrock_runtime.client import AsyncBedrockRuntimeClient, InvokeModelWithBidirectionalStreamOperationInput
from aws_sdk_bedrock_runtime.models import InvokeModelWithBidirectionalStreamInputChunk, BidirectionalInputPayloadPart
from smithy_http.aio.crt import AWSCRTHTTPClient
from .supervisor_agent_integration import SupervisorAgentIntegration

# Suppress warnings
warnings.filterwarnings("ignore")

# Suppress CRT InvalidStateError on stream close (cosmetic, not a real error)
import logging
logging.getLogger("awscrt").setLevel(logging.CRITICAL)
logger = logging.getLogger("S2sSessionManager")

DEBUG = False

# Session refresh config
SESSION_REFRESH_INTERVAL = 270  # 4.5 minutes (well before 8-min timeout)
MAX_HISTORY_MESSAGES = 10  # Keep last N exchanges for context


def debug_print(message):
    """Print only if debug mode is enabled"""
    if DEBUG:
        print(message)


class S2sSessionManager:
    """S2S Session Manager with automatic session refresh to avoid 8-min timeout."""
    
    def __init__(self, model_id='amazon.nova-2-sonic-v1:0', region='us-east-1', config=None):
        """Initialize the stream manager."""
        self.model_id = model_id
        self.region = region
        self.config = config
        
        # Audio and output queues
        self.audio_input_queue = asyncio.Queue()
        self.output_queue = asyncio.Queue()
        
        self.response_task = None
        self.audio_task = None
        self.refresh_task = None
        self.stream = None
        self.is_active = False
        self.bedrock_client = None
        self._refreshing = False  # Lock to prevent audio during refresh
        
        # Session information
        self.prompt_name = None
        self.content_name = None
        self.audio_content_name = None
        self.toolUseContent = ""
        self.toolUseId = ""
        self.toolName = ""
        
        # Session refresh state
        self.session_start_time = None
        self.conversation_history = []  # [{role: "user"|"assistant", text: "..."}]
        self.system_prompt = None  # Stored from initial setup
        self.audio_output_config = None  # Stored from initial promptStart
        self.tool_config = None  # Stored from initial promptStart
        
        # Initialize the Supervisor Agent integration
        self.supervisor_agent = SupervisorAgentIntegration(config)

    async def initialize_stream(self):
        """Initialize the bidirectional stream with Bedrock."""
        try:
            if not self.bedrock_client:
                config = await AsyncBedrockRuntimeConfig.resolve(
                    region=self.region,
                    transport=AWSCRTHTTPClient()
                )
                self.bedrock_client = AsyncBedrockRuntimeClient(config=config)
        except Exception as ex:
            self.is_active = False
            print(f"Failed to initialize Bedrock client: {str(ex)}")
            raise

        try:
            self.stream = await self.bedrock_client.invoke_model_with_bidirectional_stream(
                InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
            )
            self.is_active = True
            self.session_start_time = time.time()
            
            # Start listening for responses
            self.response_task = asyncio.create_task(self._process_responses())

            # Start processing audio input
            self.audio_task = asyncio.create_task(self._process_audio_input())
            
            # Start session refresh timer
            self.refresh_task = asyncio.create_task(self._session_refresh_timer())
            
            await asyncio.sleep(0.1)
            
            logger.info(f"Stream initialized (refresh in {SESSION_REFRESH_INTERVAL}s)")
            return self
        except Exception as e:
            self.is_active = False
            print(f"Failed to initialize stream: {str(e)}")
            raise
    
    async def _session_refresh_timer(self):
        """Timer that triggers session refresh before the 8-min timeout."""
        try:
            while self.is_active:
                await asyncio.sleep(SESSION_REFRESH_INTERVAL)
                if self.is_active and not self._refreshing:
                    logger.info("Session refresh triggered (preventing timeout)")
                    await self._refresh_session()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Session refresh timer error: {e}")

    async def _refresh_session(self):
        """Refresh the Nova Sonic session while maintaining conversation context."""
        self._refreshing = True
        logger.info("Starting session refresh...")
        
        try:
            # 1. Close the current stream gracefully
            old_stream = self.stream
            
            # Cancel response task
            if self.response_task and not self.response_task.done():
                self.response_task.cancel()
                try:
                    await self.response_task
                except asyncio.CancelledError:
                    pass
            
            # Send sessionEnd and close
            try:
                await self.send_raw_event(S2sEvent.session_end())
                await asyncio.sleep(0.2)
                await old_stream.input_stream.close()
            except Exception:
                pass
            
            # 2. Open a new stream
            self.stream = await self.bedrock_client.invoke_model_with_bidirectional_stream(
                InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
            )
            self.session_start_time = time.time()
            
            # 3. Restart response processor
            self.response_task = asyncio.create_task(self._process_responses())
            
            # 4. Re-send session setup with conversation history
            await self._resend_session_setup()
            
            logger.info(f"Session refreshed successfully ({len(self.conversation_history)} history messages preserved)")
            
        except Exception as e:
            logger.error(f"Session refresh failed: {e}")
            # If refresh fails, mark as inactive — user will need to restart
            self.is_active = False
        finally:
            self._refreshing = False

    async def _resend_session_setup(self):
        """Re-send the session initialization events with conversation history."""
        pn = str(uuid.uuid4())
        tc = str(uuid.uuid4())
        ac = str(uuid.uuid4())
        
        # Update stored names
        self.prompt_name = pn
        self.audio_content_name = ac
        
        # SessionStart
        await self.send_raw_event(S2sEvent.session_start())
        
        # PromptStart (use stored config from initial setup)
        prompt_start = {
            "event": {
                "promptStart": {
                    "promptName": pn,
                    "textOutputConfiguration": {"mediaType": "text/plain"},
                    "audioOutputConfiguration": self.audio_output_config or S2sEvent.DEFAULT_AUDIO_OUTPUT_CONFIG,
                    "toolUseOutputConfiguration": {"mediaType": "application/json"},
                    "toolConfiguration": self.tool_config or S2sEvent.SUPERVISOR_TOOL_CONFIG,
                }
            }
        }
        await self.send_raw_event(prompt_start)
        
        # System prompt with conversation history appended
        history_text = self._build_history_context()
        full_prompt = (self.system_prompt or "You are a helpful assistant.") + history_text
        
        await self.send_raw_event(S2sEvent.content_start_text(pn, tc))
        await self.send_raw_event(S2sEvent.text_input(pn, tc, full_prompt))
        await self.send_raw_event(S2sEvent.content_end(pn, tc))
        
        # Audio contentStart (ready to receive audio again)
        audio_start = {
            "event": {
                "contentStart": {
                    "promptName": pn,
                    "contentName": ac,
                    "type": "AUDIO",
                    "interactive": True,
                    "role": "USER",
                    "audioInputConfiguration": S2sEvent.DEFAULT_AUDIO_INPUT_CONFIG,
                }
            }
        }
        await self.send_raw_event(audio_start)
        
        logger.info("Session setup re-sent with history context")

    def _build_history_context(self):
        """Build a conversation history summary for context injection."""
        if not self.conversation_history:
            return ""
        
        # Take last N messages
        recent = self.conversation_history[-MAX_HISTORY_MESSAGES:]
        
        history = "\n\n[CONVERSATION HISTORY - Previous exchanges in this session:]\n"
        for msg in recent:
            role = "User" if msg["role"] == "user" else "Assistant"
            # Truncate long messages
            text = msg["text"][:200] + "..." if len(msg["text"]) > 200 else msg["text"]
            history += f"{role}: {text}\n"
        history += "[END OF HISTORY - Continue the conversation naturally.]\n"
        
        return history

    async def send_raw_event(self, event_data):
        """Send a raw event to the Bedrock stream."""
        try:
            if not self.stream or not self.is_active:
                debug_print("Stream not initialized or closed")
                return
            
            event_json = json.dumps(event_data)
            event = InvokeModelWithBidirectionalStreamInputChunk(
                value=BidirectionalInputPayloadPart(bytes_=event_json.encode('utf-8'))
            )
            await self.stream.input_stream.send(event)

            # Capture session config for refresh
            if "event" in event_data:
                evt_keys = list(event_data["event"].keys())
                if evt_keys:
                    evt_type = evt_keys[0]
                    # Store system prompt
                    if evt_type == "textInput" and event_data["event"]["textInput"].get("content"):
                        if not self.system_prompt:
                            self.system_prompt = event_data["event"]["textInput"]["content"]
                    # Store audio output config and tool config
                    elif evt_type == "promptStart":
                        ps = event_data["event"]["promptStart"]
                        if "audioOutputConfiguration" in ps:
                            self.audio_output_config = ps["audioOutputConfiguration"]
                        if "toolConfiguration" in ps:
                            self.tool_config = ps["toolConfiguration"]

            # Close session (only on explicit user end, not refresh)
            if "sessionEnd" in event_data.get("event", {}) and not self._refreshing:
                self.close()
            
        except Exception as e:
            debug_print(f"Error sending event: {str(e)}")
    
    async def _process_audio_input(self):
        """Process audio input from the queue and send to Bedrock."""
        while self.is_active:
            try:
                # Get audio data from the queue
                data = await self.audio_input_queue.get()
                
                # Skip audio during refresh (buffer will hold it)
                if self._refreshing:
                    continue
                
                # Extract data from the queue item
                prompt_name = data.get('prompt_name')
                content_name = data.get('content_name')
                audio_bytes = data.get('audio_bytes')
                
                if not audio_bytes or not prompt_name or not content_name:
                    debug_print("Missing required audio data properties")
                    continue

                # Use current prompt/content names (may have changed after refresh)
                actual_pn = self.prompt_name or prompt_name
                actual_cn = self.audio_content_name or content_name

                # Create the audio input event
                audio_event = S2sEvent.audio_input(actual_pn, actual_cn, audio_bytes.decode('utf-8') if isinstance(audio_bytes, bytes) else audio_bytes)
                
                # Send the event
                await self.send_raw_event(audio_event)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                debug_print(f"Error processing audio: {e}")
    
    def add_audio_chunk(self, prompt_name, content_name, audio_data):
        """Add an audio chunk to the queue."""
        self.audio_input_queue.put_nowait({
            'prompt_name': prompt_name,
            'content_name': content_name,
            'audio_bytes': audio_data
        })
    
    async def _process_responses(self):
        """Process incoming responses from Bedrock."""
        while self.is_active:
            try:            
                output = await self.stream.await_output()
                result = await output[1].receive()
                
                if result.value and result.value.bytes_:
                    response_data = result.value.bytes_.decode('utf-8')
                    
                    json_data = json.loads(response_data)
                    json_data["timestamp"] = int(time.time() * 1000)
                    
                    event_name = None
                    if 'event' in json_data:
                        event_name = list(json_data["event"].keys())[0]
                        
                        # Track conversation history (text outputs from assistant)
                        if event_name == 'textOutput':
                            content = json_data['event']['textOutput'].get('content', '')
                            role = json_data['event']['textOutput'].get('role', '')
                            if role == 'ASSISTANT' and content:
                                # Add to history (avoid duplicates for streaming chunks)
                                if not self.conversation_history or self.conversation_history[-1].get("text") != content:
                                    self.conversation_history.append({"role": "assistant", "text": content})
                        
                        # Handle tool use detection
                        if event_name == 'toolUse':
                            self.toolUseContent = json_data['event']['toolUse']
                            self.toolName = json_data['event']['toolUse']['toolName']
                            self.toolUseId = json_data['event']['toolUse']['toolUseId']
                            debug_print(f"Tool use detected: {self.toolName}, ID: {self.toolUseId}")

                        # Process tool use when content ends
                        elif event_name == 'contentEnd' and json_data['event'][event_name].get('type') == 'TOOL':
                            prompt_name = json_data['event']['contentEnd'].get("promptName")
                            debug_print("Processing tool use and sending result")
                            toolResult = await self.processToolUse(self.toolName, self.toolUseContent)
                                
                            # Send tool start event
                            toolContent = str(uuid.uuid4())
                            tool_start_event = S2sEvent.content_start_tool(prompt_name, toolContent, self.toolUseId)
                            await self.send_raw_event(tool_start_event)
                            
                            # Send tool result event
                            if isinstance(toolResult, dict):
                                content_json_string = json.dumps(toolResult)
                            else:
                                content_json_string = toolResult

                            tool_result_event = S2sEvent.text_input_tool(prompt_name, toolContent, content_json_string)
                            print("Tool result", tool_result_event)
                            await self.send_raw_event(tool_result_event)

                            # Send tool content end event
                            tool_content_end_event = S2sEvent.content_end(prompt_name, toolContent)
                            await self.send_raw_event(tool_content_end_event)
                    
                    # Put the response in the output queue for forwarding to frontend
                    await self.output_queue.put(json_data)

            except json.JSONDecodeError as ex:
                print(ex)
                await self.output_queue.put({"raw_data": response_data})
            except StopAsyncIteration as ex:
                print(ex)
                break
            except Exception as e:
                if "ValidationException" in str(e):
                    print(f"Validation error: {e}")
                elif "timed out" in str(e).lower():
                    logger.warning("Nova Sonic session timed out — should have been refreshed")
                else:
                    print(f"Error receiving response: {e}")
                break

        # Only mark inactive if not refreshing (refresh will restart the task)
        if not self._refreshing:
            self.is_active = False
            self.close()

    async def processToolUse(self, toolName, toolUseContent):
        """Process tool use with Supervisor Agent."""
        print(f"Tool Use Content: {toolUseContent}")

        toolName = toolName.lower()
        content, result = None, None
        try:
            if toolUseContent.get("content"):
                content = toolUseContent.get("content")
                print(f"Extracted query: {content}")
                
                # Track user query in history
                self.conversation_history.append({"role": "user", "text": content})
            
            if toolName == "supervisoragent":
                if isinstance(content, str):
                    try:
                        content_obj = json.loads(content)
                        if "query" in content_obj:
                            query = content_obj["query"]
                        else:
                            query = content
                    except:
                        query = content
                else:
                    query = str(content)
                
                result = await self.supervisor_agent.query(query)
                
                if not isinstance(result, str):
                    if hasattr(result, 'content'):
                        result = result.content
                    else:
                        result = str(result)
                
                if len(result) > 800:
                    result = result[:800] + "... (truncated for voice)"
                
                print(f"Supervisor agent result: {result[:100]}...")

            if not result:
                result = "I couldn't process that request."

            return {"result": result}
        except Exception as ex:
            print(f"Error in processToolUse: {ex}")
            return {"result": f"Sorry, I encountered an error: {str(ex)}"}
    
    def close(self):
        """Close the stream properly."""
        if not self.is_active:
            return
            
        self.is_active = False
        
        # Cancel all tasks
        for task in [self.response_task, self.audio_task, self.refresh_task]:
            if task and not task.done():
                task.cancel()
        
        # Close the stream
        if self.stream:
            try:
                asyncio.create_task(self._close_stream())
            except RuntimeError:
                pass

    async def _close_stream(self):
        """Gracefully close the Bedrock stream."""
        try:
            await self.stream.input_stream.close()
        except Exception:
            pass
