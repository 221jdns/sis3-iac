import json
import os
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import boto3
from botocore.exceptions import BotoCoreError, ClientError

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path not in ("/", "/health", "/version"):
            return self.reply(404, {"error": "Not found"})
        self.reply(200, {"status": "ok", "service": "sis3-orders",
                         "version": os.getenv("APP_VERSION", "local")})

    def do_POST(self):
        if urlparse(self.path).path != "/orders":
            return self.reply(404, {"error": "Not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16384:
                raise ValueError("Body must contain 1 to 16384 bytes")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("JSON body must be an object")
            order_id = data.get("orderId")
            event_id = data.get("eventId", str(uuid.uuid4()))
            for key, value in (("orderId", order_id), ("eventId", event_id)):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(key + " must be a non-empty string")
                if len(value) > 128:
                    raise ValueError(key + " must not exceed 128 characters")
        except (ValueError, UnicodeDecodeError) as exc:
            return self.reply(400, {"error": str(exc)})
        topic = os.getenv("TOPIC_ARN")
        if not topic:
            return self.reply(503, {"error": "TOPIC_ARN is not configured"})
        event = {"eventId": event_id, "orderId": order_id,
                 "eventType": "OrderCreated",
                 "createdAt": datetime.now(timezone.utc).isoformat()}
        try:
            boto3.client("sns").publish(TopicArn=topic,
                                         Message=json.dumps(event))
        except (BotoCoreError, ClientError):
            print(json.dumps({"action": "publish_failed",
                              "eventId": event_id}), flush=True)
            return self.reply(502, {"error": "Event publication failed"})
        print(json.dumps({"action": "event_published",
                          "eventId": event_id}), flush=True)
        self.reply(202, {"status": "accepted", "eventId": event_id,
                         "orderId": order_id})

    def log_message(self, fmt, *args):
        print(json.dumps({"request": fmt % args}), flush=True)

if __name__ == "__main__":
    print("Starting sis3-orders on port 8080", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
