#!/usr/bin/env python3
"""Find OK button in settings dialog."""
import asyncio, json, urllib.request
BROWSER_PORT = 9223
def cdp_fetch(path):
    with urllib.request.urlopen(f'http://127.0.0.1:{BROWSER_PORT}{path}', timeout=5) as resp:
        return json.loads(resp.read().decode())
tabs = cdp_fetch('/json')
tv_tab = None
for t in tabs:
    if 'tradingview.com' in t.get('url','') and 'chart' in t.get('url',''):
        tv_tab = t; break
import websockets

async def main():
    ws_url = tv_tab['webSocketDebuggerUrl']
    async with websockets.connect(ws_url) as ws:
        async def cdp(method, params=None, rid=1):
            cmd = {'id': rid, 'method': method}
            if params: cmd['params'] = params
            await ws.send(json.dumps(cmd))
            while True:
                r = json.loads(await ws.recv())
                if r.get('id') == rid: return r
        async def eval_obj(js):
            r = await cdp('Runtime.evaluate', {'expression': js, 'returnByValue': True})
            return r.get('result',{}).get('result',{}).get('value')
        await cdp('Page.enable')

        # Open settings
        gear = await eval_obj("""
            (() => {
                const indicators = document.querySelectorAll('[class*="legend"] [class*="name"], [class*="legend"] [class*="title"]');
                for (const ind of indicators) {
                    if (ind.textContent.includes('v13.8')) {
                        let el = ind;
                        while (el && !el.className.includes('item') && !el.className.includes('study')) { el = el.parentElement; }
                        if (el) {
                            const btns = el.querySelectorAll('button');
                            for (const b of btns) {
                                if (b.getAttribute('aria-label') === 'Settings') {
                                    const r = b.getBoundingClientRect();
                                    return {x: r.x + r.width/2, y: r.y + r.height/2};
                                }
                            }
                        }
                    }
                }
                return null;
            })()
        """)
        if gear:
            await cdp("Input.dispatchMouseEvent", {"type": "mousePressed", "x": gear["x"], "y": gear["y"], "button": "left", "clickCount": 1})
            await cdp("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": gear["x"], "y": gear["y"], "button": "left", "clickCount": 1})
            await asyncio.sleep(3)

        # Find footer buttons - typically at the bottom of the dialog
        r = await eval_obj("""
            (() => {
                const wrapper = document.querySelector('[class*="wrapper-b8SxMnzX"]');
                if (!wrapper) return 'no wrapper';
                // Find the footer area
                const footer = wrapper.querySelector('[class*="footer"]');
                if (footer) {
                    const btns = footer.querySelectorAll('button');
                    return Array.from(btns).map(b => ({
                        text: (b.textContent || '').trim(),
                        visible: b.offsetParent !== null
                    }));
                }
                // Look for ANY buttons containing OK/Apply anywhere in page
                const allBtns = document.querySelectorAll('button');
                const okBtns = [];
                for (const b of allBtns) {
                    const t = (b.textContent || '').trim();
                    if (t === 'OK' || t === 'Apply' || t === 'Ok') {
                        okBtns.push({text: t, visible: b.offsetParent !== null, rect: JSON.stringify(b.getBoundingClientRect())});
                    }
                }
                return okBtns.length ? okBtns : 'no ok btns found';
            })()
        """)
        print(f'OK buttons: {json.dumps(r, indent=2)}')

asyncio.run(main())
