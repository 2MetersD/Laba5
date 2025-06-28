from fastapi import FastAPI, Request
import hazelcast
import os
import uvicorn
import multiprocessing
import consul


def register_service(port):
    c = consul.Consul(host='localhost', port=8500)
    service_name = "logging-service"
    service_id = f"{service_name}-{port}"

    # Health check для Consul з Docker все ще використовує host.docker.internal
    http_check = consul.Check.http(f"http://host.docker.internal:{port}/health", "10s", "5s", "30s")

    c.agent.service.register(
        name=service_name,
        service_id=service_id,
        # --- ВИПРАВЛЕНО ТУТ ---
        # Повертаємо адресу 127.0.0.1, щоб інші сервіси на хості могли її бачити
        address="127.0.0.1",
        port=port,
        check=http_check
    )


def start_server(port, hazel_port):
    app = FastAPI()
    register_service(port)

    HZ_MEMBERS = os.environ.get("HZ_MEMBERS", f"127.0.0.1:{hazel_port}").split(",")
    hz = hazelcast.HazelcastClient(cluster_members=HZ_MEMBERS)
    map = hz.get_map("messages").blocking()

    @app.post("/log")
    async def log_message(req: Request):
        data = await req.json()
        msg_id = data.get("uuid")
        msg = data.get("msg")
        if msg_id and msg:
            map.put(msg_id, msg)
            print(f"[LoggingService:{port}] Logged: {msg_id} -> {msg}")
            return {"status": "ok"}
        return {"status": "error", "reason": "Missing fields"}

    @app.get("/log")
    async def get_all():
        entries = map.entry_set()
        return {"messages": [v for k, v in entries]}

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    uvicorn.run(app, host="127.0.0.1", port=port, reload=False)


if __name__ == "__main__":
    p1 = multiprocessing.Process(target=start_server, args=(8011, 5701))
    p2 = multiprocessing.Process(target=start_server, args=(8012, 5702))
    p1.start()
    p2.start()
    p1.join()
    p2.join()