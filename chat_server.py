from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import asyncio
import time
import hashlib
import requests
import datetime
import os

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

message_history = []  # List to store JSON messages
online_users = {}


def send_to_discord(message_data):
    """
    Sends a message to a Discord webhook as an embed.
    """
    if message_data.get("message", "").startswith("::banner{") and message_data.get("message", "").endswith("}"):
        embed = {
            "description": message_data.get("message", "").replace("::banner{", "").replace("}", ""),
            "color": 5814783,  # You can change the color as needed
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }
    else:
        embed = {
            "title": message_data.get("username", "Anonymous"),
            "description": message_data.get("message", ""),
            "color": 5814783,  # You can change the color as needed
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }
    payload = {"embeds": [embed]}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        # Discord webhooks respond with 204 on success
        if response.status_code not in (200, 204):
            print(f"Failed to send webhook: {response.status_code} - {response.text}")
    except Exception as e:
        print("Error sending webhook:", e)


async def clear_history_periodically():
    while True:
        await asyncio.sleep(3600)  # 3600 seconds = 1 hour
        message_history.clear()
        system_message = {"username": "System", "message": "Chat history cleared."}
        message_history.append(system_message)
        print("Chat history cleared.")
        send_to_discord(system_message)


def generate_fingerprint(client_ip, headers):
    """Generate a simple fingerprint using IP, User-Agent, Accept-Language, and a supplied fingerprint."""
    user_agent = headers.get("User-Agent", "")
    accept_language = headers.get("Accept-Language", "")
    supplied_fingerprint = headers.get("X-Fingerprint", "")

    # Concatenate device attributes
    fingerprint_data = (
        f"{client_ip}|{user_agent}|{accept_language}|{supplied_fingerprint}"
    )

    # Hash it for uniqueness
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()


class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):

    def _set_response(self, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _set_response_html(self, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-type", "text/html")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        global online_users

        if self.path == "/messages":
            fingerprint = generate_fingerprint(self.client_address[0], self.headers)
            if "X-Fingerprint" in self.headers:
                online_users[fingerprint] = {
                    "time": time.time(),
                    "ip": self.client_address[0],
                }

            self._set_response()
            self.wfile.write(json.dumps(message_history).encode("utf-8"))

        elif self.path == "/online":
            current_time = time.time()
            # Remove users who haven't sent a request in the last 60 seconds
            active_users = {
                fp: user
                for fp, user in online_users.items()
                if current_time - user["time"] < 60
            }
            online_users.clear()
            online_users.update(active_users)

            # Remove duplicates (if any)
            online_users = {
                fp: user
                for fp, user in online_users.items()
                if fp not in online_users.values()
            }

            self._set_response()
            self.wfile.write(json.dumps({"online": len(online_users)}).encode("utf-8"))
        elif self.path == "/debug/fp":
            fingerprint = generate_fingerprint(self.client_address[0], self.headers)
            self._set_response_html()
            self.wfile.write(
                f"<pre>Your fingerprint: {fingerprint}</pre><pre>Online users: {online_users}</pre>".encode(
                    "utf-8"
                )
            )
        else:
            self._set_response(404)
            self.wfile.write(b"Not Found")

    def do_POST(self):
        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length)
        try:
            data = json.loads(post_data)
            username = data.get("username", "Anonymous")
            chat_message = data.get("message", "")

            message_data = {
                "username": username,
                "message": chat_message,
            }
            message_history.append(message_data)
            send_to_discord(message_data)

            self._set_response()
            self.wfile.write(b"Message received")
        except json.JSONDecodeError:
            self._set_response(400)
            self.wfile.write(b"Invalid JSON")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, User-Agent, Accept-Language, X-Fingerprint",
        )
        self.end_headers()


async def run(
    server_class=HTTPServer, handler_class=SimpleHTTPRequestHandler, port=8080
):
    server_address = ("", port)
    httpd = server_class(server_address, handler_class)
    print(f"Starting http server on port {port}")
    banner_message = {
        "username": "System",
        "message": "::banner{Server has been started/restarted. All previous messages have been cleared.}",
    }
    message_history.append(banner_message)
    send_to_discord(banner_message)
    httpd.serve_forever()


async def main():
    asyncio.create_task(clear_history_periodically())
    await asyncio.gather(run())


if __name__ == "__main__":
    asyncio.run(main())
