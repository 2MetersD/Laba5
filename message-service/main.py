from kafka import KafkaConsumer
from fastapi import FastAPI
from threading import Thread
import multiprocessing
import json
import os
import uvicorn
import consul

def register_service(port):
    print(f"[{port}] Намагаюся зареєструвати сервіс в Consul...")
    try:
        c = consul.Consul(host='localhost', port=8500)
        service_name = "messages-service"
        service_id = f"{service_name}-{port}"

        http_check = consul.Check.http(f"http://host.docker.internal:{port}/health", "10s", "5s", "30s")

        c.agent.service.register(
            name=service_name,
            service_id=service_id,
            address="host.docker.internal",
            port=port,
            check=http_check
        )
        print(f"[{port}] Сервіс успішно зареєстровано!")

    except Exception as e:
        print(f"[{port}] !!! ВИНИКЛА ПОМИЛКА ПРИ РЕЄСТРАЦІЇ В CONSUL: {e}")


def create_app(port):
    app = FastAPI()
    storage = []
    register_service(port)

    def consume():
        consumer = KafkaConsumer(
            'messages',
            bootstrap_servers=['localhost:9092', 'localhost:9093', 'localhost:9094'],
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            group_id=f"msg-group-{port}",
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        for message in consumer:
            print(f"[MSG-SERVICE {port}] Received:", message.value)
            storage.append(message.value)

    @app.get("/msg")
    async def get_messages():
        return storage

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    Thread(target=consume, daemon=True).start()
    return app


def run_instance(port):
    os.environ["PORT"] = str(port)
    app = create_app(port)
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    ports = [8003, 8004]
    processes = []

    for port in ports:
        p = multiprocessing.Process(target=run_instance, args=(port,))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()