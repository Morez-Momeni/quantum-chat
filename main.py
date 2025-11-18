from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
from typing import Dict

from users import users  # فرض: users.py وجود داره

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, username: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[username] = websocket

    def disconnect(self, username: str):
        self.active_connections.pop(username, None)

    async def broadcast(self, message: str, exclude: str = None):
        dead = []
        for username, conn in self.active_connections.items():
            if exclude and username == exclude: continue
            try:
                await conn.send_text(message)
            except:
                dead.append(username)
        for u in dead:
            self.disconnect(u)

manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "friends": list(users.keys())})

@app.get("/login/{username}", response_class=HTMLResponse)
async def login_page(request: Request, username: str):
    # فیلتر در سرور
    clean_username = ''.join(c for c in username if c.isalnum() or c in 'آابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی ')
    clean_username = clean_username.strip()
    if not clean_username or clean_username not in users:
        return HTMLResponse("کاربر پیدا نشد!", status_code=404)
    return templates.TemplateResponse("login.html", {"request": request, "username": clean_username})

@app.post("/login/{username}")
async def login(username: str, password: str = Form()):
    clean_username = ''.join(c for c in username if c.isalnum() or c in 'آابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی ')
    clean_username = clean_username.strip()
    if clean_username in users and users[clean_username]["password"] == password:
        return {"success": True}
    return {"success": False, "error": "رمز اشتباه است!"}

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    # فیلتر نهایی
    clean_username = ''.join(c for c in username if c.isalnum() or c in 'آابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی ')
    clean_username = clean_username.strip()
    if not clean_username or clean_username not in users:
        await websocket.close(code=1008, reason="Invalid username")
        return

    await manager.connect(clean_username, websocket)
    await manager.broadcast(json.dumps({"type": "join", "username": clean_username}), exclude=clean_username)

    try:
        while True:
            data = await websocket.receive_text()

            if data.strip() == '{"type":"ping"}':
                await websocket.send_text('{"type":"pong"}')
                continue

            if data.strip().startswith('{"type":"typing"'):
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "typing":
                        await manager.broadcast(json.dumps({"type": "typing", "username": clean_username}), exclude=clean_username)
                        continue
                except: pass

            await manager.broadcast(json.dumps({
                "type": "message",
                "sender": clean_username,
                "text": data
            }))
    except WebSocketDisconnect:
        manager.disconnect(clean_username)
        await manager.broadcast(json.dumps({"type": "leave", "username": clean_username}), exclude=clean_username)



voice_manager = ConnectionManager()

@app.get("/voice", response_class=HTMLResponse)
async def voice_room(request: Request):
    return templates.TemplateResponse("voice.html", {"request": request})

@app.websocket("/voice-ws/{username}")
async def voice_websocket(websocket: WebSocket, username: str):
    clean_username = ''.join(c for c in username if c.isalnum() or c in 'آابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی ')
    clean_username = clean_username.strip()
    if not clean_username or clean_username not in users:
        await websocket.close(code=1008, reason="Invalid username")
        return

    await voice_manager.connect(clean_username, websocket)

    await voice_manager.broadcast(json.dumps({
        "type": "users",
        "users": list(voice_manager.active_connections.keys())
    }))

    for other_username in voice_manager.active_connections:
        if other_username != clean_username:
            await voice_manager.active_connections[other_username].send_text(json.dumps({
                "type": "new-user",
                "username": clean_username
            }))

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

           
            if msg.get("type") == "joined":
                for other_username in voice_manager.active_connections:
                    if other_username != clean_username:
                        await voice_manager.active_connections[other_username].send_text(json.dumps({
                            "type": "new-user",
                            "username": clean_username
                        }))


            elif msg["type"] in ["offer", "answer", "ice"]:
                target = msg.get("target")
                if target and target in voice_manager.active_connections:
                    await voice_manager.active_connections[target].send_text(json.dumps({
                        **msg,
                        "from": clean_username
                    }))

    except WebSocketDisconnect:
        voice_manager.disconnect(clean_username)
        await voice_manager.broadcast(json.dumps({
            "type": "users",
            "users": list(voice_manager.active_connections.keys())
        }))

