class S2sEvent {
  static DEFAULT_INFER_CONFIG = {
    maxTokens: 1024,
    topP: 0.95,
    temperature: 0.7
  };

  static DEFAULT_TURN_DETECTION_CONFIG = {
    endpointingSensitivity: "HIGH"  // HIGH=1.5s, MEDIUM=1.75s, LOW=2s
  };

  static DEFAULT_SYSTEM_PROMPT = "You are a helpful personal voice assistant with access to a powerful tool (supervisorAgent) connected to Notion, GitHub, bookmarks, memory, AWS documentation, the current time, and web fetch. Use the supervisorAgent tool when the user asks a question that requires looking up information. For simple greetings or casual conversation, respond directly without the tool. Keep responses concise and conversational — optimized for voice (2-3 sentences max). Respond in the same language the user speaks to you. When you use a tool, say a brief filler like 'Let me check that for you' before waiting.";

  static DEFAULT_AUDIO_INPUT_CONFIG = {
    mediaType: "audio/lpcm",
    sampleRateHertz: 16000,
    sampleSizeBits: 16,
    channelCount: 1,
    audioType: "SPEECH",
    encoding: "base64"
  };

  static DEFAULT_AUDIO_OUTPUT_CONFIG = {
    mediaType: "audio/lpcm",
    sampleRateHertz: 24000,
    sampleSizeBits: 16,
    channelCount: 1,
    voiceId: "matthew",
    encoding: "base64",
    audioType: "SPEECH"
  };

  static sessionStart(inferenceConfig = S2sEvent.DEFAULT_INFER_CONFIG) {
    return { event: { sessionStart: { 
      inferenceConfiguration: inferenceConfig,
      turnDetectionConfiguration: S2sEvent.DEFAULT_TURN_DETECTION_CONFIG
    } } };
  }

  static promptStart(promptName, audioOutputConfig = S2sEvent.DEFAULT_AUDIO_OUTPUT_CONFIG, toolConfig = null) {
    const config = {
      "event": {
        "promptStart": {
          "promptName": promptName,
          "textOutputConfiguration": {
            "mediaType": "text/plain"
          },
          "audioOutputConfiguration": audioOutputConfig
        }
      }
    };
    
    // Add tool configuration if provided
    if (toolConfig) {
      config.event.promptStart.toolUseOutputConfiguration = {
        "mediaType": "application/json"
      };
      config.event.promptStart.toolConfiguration = toolConfig;
    }
    
    return config;
  }

  static contentStartText(promptName, contentName, role="SYSTEM") {
    return {
      "event": {
        "contentStart": {
          "promptName": promptName,
          "contentName": contentName,
          "type": "TEXT",
          "interactive": true,
          "role": role,
          "textInputConfiguration": {
            "mediaType": "text/plain"
          }
        }
      }
    }
  }

  static textInput(promptName, contentName, systemPrompt = S2sEvent.DEFAULT_SYSTEM_PROMPT) {
    var evt = {
      "event": {
        "textInput": {
          "promptName": promptName,
          "contentName": contentName,
          "content": systemPrompt
        }
      }
    }
    return evt;
  }

  static contentEnd(promptName, contentName) {
    return {
      "event": {
        "contentEnd": {
          "promptName": promptName,
          "contentName": contentName
        }
      }
    }
  }

  static contentStartAudio(promptName, contentName, audioInputConfig = S2sEvent.DEFAULT_AUDIO_INPUT_CONFIG) {
    return {
      "event": {
        "contentStart": {
          "promptName": promptName,
          "contentName": contentName,
          "type": "AUDIO",
          "interactive": true,
          "role": "USER",
          "audioInputConfiguration": audioInputConfig
        }
      }
    }
  }

  static audioInput(promptName, contentName, content) {
    return {
      event: {
        audioInput: {
          promptName,
          contentName,
          content,
        }
      }
    };
  }

  static promptEnd(promptName) {
    return {
      event: {
        promptEnd: {
          promptName
        }
      }
    };
  }

  static sessionEnd() {
    return { event: { sessionEnd: {} } };
  }
}

export default S2sEvent;
