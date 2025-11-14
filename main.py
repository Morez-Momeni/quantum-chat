from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json
from typing import Dict

from users import users

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
        dead_usernames = []
        for username, conn in self.active_connections.items():
            if exclude and username == exclude:
                continue
            try:
                await conn.send_text(message)
            except Exception:  # شامل WebSocketDisconnect
                dead_usernames.append(username)

        for username in dead_usernames:
            self.disconnect(username)

manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "friends": list(users.keys())})

@app.get("/login/{username}", response_class=HTMLResponse)
async def login_page(request: Request, username: str):
    if username not in users:
        return HTMLResponse("کاربر پیدا نشد!", status_code=404)
    return templates.TemplateResponse("login.html", {"request": request, "username": username})

@app.post("/login/{username}")
async def login(username: str, password: str = Form()):
    if username in users and users[username]["password"] == password:
        return {"success": True, "username": username}
    return {"success": False, "error": "رمز اشتباه است!"}

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await manager.connect(username, websocket)

    await manager.broadcast(json.dumps({
        "type": "join",
        "username": username
    }), exclude=username)

    try:
        while True:
            data = await websocket.receive_text()

            if data.strip().startswith('{"type":"typing"'):
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "typing":
                        await manager.broadcast(json.dumps({
                            "type": "typing",
                            "username": username
                        }), exclude=username)
                        continue
                except:
                    pass

            await manager.broadcast(json.dumps({
                "type": "message",
                "sender": username,
                "text": data
            }))

    except WebSocketDisconnect:
        manager.disconnect(username)
        await manager.broadcast(json.dumps({
            "type": "leave",
            "username": username
        }), exclude=username)
