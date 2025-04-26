from fasthtml.common import *
from monsterui.all import *
import os
from dotenv import load_dotenv
import httpx
import json
import time 

# Create FastHTML app with WebSocket extension
app, rt = fast_app(exts='ws', hdrs=Theme.zinc.headers())

# Load environment variables
load_dotenv()

# Restack configuration
restack_api_endpoint = os.environ.get("RESTACK_API_ENDPOINT", "http://localhost:6233")
room_name = os.environ.get("ROOM_NAME", "heirloom-stories")

# Main UI components
def create_chat_ui(messages=None):
    if messages is None: messages = []
    return Div(
        *[ChatMessage(msg["role"], msg["content"]) for msg in messages],
        id="chat-messages",
        cls=("pt-16", "pb-24")
    )

def ChatMessage(role, content):
    colors = dict(user=dict(bg="bg-blue-500", text="text-white"), 
                  assistant=dict(bg="bg-gray-200", text="text-gray-800"))
    style = colors.get(role, colors["assistant"])
    align = "justify-end" if role == "user" else "justify-start"
    
    return Div(cls=f'flex {align} mb-4')(
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
    # Get LiveKit credentials for direct connection
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
    
    return Container(
        create_navbar(),
        Div(
            create_chat_ui(), 
            id="chat-container",
            hx_ext="ws",
            ws_connect="/ws"
        ),
        Div(
            Div(id="status", cls="text-center mb-2"),
            DivHStacked(
                Button(
                    "Start Agent", 
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
                cls="flex justify-center gap-4"
            ),
            cls="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-800 border-t p-4 flex flex-col justify-center"
        ),
        # Add LiveKit client library
        Script(src="https://cdn.jsdelivr.net/npm/livekit-client/dist/livekit-client.umd.min.js"),
        # Add direct connection script
        Script(f"""
        let currentRoom;
        
        async function connectToLiveKit() {{
            console.log('Connect to LiveKit function called');
            
            try {{
                if (!window.LivekitClient) {{
                    console.error('LiveKit client not available');
                    document.getElementById('status').innerHTML = 
                        '<div class="text-red-500">Error: LiveKit client not available</div>';
                    return;
                }}
                
                console.log('Creating room...');
                const room = new LivekitClient.Room();
                
                // Set up event listeners
                room.on('connected', () => {{
                    console.log('Connected to room:', room.name);
                    document.getElementById('status').innerHTML = 
                        `<div class="text-green-500">Connected to room: ${{room.name}}</div>`;
                }});
                
                room.on('disconnected', () => {{
                    console.log('Disconnected from room');
                    document.getElementById('status').innerHTML = 
                        '<div class="text-red-500">Disconnected from room</div>';
                }});
                
                room.on('participantConnected', (participant) => {{
                    console.log('Participant connected:', participant.identity);
                    document.getElementById('status').innerHTML += 
                        `<div>Participant joined: ${{participant.identity}}</div>`;
                }});
                
                room.on('trackSubscribed', (track, publication, participant) => {{
                    console.log('Track subscribed:', track.kind, 'from', participant.identity);
                    if (track.kind === 'audio') {{
                        console.log('Attaching audio track');
                        const audioEl = new Audio();
                        track.attach(audioEl);
                        audioEl.volume = 1.0;
                        document.body.appendChild(audioEl);
                        console.log('Audio track attached');
                    }}
                }});
                
                // Connect to room
                console.log('Connecting to room...');
                console.log('URL:', '{livekit_url}');
                console.log('Token (first 20 chars):', '{jwt[:20]}...');
                
                await room.connect('{livekit_url}', '{jwt}');
                console.log('Connected successfully');
                
                // Store room for later use
                currentRoom = room;
                
                // Enable microphone
                await room.localParticipant.setMicrophoneEnabled(true);
                console.log('Microphone enabled');
                
                // Update button
                document.getElementById('join-button').innerText = 'Connected';
                document.getElementById('join-button').disabled = true;
                
            }} catch (error) {{
                console.error('Error connecting to LiveKit:', error);
                document.getElementById('status').innerHTML = 
                    `<div class="text-red-500">Error: ${{error.message}}</div>`;
            }}
        }}
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
        print(f"Starting agent with room_id: {room_name}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{restack_api_endpoint}/api/agents/AgentVoice", 
                json={"room_id": room_name}
            )
            agent_data = response.json()
            print(f"Agent response: {agent_data}")
            
            return Div(
                Div(f"Agent active - Room: {room_name}", 
                    id="status", cls="text-center mb-2 text-green-500 text-sm"),
                Div("Speak now - the assistant is listening...", 
                    cls="text-center mb-4 text-gray-700"),
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


@app.ws('/ws')
async def ws(msg:str, send):
    print(f"WebSocket message received: {msg}")
    
    # Send an immediate response to confirm WebSocket is working
    await send(Div(f"WebSocket received: {msg}", id="status", cls="text-xs text-blue-500"))
    try:
        # Try to parse as JSON in case we're receiving structured data
        data = json.loads(msg)
        if "transcript" in data:
            messages = [dict(role="user", content=data["transcript"])]
            await send(create_chat_ui(messages))
        elif "response" in data:
            messages = [dict(role="assistant", content=data["response"])]
            await send(create_chat_ui(messages))
    except json.JSONDecodeError:
        # Handle plain text messages
        if msg == "agent_started":
            await send(Div("Connected to voice agent", id="status", cls="text-green-500"))
        elif msg.startswith("transcript:"):
            transcript = msg.split(":", 1)[1]
            messages = [dict(role="user", content=transcript)]
            await send(create_chat_ui(messages))
        elif msg.startswith("response:"):
            response = msg.split(":", 1)[1]
            messages = [dict(role="assistant", content=response)]
            await send(create_chat_ui(messages))

# Run the app
serve()
