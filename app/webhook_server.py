"""Part 4 student implementation."""
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from app.integration import process_request
from app.webex_client import WEBEX_API_BASE, WebexClient

class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor if processor is not None else process_request

    def handle_event(self, event):
        if not isinstance(event, dict):
            return None

        if event.get("resource") != "messages" or event.get("event") != "created":
            return None

        data = event.get("data")
        if not isinstance(data, dict):
            return None

        if not data.get("id"):
            return None

        # Ignore messages from the bot itself before API lookup
        if data.get("personId") == self.bot_person_id:
            return None

        msg = self.client.get_message(data["id"])
        if not isinstance(msg, dict):
            return None

        # Check author of fetched message to prevent reply loops
        if msg.get("personId") == self.bot_person_id:
            return None

        room_id = msg.get("roomId")
        mentioned_people = msg.get("mentionedPeople", [])
        files = msg.get("files") or []

        if len(files) > 1:
            result = {"status": "error", "result": "multiple_attachments"}
            if room_id:
                self.client.send_message(room_id, json.dumps(result))
            return result

        if len(files) == 0:
            result = self.processor(mentioned_people, None, self.bot_person_id)
            if room_id:
                self.client.send_message(room_id, json.dumps(result))
            return result

        # Exactly 1 attachment
        content = self.client.download_file(files[0])
        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "request.yaml"
            tmp_path.write_bytes(content)
            try:
                result = self.processor(mentioned_people, tmp_path, self.bot_person_id)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

        if room_id:
            self.client.send_message(room_id, json.dumps(result))
        return result

def make_http_handler(submit_event):
    class WebhookHTTPHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"status": "ok", "result": "healthy"}).encode("utf-8")
                )
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"status": "error", "result": "not_found"}).encode("utf-8")
                )

        def do_POST(self):
            if self.path == "/webhook":
                content_length_str = self.headers.get("Content-Length")
                if not content_length_str:
                    self.send_error_400()
                    return
                try:
                    content_length = int(content_length_str)
                except ValueError:
                    self.send_error_400()
                    return

                if content_length < 1 or content_length > 1_000_000:
                    self.send_error_400()
                    return

                body = self.rfile.read(content_length)
                try:
                    data = json.loads(body.decode("utf-8"))
                except Exception:
                    self.send_error_400()
                    return

                if not isinstance(data, dict):
                    self.send_error_400()
                    return

                try:
                    submit_event(data)
                except Exception:
                    pass

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"status": "ok", "result": "accepted"}).encode("utf-8")
                )
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"status": "error", "result": "not_found"}).encode("utf-8")
                )

        def send_error_400(self):
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"status": "error", "result": "invalid_event"}).encode("utf-8")
            )

        def log_message(self, format, *args):
            pass

    return WebhookHTTPHandler


def main():
    logging.basicConfig(level=logging.INFO)
    host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.getenv("WEBHOOK_PORT", "8000"))
    token = os.getenv("WEBEX_BOT_TOKEN")

    client = None
    bot_person_id = None
    if token:
        try:
            client = WebexClient(token=token)
            me = client.get_me()
            bot_person_id = me.get("id")
            logging.info(
                f"Bot authenticated as {me.get('displayName')} (id: {bot_person_id})"
            )
        except Exception as e:
            logging.error(f"Failed to initialize Webex client: {e}")

    executor = ThreadPoolExecutor(max_workers=1)
    if client and bot_person_id:
        handler = WebexEventHandler(client, bot_person_id)
        submit_event = lambda evt: executor.submit(handler.handle_event, evt)
    else:
        submit_event = lambda evt: logging.warning(
            "Event received but Webex client is unconfigured"
        )

    server = ThreadingHTTPServer((host, port), make_http_handler(submit_event))
    logging.info(f"Serving webhook HTTP server on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
        executor.shutdown(wait=False)

if __name__ == "__main__":
    main()