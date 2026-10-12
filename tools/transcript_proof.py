"""Round-21 proof: what the tutor says when a student really talks to it."""
import asyncio, json, urllib.request

BASE = "http://127.0.0.1:3000"


def create(level="beginner", topic="binary-search", lang="ar"):
    body = json.dumps({"student_id": "demo-teach", "topic_id": topic,
                       "language": lang, "level": level}).encode()
    req = urllib.request.Request(BASE + "/voice/session", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


async def main():
    import websockets
    info = create()
    print("session:", info["session_id"], "| level:", info["student_level"])

    async def turn():
        text = ""
        while True:
            ev = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
            if ev.get("event") == "assistant.text.delta":
                text += ev.get("text", "")
            elif ev.get("event") == "assistant.response.completed":
                return text

    async with websockets.connect(info["websocket_url"]) as ws:
        await ws.send(json.dumps({"type": "start"}))
        print("\nالمدرس (الافتتاح):\n" + await turn())
        for q in ["كم مقارنة تحتاج لمليون عنصر؟",
                  "ليه لازم البيانات تكون مرتبة؟",
                  "أنا مش فاهم",
                  "إيه الفرق بينه وبين البحث العادي؟"]:
            kind = "question" if q.endswith("؟") else "text"
            await ws.send(json.dumps({"type": kind, "text": q}))
            print(f"\nالطالب: {q}\nالمدرس:\n" + await turn())
        await ws.send(json.dumps({"type": "end"}))


asyncio.run(main())
