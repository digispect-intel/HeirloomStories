from fasthtml.common import *
from monsterui.all import *
import os
from dotenv import load_dotenv
import httpx
import json
import time 
from livekit import api, rtc
import asyncio

# Create FastHTML app with WebSocket extension
app, rt = fast_app(exts='ws', hdrs=Theme.zinc.headers())
if not hasattr(app, 'ws_clients'):
    app.ws_clients = []

# Load environment variables
load_dotenv()

# Restack configuration
restack_api_endpoint = os.environ.get("RESTACK_API_ENDPOINT", "http://localhost:6233")
room_name = os.environ.get("ROOM_NAME", "default")

async def connect_to_livekit_room():
    """Connect to the LiveKit room to receive transcripts."""
    print("Connecting to LiveKit room...")
    
    # Get credentials for LiveKit
    api_key = os.environ.get("LIVEKIT_API_KEY")
    api_secret = os.environ.get("LIVEKIT_API_SECRET")
    livekit_url = os.environ.get("LIVEKIT_URL")
    room_name = os.environ.get("ROOM_NAME", "default")
    
    if not api_key or not api_secret or not livekit_url:
        print("Missing LiveKit credentials in environment variables")
        return
    
    # Create token for connecting
    token = api.AccessToken(api_key, api_secret) \
        .with_identity("fasthtml-app") \
        .with_name("FastHTML App") \
        .with_grants(api.VideoGrants(
            room_join=True,
            room=room_name,
        ))
    
    jwt = token.to_jwt()
    
    # Create room and connect
    room = rtc.Room()
    
    # Set up event handlers for transcripts
    @room.on("data_received")
    def on_data_received(data, participant):
        try:
            # Decode and parse the data
            message = json.loads(data.decode('utf-8'))
            print(f"Received data from LiveKit: {message}")
            
            # Check if it's a transcript message
            if "type" in message and message["type"] == "transcript":
                speaker = "user" if participant.identity != "fasthtml-app" else "assistant"
                text = message.get("text", "")
                
                # Broadcast to WebSocket clients
                asyncio.create_task(broadcast_transcript(speaker, text))
        except Exception as e:
            print(f"Error processing LiveKit data: {e}")
    
    @room.on("participant_connected")
    def on_participant_connected(participant):
        print(f"Participant connected: {participant.identity}")
    
    # Connect to the room
    await room.connect(livekit_url, jwt)
    print(f"Connected to LiveKit room: {room_name}")
    
    # Keep the connection alive
    while True:
        await asyncio.sleep(1)

# Helper function to broadcast transcripts to WebSocket clients
async def broadcast_transcript(speaker, text):
    """Broadcast transcript to all connected WebSocket clients."""
    print(f"Broadcasting transcript - {speaker}: {text}")
    
    if not hasattr(app, 'ws_clients') or not app.ws_clients:
        print("No WebSocket clients connected")
        return
    
    for client in list(app.ws_clients):
        try:
            await client.send_json({
                "type": speaker,
                "message": text
            })
            print(f"Sent transcript to a WebSocket client")
        except Exception as e:
            print(f"Error sending to WebSocket client: {e}")
            if client in app.ws_clients:
                app.ws_clients.remove(client)

# Add this to your app startup code
@app.on_event("startup")
async def startup_event():
    # Start LiveKit connection in the background
    asyncio.create_task(connect_to_livekit_room())

def create_chat_ui():
    """Create a chat UI that displays the conversation transcript."""
    return Div(
        Div(
            Div("Conversation Transcript", cls="text-xl font-bold mb-4 text-center"),
            Div(id="chat-messages", cls="space-y-4 overflow-y-auto max-h-96 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg"),
            cls="w-full max-w-3xl mx-auto"
        ),
        id="conversation-container",
        cls="flex-1 overflow-hidden py-4"
    )

def user_message_html(text):
    """Generate HTML for a user message."""
    return f"""
    <div class="flex items-start mb-4">
        <div class="flex-shrink-0 mr-3">
            <div class="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-white">
                U
            </div>
        </div>
        <div class="bg-blue-100 dark:bg-blue-900 rounded-lg p-3 flex-1">
            <p class="text-sm text-gray-800 dark:text-gray-200">{text}</p>
        </div>
    </div>
    """

def assistant_message_html(text):
    """Generate HTML for an assistant message."""
    return f"""
    <div class="flex items-start mb-4 flex-row-reverse">
        <div class="flex-shrink-0 ml-3">
            <div class="w-8 h-8 rounded-full bg-purple-500 flex items-center justify-center text-white">
                A
            </div>
        </div>
        <div class="bg-purple-100 dark:bg-purple-900 rounded-lg p-3 flex-1">
            <p class="text-sm text-gray-800 dark:text-gray-200">{text}</p>
        </div>
    </div>
    """


# Main UI components
def create_chat_ui(messages=[]):
    return Div(
        Div(
            id="chat-messages",
            cls="pt-16 pb-24"
        ),
        Script("document.getElementById('chat-container').scrollTop = document.getElementById('chat-container').scrollHeight;"),
        id="chat-container",
        hx_ext="ws",
        ws_connect="/ws"

    )

def ChatMessage(role, content):
    """Creates a styled chat message bubble"""
    colors = {
        'system': {'bg': 'bg-gray-200', 'text': 'text-gray-800'},
        'user': {'bg': 'bg-blue-500', 'text': 'text-white'},
        'assistant': {'bg': 'bg-gray-200', 'text': 'text-gray-800'}
    }
    style = colors.get(role.lower(), colors['system'])
    
    align_cls = 'justify-end' if role.lower() == 'user' else 'justify-start'
    
    return Div(cls=f'flex {align_cls} mb-4')(
        Div(cls=f'{style["bg"]} {style["text"]} rounded-2xl p-4 max-w-[80%]')(
            Strong(role.capitalize(), cls='text-sm font-semibold tracking-wide'),
            Div(content, cls='mt-2')
        )
    )


def create_navbar():
    return NavBar(
        brand=H3("HeirloomStories AI Assistant"),
        sticky=True,
        cls="px-6 py-3 shadow-sm bg-background z-50 fixed top-0 left-0 right-0 w-full"
    )

def VoiceStatusIndicator(state="idle"):
    """
    Create a visual indicator for the current voice state.
    """
    state_styles = {
        "idle": "bg-gray-300 border-gray-400",
        "listening": "bg-green-500 border-green-600 animate-pulse",
        "processing": "bg-yellow-500 border-yellow-600",
        "speaking": "bg-blue-500 border-blue-600 animate-pulse"
    }
    
    state_labels = {
        "idle": "Ready",
        "listening": "Listening...",
        "processing": "Processing...",
        "speaking": "Speaking..."
    }
    
    style = state_styles.get(state, state_styles["idle"])
    label = state_labels.get(state, state_labels["idle"])
    
    return Div(
        Div(cls=f"w-6 h-6 rounded-full {style} mr-2"),
        Span(label, cls="text-lg font-medium"),
        cls="flex items-center justify-center p-4 rounded-lg border bg-white shadow-md fixed top-20 right-4 z-50",
        id="voice-status-indicator"
    )


@rt('/get_token', methods=['GET'])
async def get_token():
    try:
        from livekit import api
        
        # Get API key and secret from environment variables
        api_key = os.environ.get("LIVEKIT_API_KEY")
        api_secret = os.environ.get("LIVEKIT_API_SECRET")
        
        if not api_key or not api_secret:
            return {"error": "LiveKit API key or secret not set"}
        
        # Create the token
        token = api.AccessToken(api_key, api_secret) \
            .with_identity("user") \
            .with_name("User") \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
            ))
        
        jwt = token.to_jwt()
        
        return {
            "token": jwt,
            "room": room_name,
            "url": os.environ.get("LIVEKIT_URL", "wss://your-livekit-url.livekit.cloud")
        }
    except Exception as e:
        print(f"Error generating token: {e}")
        return {"error": str(e)}


@rt('/')
def homepage():
    return Container(
        create_navbar(),
        Div(
            # Add the voice status indicator at the top
            VoiceStatusIndicator(state="idle"),
            Div(
                Div("System: Connected to room. Waiting for conversation...", 
                    cls="flex justify-start mb-4"),
                id="chat-messages",
                cls="pt-16 pb-24 px-4"
            ),
            Script("document.getElementById('chat-container').scrollTop = document.getElementById('chat-container').scrollHeight;"),
            id="chat-container",
            cls="overflow-y-auto h-[calc(100vh-120px)]",
            hx_ext="ws",
            ws_connect="/ws"
        ),
        Div(
            Div(id="status", cls="text-center mb-2"),
            DivHStacked(
                Button(
                    "Start Conversation", 
                    id="start-button", 
                    cls=ButtonT.primary, 
                    hx_post="/start_agent", 
                    hx_swap="outerHTML"
                ),
                Button(
                    "Join Room", 
                    id="join-button", 
                    cls=ButtonT.secondary, 
                    onclick="connectToLiveKit()"
                ),
                Button(
                    "Test Voice States", 
                    id="test-voice-states", 
                    cls=ButtonT.secondary,
                    onclick="""
                    const states = ['idle', 'listening', 'processing', 'speaking'];
                    let index = 0;
                    
                    function cycleState() {
                        updateVoiceState(states[index]);
                        index = (index + 1) % states.length;
                    }
                    
                    // Cycle through states every 2 seconds
                    cycleState();
                    const interval = setInterval(cycleState, 2000);
                    
                    // Stop after cycling through all states
                    setTimeout(() => {
                        clearInterval(interval);
                        updateVoiceState('idle');
                    }, states.length * 2000);
                    """
                ),
                Button(
                    "Test Chat", 
                    id="test-chat", 
                    cls=ButtonT.secondary,
                    onclick="""
                    addMessageToTranscript('user', 'Hello! How can you help me with my project?');
                    setTimeout(() => {
                        addMessageToTranscript('assistant', 'I can help you with your project by providing information, suggestions, and answering your questions. What kind of project are you working on?');
                    }, 1000);
                    """
                ),
                cls="flex justify-center gap-4"
            ),
            cls="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-800 border-t p-4 flex flex-col justify-center"
        ),
        # Add LiveKit client library
        Script(src="https://cdn.jsdelivr.net/npm/livekit-client/dist/livekit-client.umd.min.js"),
        # Add connection script with voice state updates
        Script("""
        let currentRoom;
        let voiceState = "idle";
        let userSpeakingTimeout = null;
        let agentSpeakingTimeout = null;
        let stateChangeTimeout = null;
        let lastStateChange = Date.now();
        let transcriptMessages = [];
        let currentUserSpeech = '';
        let currentAgentSpeech = '';
        const MIN_STATE_DURATION = 800;
        let lastVoiceState = 'idle';
        let pendingUserMessage = '';
        let isProcessingVoiceState = false;

        // Function to add a message to the transcript
        function addMessageToTranscript(role, text) {
            if (!text || text.trim() === '') return;
            
            console.log(`Adding ${role} message to transcript: ${text}`);
            transcriptMessages.push({ role, text });
            
            const messagesContainer = document.getElementById('chat-messages');
            if (!messagesContainer) {
                console.error('Chat messages container not found');
                return;
            }
            
            // Use the same styling as the template
            const colors = {
                'system': {'bg': 'bg-gray-200', 'text': 'text-gray-800'},
                'user': {'bg': 'bg-blue-500', 'text': 'text-white'},
                'assistant': {'bg': 'bg-gray-200', 'text': 'text-gray-800'}
            };
            const style = colors[role] || colors['system'];
            const alignClass = role === 'user' ? 'justify-end' : 'justify-start';
            
            const messageHTML = `
            <div class="flex ${alignClass} mb-4">
                <div class="${style.bg} ${style.text} rounded-2xl p-4 max-w-[80%]">
                    <strong class="text-sm font-semibold tracking-wide">${role.charAt(0).toUpperCase() + role.slice(1)}</strong>
                    <div class="mt-2">${text}</div>
                </div>
            </div>
            `;
            
            messagesContainer.innerHTML += messageHTML;
            
            // Scroll to the bottom
            const container = document.getElementById('chat-container');
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        }

        function checkStateTransitions(newState) {
            console.log(`Checking state transition from ${lastVoiceState} to ${newState}`);
            
            // If transitioning from listening to processing, add user message
            if (lastVoiceState === 'listening' && newState === 'processing') {
                console.log('Transition detected: listening -> processing');
                // Generate a placeholder message if no transcript is available
                if (!currentUserSpeech || currentUserSpeech.trim() === '') {
                    currentUserSpeech = "I'm speaking to the AI assistant...";
                }
                addMessageToTranscript('user', currentUserSpeech);
                currentUserSpeech = '';
            }
            
            // If transitioning from speaking to idle, add assistant message
            if (lastVoiceState === 'speaking' && newState === 'idle') {
                console.log('Transition detected: speaking -> idle');
                // Generate a placeholder message if no transcript is available
                if (!currentAgentSpeech || currentAgentSpeech.trim() === '') {
                    currentAgentSpeech = "I've processed your request and provided a response.";
                }
                addMessageToTranscript('assistant', currentAgentSpeech);
                currentAgentSpeech = '';
            }
            
            lastVoiceState = newState;
        }

        // Function to update the voice state indicator
        function updateVoiceState(newState) {
            // Skip processing state entirely
            if (newState === 'processing') {
                newState = 'idle';
            }
            
            // Skip if same state
            if (newState === voiceState) return;
            
            console.log(`Updating voice state: ${voiceState} -> ${newState}`);
            voiceState = newState;
            
            const indicator = document.getElementById('voice-status-indicator');
            if (!indicator) {
                console.error('Voice status indicator not found');
                return;
            }
            
            // Update the indicator with new state
            let color, label, animation = '';
            
            switch (newState) {
                case 'idle':
                    color = 'bg-gray-300';
                    label = 'Ready';
                    break;
                case 'listening':
                    color = 'bg-green-500';
                    label = 'Listening...';
                    animation = 'animate-pulse';
                    break;
                case 'speaking':
                    color = 'bg-blue-500';
                    label = 'Speaking...';
                    animation = 'animate-pulse';
                    break;
            }
            
            // Create HTML for the indicator
            indicator.innerHTML = `
                <div class="w-6 h-6 rounded-full ${color} ${animation} mr-2"></div>
                <span class="text-lg font-medium">${label}</span>
            `;
        }

        // Enhanced WebSocket setup with detailed logging
        function setupWebSocket() {
            console.log("[JS] Setting up WebSocket connection");
            
            const ws = new WebSocket(`ws://${window.location.host}/ws`);
            
            ws.onopen = function(event) {
                console.log("[JS] WebSocket connection established");
            };
            
            ws.onmessage = function(event) {
                console.log("[JS] Raw WebSocket message received:", event.data);
                
                try {
                    const data = JSON.parse(event.data);
                    console.log("[JS] Parsed WebSocket message:", data);
                    
                    if (data.type === "user") {
                        console.log("[JS] Adding user message to transcript:", data.message);
                        addMessageToTranscript('user', data.message);
                    } else if (data.type === "assistant") {
                        console.log("[JS] Adding assistant message to transcript:", data.message);
                        addMessageToTranscript('assistant', data.message);
                    } else if (data.type === "system") {
                        console.log("[JS] System message:", data.message);
                    } else {
                        console.log("[JS] Unknown message type:", data.type);
                    }
                } catch (e) {
                    console.error("[JS] Error processing WebSocket message:", e);
                    console.error("[JS] Raw message was:", event.data);
                }
            };
            
            ws.onclose = function(event) {
                console.log("[JS] WebSocket connection closed with code:", event.code);
                console.log("[JS] Close reason:", event.reason);
                // Attempt to reconnect after a delay
                console.log("[JS] Will attempt to reconnect in 5 seconds");
                setTimeout(setupWebSocket, 5000);
            };
            
            ws.onerror = function(event) {
                console.error("[JS] WebSocket error:", event);
            };
            
            // Store the WebSocket connection for later use
            window.chatWs = ws;
            console.log("[JS] WebSocket setup complete");
        }

        // Enhanced addMessageToTranscript function with logging
        function addMessageToTranscript(role, text) {
            console.log(`[JS] Adding ${role} message to transcript: ${text}`);
            
            if (!text || text.trim() === '') {
                console.log("[JS] Empty message, not adding to transcript");
                return;
            }
            
            const messagesContainer = document.getElementById('chat-messages');
            if (!messagesContainer) {
                console.error("[JS] Chat messages container not found");
                return;
            }
            
            console.log("[JS] Found messages container, adding message");
            
            // Use the same styling as the template
            const colors = {
                'system': {'bg': 'bg-gray-200', 'text': 'text-gray-800'},
                'user': {'bg': 'bg-blue-500', 'text': 'text-white'},
                'assistant': {'bg': 'bg-gray-200', 'text': 'text-gray-800'}
            };
            const style = colors[role] || colors['system'];
            const alignClass = role === 'user' ? 'justify-end' : 'justify-start';
            
            const messageHTML = `
            <div class="flex ${alignClass} mb-4">
                <div class="${style.bg} ${style.text} rounded-2xl p-4 max-w-[80%]">
                    <strong class="text-sm font-semibold tracking-wide">${role.charAt(0).toUpperCase() + role.slice(1)}</strong>
                    <div class="mt-2">${text}</div>
                </div>
            </div>
            `;
            
            messagesContainer.innerHTML += messageHTML;
            console.log("[JS] Added message to container");
            
            // Scroll to the bottom
            const container = document.getElementById('chat-container');
            if (container) {
                container.scrollTop = container.scrollHeight;
                console.log("[JS] Scrolled container to bottom");
            } else {
                console.warn("[JS] Chat container not found for scrolling");
            }
        }

        async function connectToLiveKit() {
            console.log('Connect to LiveKit function called');
            updateVoiceState('idle');
            
            try {
                if (!window.LivekitClient) {
                    console.error('LiveKit client not available');
                    document.getElementById('status').innerHTML = 
                        '<div class="text-red-500">Error: LiveKit client not available</div>';
                    return;
                }
                
                console.log('Creating room...');
                const room = new LivekitClient.Room();
                
                // Get token for the LiveKit room
                const response = await fetch('/get_token');
                const tokenData = await response.json();
                
                if (tokenData.error) {
                    throw new Error(tokenData.error);
                }
                
                console.log('Connecting to room...');
                console.log('URL:', tokenData.url);
                console.log('Token (first 20 chars):', tokenData.token.substring(0, 20) + '...');
                
                // Connect to room
                await room.connect(tokenData.url, tokenData.token);
                console.log('Connected to room:', room.name);
                document.getElementById('status').innerHTML = 
                    `<div class="text-green-500">Connected to room: ${room.name}</div>`;
                
                // Simple state transitions based on events
                
                // When local participant publishes audio (starts speaking)
                room.localParticipant.on('trackPublished', (publication) => {
                    if (publication.kind === 'audio') {
                        console.log('Local audio published');
                        updateVoiceState('listening');
                    }
                });
                
                // When a remote track is subscribed (agent speaking)
                room.on('trackSubscribed', (track, publication, participant) => {
                    console.log('Track subscribed:', track.kind, 'from', participant.identity);
                    
                    if (track.kind === 'audio' && participant.identity.includes('agent')) {
                        console.log('Agent audio track subscribed');
                        updateVoiceState('speaking');
                        
                        // Attach audio
                        const audioEl = new Audio();
                        track.attach(audioEl);
                        audioEl.volume = 1.0;
                        document.body.appendChild(audioEl);
                    }
                });
                
                // When a remote track is unsubscribed (agent stops speaking)
                room.on('trackUnsubscribed', (track, publication, participant) => {
                    if (track.kind === 'audio' && participant.identity.includes('agent')) {
                        console.log('Agent audio track unsubscribed');
                        updateVoiceState('idle');
                    }
                });
                
                // Monitor all participants for speaking
                room.on('activeSpeakersChanged', (speakers) => {
                    console.log('Active speakers changed:', speakers.map(p => p.identity || 'unknown'));
                    
                    // Simple detection logic
                    const agentSpeaking = speakers.some(p => 
                        p !== room.localParticipant && 
                        p.identity && 
                        p.identity.includes('agent')
                    );
                    
                    const userSpeaking = speakers.some(p => p === room.localParticipant);
                    
                    // Direct state updates based on who's speaking
                    if (agentSpeaking) {
                        updateVoiceState('speaking');
                    } else if (userSpeaking) {
                        updateVoiceState('listening');
                    } else {
                        // Go directly to idle when no one is speaking
                        updateVoiceState('idle');
                    }
                });

                function simulateDialogue() {
                    // Add a timer to periodically check voice state and generate messages
                    setInterval(() => {
                        if (voiceState === 'processing' && !document.querySelector('.user-message-added')) {
                            // Add a user message if we're in processing state and haven't added one yet
                            addMessageToTranscript('user', 'What can you tell me about this project?');
                            // Mark that we've added a user message
                            const marker = document.createElement('div');
                            marker.style.display = 'none';
                            marker.className = 'user-message-added';
                            document.body.appendChild(marker);
                            
                            // After a delay, add an assistant response
                            setTimeout(() => {
                                if (document.querySelector('.user-message-added')) {
                                    addMessageToTranscript('assistant', 'This project is a voice interface that uses LiveKit to enable real-time communication with an AI assistant. It captures audio, processes it, and generates responses.');
                                    document.querySelector('.user-message-added').remove();
                                }
                            }, 2000);
                        }
                    }, 5000);
                }


                // Enhanced debug for data events
                room.on('data', (data, participant) => {
                    console.log('Received data event from:', participant?.identity);
                    
                    try {
                        const message = JSON.parse(new TextDecoder().decode(data));
                        console.log('Parsed message:', message);
                        
                        // Check if it's a transcription message
                        if (message.type === 'transcription') {
                            console.log('Transcription message received:', message);
                            
                            if (participant === room.localParticipant) {
                                // User's speech
                                currentUserSpeech = message.text;
                                console.log('Updated user speech:', currentUserSpeech);
                            } else {
                                // Agent's speech
                                currentAgentSpeech = message.text;
                                console.log('Updated agent speech:', currentAgentSpeech);
                                

                                // Only add to transcript when complete
                                if (message.final) {
                                    console.log('Adding final agent message to transcript');
                                    addMessageToTranscript('assistant', currentAgentSpeech);
                                    currentAgentSpeech = '';
                                }
                            }
                        }
                    } catch (e) {
                        console.error('Error parsing data message:', e);
                    }
                });

                // Store room for later use
                currentRoom = room;
                
                // Enable microphone
                await room.localParticipant.setMicrophoneEnabled(true);
                console.log('Microphone enabled');
                
                // Update button
                document.getElementById('join-button').innerText = 'Connected';
                document.getElementById('join-button').disabled = true;

                room.localParticipant.on('isSpeakingChanged', (speaking) => {
                    console.log('Local participant speaking changed:', speaking);
                    if (speaking) {
                        updateVoiceState('listening');
                    } else {
                        // Go directly to idle when user stops speaking
                        updateVoiceState('idle');
                    }
                });

                // Listen for track enabled/disabled events
                room.on('trackSubscribed', (track, publication, participant) => {
                    console.log('Track subscribed:', track.kind, 'from', participant.identity);
                    
                    if (track.kind === 'audio' && participant.identity.includes('agent')) {
                        console.log('Agent audio track subscribed');
                        
                        // Listen for track mute/unmute
                        track.on('muted', () => {
                            console.log('Agent track muted');
                            updateVoiceState('idle');
                        });
                        
                        track.on('unmuted', () => {
                            console.log('Agent track unmuted');
                            updateVoiceState('speaking');
                        });
                        
                        // Attach audio
                        const audioEl = new Audio();
                        track.attach(audioEl);
                        audioEl.volume = 1.0;
                        document.body.appendChild(audioEl);
                    }
                });

            simulateDialogue();
            } catch (error) {
                console.error('Error connecting to LiveKit:', error);
                document.getElementById('status').innerHTML = 
                    `<div class="text-red-500">Error: ${error.message}</div>`;
                updateVoiceState('idle');
            }
        }

        // Add some simple test functions
        window.addUserMessage = (text) => addMessageToTranscript('user', text);
        window.addAssistantMessage = (text) => addMessageToTranscript('assistant', text);
        document.addEventListener('DOMContentLoaded', setupWebSocket);
        """
        ),
        # // Add this right after the LiveKit script tag
        Script("""
        // Debug voice state changes
        let voiceStateDebug = document.createElement('div');
        voiceStateDebug.id = 'voice-state-debug';
        voiceStateDebug.style.position = 'fixed';
        voiceStateDebug.style.top = '80px';
        voiceStateDebug.style.left = '10px';
        voiceStateDebug.style.background = 'rgba(0,0,0,0.7)';
        voiceStateDebug.style.color = 'white';
        voiceStateDebug.style.padding = '10px';
        voiceStateDebug.style.borderRadius = '5px';
        voiceStateDebug.style.zIndex = '1000';
        voiceStateDebug.style.maxHeight = '200px';
        voiceStateDebug.style.overflow = 'auto';
        voiceStateDebug.style.fontSize = '12px';
        document.body.appendChild(voiceStateDebug);

        function logVoiceState(message) {
            console.log(message);
            const entry = document.createElement('div');
            entry.textContent = new Date().toLocaleTimeString() + ': ' + message;
            voiceStateDebug.appendChild(entry);
            voiceStateDebug.scrollTop = voiceStateDebug.scrollHeight;
            
            // Limit entries
            while (voiceStateDebug.children.length > 20) {
                voiceStateDebug.removeChild(voiceStateDebug.firstChild);
            }
        }
        """)

    )


@rt('/htmx_test', methods=['GET'])
def htmx_test():
    print("HTMX test endpoint called")
    return Div("HTMX is working!", cls="text-green-500")

@rt('/join_room', methods=['POST'])
async def join_room():
    print("Join room endpoint called")
    
    try:
        # Get a token for the LiveKit room
        from livekit import api
        
        # Get API key and secret from environment variables
        api_key = os.environ.get("LIVEKIT_API_KEY")
        api_secret = os.environ.get("LIVEKIT_API_SECRET")
        livekit_url = os.environ.get("LIVEKIT_URL")
        
        # Create the token
        token = api.AccessToken(api_key, api_secret) \
            .with_identity("user") \
            .with_name("User") \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
            ))
        
        jwt = token.to_jwt()
        
        print(f"Generated token: {jwt[:20]}...")
        print(f"LiveKit URL: {livekit_url}")
        
        return Div(
            Div("Connecting to LiveKit...", id="status", cls="text-center mb-2 text-blue-500"),
            Button(
                "Connected", 
                id="join-button", 
                disabled=True,
                cls=ButtonT.primary,
            ),
            # Simple connection script
            Script(f"""
            console.log('Connect script running');
            
            if (window.LivekitClient) {{
                console.log('LiveKit client available');
                
                try {{
                    // Create room
                    const room = new LivekitClient.Room();
                    console.log('Room created');
                    
                    // Store in window for debugging
                    window.lkRoom = room;
                    
                    // Set up event listeners
                    room.on('connected', () => {{
                        console.log('Connected to LiveKit room:', room.name);
                        document.getElementById('status').innerHTML = 
                            `<div class="text-green-500">Connected to room: ${{room.name}}</div>`;
                    }});
                    
                    room.on('disconnected', () => {{
                        console.log('Disconnected from LiveKit room');
                    }});
                    
                    room.on('participantConnected', (participant) => {{
                        console.log('Participant connected:', participant.identity);
                    }});
                    
                    // Connect to room
                    console.log('Connecting to room with URL:', '{livekit_url}');
                    console.log('Token (first 20 chars):', '{jwt[:20]}...');
                    
                    room.connect('{livekit_url}', '{jwt}')
                        .then(() => {{
                            console.log('Connected successfully');
                            return room.localParticipant.setMicrophoneEnabled(true);
                        }})
                        .then(() => {{
                            console.log('Microphone enabled');
                        }})
                        .catch(error => {{
                            console.error('Connection error:', error);
                            document.getElementById('status').innerHTML = 
                                `<div class="text-red-500">Error: ${{error.message}}</div>`;
                        }});
                }} catch (error) {{
                    console.error('Script error:', error);
                }}
            }} else {{
                console.error('LiveKit client not available');
            }}
            """),
            hx_swap_oob="true"
        )
    except Exception as e:
        print(f"Error in join_room: {e}")
        return Div(f"Error: {str(e)}", cls="text-red-500", id="join-button")


@rt('/disconnect_room', methods=['POST'])
async def disconnect_room():
    return Div(
        Button(
            "Join Room", 
            id="join-button", 
            cls=ButtonT.secondary,
            hx_post="/join_room",
            hx_swap="outerHTML",
        ),
        Script("disconnectFromRoom();"),
        hx_swap_oob="true"
    )

@rt('/start_agent', methods=['POST'])
async def start_agent():
    try:

        async with httpx.AsyncClient() as client:
            response = await client.post(f"{restack_api_endpoint}/api/agents/AgentVoice", 
                                        json={"room_id": room_name})
            
            if response.status_code == 200:
                agent_data = response.json()
                print(f"Agent response: {agent_data}")
                
                # Store agent ID and run ID in global variables
                global agent_id, run_id
                agent_id = agent_data.get("agentId")
                run_id = agent_data.get("runId")
            
            return Div(
                Div(f"Agent started - Room: {room_name}", 
                    id="status", cls="text-center mb-2 text-green-500 text-sm"),
                Button(
                    "Agent Active", 
                    id="start-button", 
                    disabled=True,
                    cls=ButtonT.primary,
                ),
                hx_swap_oob="true"
            )
    except Exception as e:
        print(f"Error starting agent: {e}")
        return Div(f"Error: {str(e)}", cls="text-red-500", id="start-button")

@rt('/api/get_transcripts', methods=['GET'])
async def get_transcripts():
    """Get transcripts from the current conversation."""
    try:
        # Connect to Restack client
        restack_url = os.environ.get("RESTACK_ENGINE_API_ADDRESS", "http://localhost:9233")
        
        # Get transcripts from the agent
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{restack_url}/stream/agents/AgentVoice/{agent_id}/{run_id}")
            
            if response.status_code == 200:
                transcript_data = response.json()
                # Extract user and assistant messages
                messages = []
                
                for item in transcript_data.get("transcript", []):
                    if item.get("role") == "user":
                        messages.append({
                            "speaker": "user",
                            "text": item.get("content", "")
                        })
                    elif item.get("role") == "assistant":
                        messages.append({
                            "speaker": "assistant",
                            "text": item.get("content", "")
                        })
                
                return messages
            else:
                return []
    except Exception as e:
        print(f"Error getting transcripts: {e}")
        return []


@app.ws('/ws')
async def ws(ws):
    print("[WS] New WebSocket connection request")
    
    # Add this client to the global list
    app.ws_clients.append(ws)
    print(f"[WS] Client added to list. Total clients: {len(app.ws_clients)}")
    
    await ws.accept()
    print("[WS] WebSocket connection accepted")
    
    try:
        # Send initial message
        await ws.send_json({
            "type": "system",
            "message": "Connected to WebSocket. Waiting for conversation..."
        })
        print("[WS] Sent initial system message")
        
        # Send any existing transcripts
        if hasattr(app, 'transcripts') and app.transcripts:
            print(f"[WS] Sending {len(app.transcripts)} existing transcripts")
            for transcript in app.transcripts:
                await ws.send_json({
                    "type": transcript["speaker"],
                    "message": transcript["text"]
                })
                print(f"[WS] Sent transcript: {transcript['speaker']}: {transcript['text'][:30]}...")
        else:
            print("[WS] No existing transcripts to send")
        
        # Keep connection alive
        print("[WS] Entering keep-alive loop")
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        print(f"[WS] WebSocket error: {e}")
    finally:
        # Remove this client from the list
        if ws in app.ws_clients:
            app.ws_clients.remove(ws)
            print(f"[WS] Client removed from list. Remaining clients: {len(app.ws_clients)}")
        print("[WS] WebSocket connection closed")
        await ws.close()


@rt('/api/transcript', methods=['POST'])
async def receive_transcript(speaker: str, text: str):
    """Receive transcript from pipeline and broadcast to WebSocket clients."""
    print(f"[TRANSCRIPT API] Received transcript - {speaker}: {text}")
    
    # Store this transcript for later retrieval
    if not hasattr(app, 'transcripts'):
        app.transcripts = []
    
    app.transcripts.append({
        "speaker": speaker,
        "text": text,
        "timestamp": time.time()
    })
    
    print(f"[TRANSCRIPT API] Total stored transcripts: {len(app.transcripts)}")
    
    # Check if we have ws_clients attribute and if it has any clients
    if hasattr(app, 'ws_clients') and app.ws_clients:
        print(f"[TRANSCRIPT API] Broadcasting to {len(app.ws_clients)} WebSocket clients")
        for client in app.ws_clients:
            try:
                await client.send_json({
                    "type": speaker,
                    "message": text
                })
                print(f"[TRANSCRIPT API] Successfully sent to a WebSocket client")
            except Exception as e:
                print(f"[TRANSCRIPT API] Error sending to WebSocket: {e}")
                # If there was an error, try to remove the client
                if client in app.ws_clients:
                    app.ws_clients.remove(client)
    else:
        print("[TRANSCRIPT API] No WebSocket clients connected")
    
    return {"status": "success"}


@rt('/test_transcript')
def test_transcript():
    """Test page for transcript API."""
    return Container(
        H1("Transcript API Test"),
        P("Click the buttons below to simulate transcript messages:"),
        Button(
            "Send User Message", 
            cls=ButtonT.primary,
            onclick="""
            fetch('/api/transcript', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ speaker: 'user', text: 'This is a test user message from the test page.' })
            }).then(response => response.json())
              .then(data => console.log('API response:', data))
              .catch(error => console.error('Error:', error));
            """
        ),
        Button(
            "Send Assistant Message", 
            cls=ButtonT.secondary,
            onclick="""
            fetch('/api/transcript', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ speaker: 'assistant', text: 'This is a test assistant message from the test page.' })
            }).then(response => response.json())
              .then(data => console.log('API response:', data))
              .catch(error => console.error('Error:', error));
            """
        ),
        Div(id="result")
    )

@rt('/test_ws')
def test_ws():
    """Test page for WebSocket connections."""
    return Container(
        H1("WebSocket Test"),
        P("This page tests WebSocket connections and transcript display."),
        Div(id="chat-messages", cls="space-y-4 overflow-y-auto h-64 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg"),
        P("Connected clients: ", Strong(str(len(getattr(app, 'ws_clients', [])))), id="client-count"),
        Button(
            "Refresh Count", 
            cls=ButtonT.primary,
            hx_get="/ws_client_count",
            hx_target="#client-count",
            hx_trigger="click"
        ),
        Button(
            "Send Test Message", 
            cls=ButtonT.secondary,
            onclick="""
            fetch('/api/transcript', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    speaker: 'assistant', 
                    text: 'This is a test message sent at ' + new Date().toLocaleTimeString() 
                })
            });
            """
        ),
        Script("""
        // Setup WebSocket
        const ws = new WebSocket(`ws://${window.location.host}/ws`);
        
        ws.onopen = function(event) {
            console.log("WebSocket connection established");
            document.getElementById('client-count').innerHTML = 
                "Connected clients: <strong>Connected</strong>";
        };
        
        ws.onmessage = function(event) {
            console.log("WebSocket message received:", event.data);
            
            try {
                const data = JSON.parse(event.data);
                
                const messagesContainer = document.getElementById('chat-messages');
                const messageHTML = `
                <div class="p-2 mb-2 ${data.type === 'user' ? 'bg-blue-100' : 'bg-green-100'} rounded">
                    <strong>${data.type}:</strong> ${data.message}
                </div>
                `;
                messagesContainer.innerHTML += messageHTML;
            } catch (e) {
                console.error("Error processing message:", e);
            }
        };
        
        ws.onclose = function(event) {
            console.log("WebSocket connection closed");
            document.getElementById('client-count').innerHTML = 
                "Connected clients: <strong>Disconnected</strong>";
        };
        """)
    )

@rt('/ws_client_count')
def ws_client_count():
    """Get the current WebSocket client count."""
    return P("Connected clients: ", Strong(str(len(getattr(app, 'ws_clients', [])))))

# Run the app
serve()
