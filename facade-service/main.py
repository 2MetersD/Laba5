from fastapi import FastAPI, Request
import requests
import random
import uuid
import os
import uvicorn
import json
from kafka import KafkaProducer
import consul

app = FastAPI()


def get_service_urls(service_name):
    c = consul.Consul(host='localhost', port=8500)
    index, services = c.health.service(service_name, passing=True)
    if not services:
        return []
    return [f"http://{service['Service']['Address']}:{service['Service']['Port']}" for service in services]


def register_service():
    c = consul.Consul(host='localhost', port=8500)
    service_name = "facade-service"
    port = 8000  # Порт для facade-service
    service_id = f"{service_name}-{port}"

    c.agent.service.register(
        name=service_name,
        service_id=service_id,
        address="127.0.0.1",
        port=port
    )


producer = KafkaProducer(
    bootstrap_servers=['localhost:9092', 'localhost:9093', 'localhost:9094'],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)


@app.post("/")
async def post_msg(req: Request):
    data = await req.json()
    msg = data.get("msg")
    if not msg:
        return {"error": "msg field required"}

    msg_id = str(uuid.uuid4())
    payload = {"uuid": msg_id, "msg": msg}

    try:
        producer.send("messages", value=payload)
    except Exception as e:
        return {"status": "error", "reason": f"Kafka send failed: {str(e)}"}

    LOGGING_SERVICES = get_service_urls("logging-service")
    if not LOGGING_SERVICES:
        return {"status": "ok", "uuid": msg_id, "log_sent": False, "log_error": "logging-service unavailable"}

    random.shuffle(LOGGING_SERVICES)
    log_sent = False
    for url in LOGGING_SERVICES:
        try:
            r = requests.post(f"{url}/log", json=payload, timeout=2)
            if r.status_code == 200:
                log_sent = True
                break
        except:
            continue

    return {
        "status": "ok",
        "uuid": msg_id,
        "log_sent": log_sent
    }


@app.get("/")
async def get_combined():
    logs = []
    msgs = []

    LOGGING_SERVICES = get_service_urls("logging-service")
    MESSAGES_SERVICES = get_service_urls("messages-service")

    if not LOGGING_SERVICES:
        logs = "logging-service unavailable"
    else:
        for url in random.sample(LOGGING_SERVICES, len(LOGGING_SERVICES)):
            try:
                r = requests.get(f"{url}/log", timeout=2)
                if r.status_code == 200:
                    logs = r.json().get("messages", [])
                    break
            except:
                continue

    if not MESSAGES_SERVICES:
        msgs = "messages-service unavailable"
    else:
        for url in random.sample(MESSAGES_SERVICES, len(MESSAGES_SERVICES)):
            try:
                r = requests.get(f"{url}/msg", timeout=2)
                if r.status_code == 200:
                    msgs = r.json()
                    break
            except:
                continue

    return {
        "logs": logs,
        "messages": msgs
    }


if __name__ == "__main__":
    register_service()
    # Змінено: тепер запускаємо "main:app" на порту 8000
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)