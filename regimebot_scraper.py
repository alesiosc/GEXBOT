"""
Discord #regimebot scraper - checks for new posts from gex.bot every 15min
Posts to webhook when new messages are detected
"""
import requests, json, asyncio, websockets, re, os, io
from datetime import datetime

CHANNEL_URL = "https://discord.com/channels/921574741272317982/1299110315673387060"
WEBHOOK_URL = "https://discord.com/api/webhooks/1520138589747282010/X2buNs1fAZ9bTrfC2BAPd2gYoKzvfVY2G4jG2DMvXowYrw853-H9W7BWdLoK2hqKBF2M"
STATE_FILE = os.path.expanduser("~/.regimebot_last_seen.txt")

def load_state():
    try:
        with open(STATE_FILE) as f:
            return f.read().strip()
    except: return ""

def save_state(ts):
    d = os.path.dirname(STATE_FILE)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        f.write(ts)

async def cdp_call(ws, req_id, method, params=None):
    cmd = {"id": req_id, "method": method}
    if params: cmd["params"] = params
    await ws.send(json.dumps(cmd))
    while True:
        resp = json.loads(await ws.recv())
        if resp.get("id") == req_id:
            return resp

async def scrape():
    r = requests.get("http://localhost:9223/json", timeout=5)
    ws_url = None
    for t in r.json():
        if "channels/921574741272317982/1299110315673387060" in t.get("url",""):
            ws_url = t["webSocketDebuggerUrl"]; break
    if not ws_url:
        for t in r.json():
            if "discord.com/channels" in t.get("url",""):
                ws_url = t["webSocketDebuggerUrl"]; break
    if not ws_url:
        raise Exception("No Discord tab found on Trump browser")
    
    async with websockets.connect(ws_url) as sock:
        await cdp_call(sock, 1, "Page.enable")
        await cdp_call(sock, 2, "Page.bringToFront")
        await asyncio.sleep(0.5)
        
        # Navigate or refresh
        current_url = None
        resp = await cdp_call(sock, 3, "Runtime.evaluate",
            {"expression": "window.location.href", "returnByValue": True})
        current_url = resp.get("result",{}).get("result",{}).get("value","")
        
        if CHANNEL_URL not in current_url:
            await cdp_call(sock, 4, "Page.navigate", {"url": CHANNEL_URL})
            await asyncio.sleep(6)
        
        # Scroll to bottom
        await cdp_call(sock, 5, "Runtime.evaluate",
            {"expression": 'document.querySelector("[class*=scroller__36d07]")?.scrollTo(0, 99999)'})
        await asyncio.sleep(3)
        
        # Scrape text
        resp = await cdp_call(sock, 6, "Runtime.evaluate",
            {"expression": "document.body.innerText", "returnByValue": True})
        text = resp.get("result",{}).get("result",{}).get("value","")
        
        # Extract timestamps
        times = re.findall(r'(\d{2}:\d{2})\s*\n\s*Friday, 26 June 2026', text)
        if not times:
            times = re.findall(r'(\d{2}:\d{2})', text)
        
        # Get latest time
        latest = times[-1] if times else ""
        
        # Also extract the gex.bot message section
        idx = text.find("regimebot chat")
        if idx < 0: idx = text.find("gex.bot APP")
        section = text[idx:idx+2000] if idx >= 0 else text[-2000:]
        
        return {"latest_time": latest, "section": section, "all_times": times}

if __name__ == "__main__":
    try:
        data = asyncio.run(scrape())
    except Exception as e:
        print(f"SCRAPE_ERROR: {e}")
        exit(1)
    
    latest = data["latest_time"]
    last_seen = load_state()
    
    if latest and latest == last_seen:
        print(f"No new posts (latest: {latest})")
        exit(0)
    
    if not latest:
        print("No timestamps found")
        exit(1)
    
    # Format message
    msg = f"**#regimebot New Post** — {latest}\n\n```\n{data['section'][:1500]}\n```"
    
    r = requests.post(WEBHOOK_URL, json={"content": msg[:1900]})
    if r.status_code in [200, 204]:
        save_state(latest)
        print(f"Posted: {latest}")
    else:
        print(f"Webhook failed: {r.status_code} {r.text[:200]}")
        exit(1)
