import random
import time
import json
import urllib.request
import urllib.error
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright

# Force UTF-8 encoding for Windows terminals
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# -------------------------
# YOUR WEBSITE URL
# -------------------------
URL = "https://app.hidevs.xyz/vote/flow-scrape-agent-etx5"

# -------------------------
# Multi-Brand Device Pool
# -------------------------
android_devices = {
    "Samsung": ["Galaxy S21", "Galaxy S22", "Galaxy S23", "Galaxy S24"],
    "Redmi": ["Note 11", "Note 12", "K50"],
    "Realme": ["10 Pro", "11 Pro", "GT Neo 3"],
    "OnePlus": ["Nord 3", "11R", "12"],
    "Oppo": ["Reno 8", "Reno 10", "Find X5"],
    "Vivo": ["V27", "V29", "Y100"],
    "Pixel": ["Pixel 6", "Pixel 7", "Pixel 8"]
}

iphone_devices = ["iPhone 12", "iPhone 13", "iPhone 14", "iPhone 15"]

# -------------------------
# Random Device Generator
# -------------------------
def generate_device():
    device_type = random.choice(["android", "iphone"])

    if device_type == "android":
        brand = random.choice(list(android_devices.keys()))
        model = random.choice(android_devices[brand])
        android_version = random.randint(11, 14)
        chrome_version = random.randint(118, 124)

        user_agent = (
            f"Mozilla/5.0 (Linux; Android {android_version}; {brand} {model}) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_version}.0.0.0 Mobile Safari/537.36"
        )
    else:
        model = random.choice(iphone_devices)
        ios_version = f"{random.randint(15, 17)}_{random.randint(0, 5)}"

        user_agent = (
            f"Mozilla/5.0 (iPhone; CPU iPhone OS {ios_version} like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            f"Version/{random.randint(15, 17)}.0 Mobile/15E148 Safari/604.1"
        )

    return {
        "name": model,
        "type": device_type,
        "user_agent": user_agent,
        "viewport": {
            "width": random.randint(360, 430),
            "height": random.randint(740, 932)
        }
    }

# -------------------------
# Configuration
# -------------------------
TOTAL_SESSIONS = 1000          # Total number of votes to cast
HEADLESS = True               # Set True to run without browser window
AUTO_CONTINUE = True          # Set False to pause between sessions
RANDOM_DELAY = (1, 3)         # Random delay range in seconds between actions
USE_PROXIES = True            # True = fetch free proxies, False = skip

# Concurrent Mode Configuration
CONCURRENT_BROWSERS = 100     # Number of browsers to open at once (Set to 1 for sequential mode)

# Block heavy resources for faster page loads
BLOCK_RESOURCES = True

# Resource types to block (saves bandwidth + load time)
BLOCKED_RESOURCE_TYPES = [
    "image", "media", "font", "stylesheet",
    "texttrack", "eventsource", "manifest", "other"
]

# -------------------------
# Proxy System
# -------------------------
def check_proxy(proxy_dict):
    try:
        # We'll test against a fast, reliable endpoint
        req = urllib.request.Request("http://httpbin.org/ip", headers={"User-Agent": "Mozilla/5.0"})
        proxy_handler = urllib.request.ProxyHandler({"http": proxy_dict["server"], "https": proxy_dict["server"]})
        opener = urllib.request.build_opener(proxy_handler)
        # Short timeout to ensure we only keep fast, live proxies
        resp = opener.open(req, timeout=3)
        if resp.status == 200:
            return proxy_dict
    except:
        pass
    return None

def fetch_free_proxies():
    """Pull free proxies from public APIs."""
    from concurrent.futures import ThreadPoolExecutor

    raw_proxies = []

    # --- Source 1: TheSpeedX (GitHub) ---
    try:
        url = "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode("utf-8", errors="ignore")
        for line in raw.strip().splitlines():
            line = line.strip()
            if line and ":" in line:
                raw_proxies.append({"server": f"http://{line}"})
    except Exception as e:
        print(f"[proxy] TheSpeedX failed: {e}")

    # --- Source 2: monosans (GitHub) ---
    try:
        url = "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode("utf-8", errors="ignore")
        for line in raw.strip().splitlines():
            line = line.strip()
            if line and ":" in line:
                raw_proxies.append({"server": f"http://{line}"})
    except Exception as e:
        print(f"[proxy] monosans failed: {e}")

    # --- Source 3: proxyscrape ---
    try:
        url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=elite"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode("utf-8", errors="ignore")
        for line in raw.strip().splitlines():
            line = line.strip()
            if ":" in line:
                raw_proxies.append({"server": f"http://{line}"})
    except Exception as e:
        print(f"[proxy] proxyscrape failed: {e}")

    print(f"[proxy] Fetching and testing proxies...")
    proxies = []
    
    with ThreadPoolExecutor(max_workers=50) as executor:
        results = executor.map(check_proxy, raw_proxies)
        for res in results:
            if res:
                proxies.append(res)

    if proxies:
        random.shuffle(proxies)
        print(f"[proxy] Found {len(proxies)} live proxies.")
    else:
        print("[proxy] No live proxies found.")

    return proxies

# (Proxy initialization moved into run_voting loop)

_proxy_idx = 0
def next_proxy():
    """Round-robin through proxy pool. Returns None if pool is empty."""
    global _proxy_idx
    if not PROXY_POOL:
        return None
    proxy = PROXY_POOL[_proxy_idx % len(PROXY_POOL)]
    _proxy_idx += 1
    return proxy

# -------------------------
# Helper: Human-like delay
# -------------------------
def human_delay(min_sec=None, max_sec=None):
    if min_sec is None:
        min_sec = RANDOM_DELAY[0]
    if max_sec is None:
        max_sec = RANDOM_DELAY[1]
    time.sleep(random.uniform(min_sec, max_sec))

# -------------------------
# Helper: Get community vote count
# -------------------------
def get_vote_count(page):
    """Scrape the current community vote count from the page."""
    try:
        count = page.evaluate("""
            () => {
                const allEls = document.querySelectorAll('*');
                for (const el of allEls) {
                    if (el.children.length > 0) continue;
                    const txt = (el.textContent || '').trim();
                    if (/^\\d+$/.test(txt)) {
                        const parent = el.parentElement;
                        if (parent) {
                            const parentText = parent.textContent.toLowerCase();
                            if (parentText.includes('vote') || parentText.includes('community')) {
                                return parseInt(txt, 10);
                            }
                        }
                    }
                }
                const body = document.body.innerText;
                const match = body.match(/(\\d+)\\s*(?:votes?|community\\s*votes?)/i);
                if (match) return parseInt(match[1], 10);
                const match2 = body.match(/(?:community\\s*votes?|total\\s*votes?)\\s*[:\\s]*(\\d+)/i);
                if (match2) return parseInt(match2[1], 10);
                return null;
            }
        """)
        return count
    except:
        return None

# -------------------------
# Helper: Cast vote
# -------------------------
def cast_vote(page):
    """Click 'Cast your vote' and verify the vote count increased."""

    # --- wait for full page load ---
    print("  ⏳ Waiting for page to fully load...")
    page.wait_for_function("document.readyState === 'complete'", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except:
        pass
    human_delay(2, 4)
    print("  ✅ Page loaded.")

    # --- capture vote count BEFORE clicking ---
    vote_before = get_vote_count(page)
    if vote_before is not None:
        print(f"  📊 Current vote count: {vote_before}")
    else:
        print("  📊 Could not read vote count (will still try)")

    # --- check for "Sign In" instead of voting ---
    try:
        sign_in_loc = page.locator('text=/Sign In/i').first
        sign_in_loc.wait_for(state="visible", timeout=2000)
        print("  ⚠️ 'Sign In' detected instead of vote button. Aborting.")
        raise Exception("Sign In page detected")
    except Exception as e:
        if str(e) == "Sign In page detected":
            raise e
        # TimeoutError means no Sign In found, which is what we want.

    # --- find the "Cast your vote" button ---
    btn = page.locator('button:has-text("Cast your vote")')

    try:
        btn.wait_for(state="visible", timeout=5000)
    except:
        for fallback in [
            'button:has-text("cast your vote")',
            'button:has-text("Vote")',
            'text=/cast\\s+your\\s+vote/i',
            'button.bg-slate-900',
            'button[type="button"]:has-text("vote")',
        ]:
            try:
                btn = page.locator(fallback).first
                if btn.is_visible(timeout=3000):
                    break
            except:
                continue
        else:
            print("  ⚠️  'Cast your vote' button not found!")
            return False

    # Check if disabled
    if btn.is_disabled():
        print("  ⚠️  Button is DISABLED — may have already voted")
        return False

    # Human-like click
    btn.scroll_into_view_if_needed()
    human_delay(0.5, 1.5)
    btn.click(force=True)
    print("  🗳️  Clicked 'Cast your vote'!")

    # --- wait for vote count to increase ---
    print("  ⏳ Waiting indefinitely for vote count to update...")

    poll_interval = 1
    vote_confirmed = False

    while not vote_confirmed:
        time.sleep(poll_interval)
        
        vote_after = get_vote_count(page)

        if vote_after is not None:
            if vote_before is not None and vote_after > vote_before:
                print(f"  🎉 Vote count: {vote_before} → {vote_after} ✓")
                vote_confirmed = True
                break
            elif vote_before is None:
                print(f"  🎉 Vote count is now: {vote_after} (assumed success)")
                vote_confirmed = True
                break
            else:
                print(f"  ⏳ Still {vote_after}, waiting...")

        # Check if button text changed
        try:
            btn_text = btn.text_content(timeout=1000)
            if btn_text and any(w in btn_text.lower() for w in ["voted", "thanks", "submitted", "done"]):
                print(f"  🎉 Button changed to: '{btn_text}' ✓")
                vote_confirmed = True
                break
        except:
            pass

        # Check if button became disabled
        try:
            if btn.is_disabled():
                print("  🎉 Button became disabled after click ✓")
                vote_confirmed = True
                break
        except:
            pass

    return True

# -------------------------
# Main: Playwright Runner
# -------------------------
import asyncio
from playwright.async_api import async_playwright

async def run_single_session(i, browser, stats):
    device = generate_device()
    proxy = next_proxy()

    context_args = {
        "user_agent": device["user_agent"],
        "viewport": device["viewport"],
        "device_scale_factor": random.choice([2, 3]),
        "is_mobile": True,
        "has_touch": True,
    }
    if proxy:
        context_args["proxy"] = proxy

    try:
        context = await browser.new_context(**context_args)
        page = await context.new_page()

        if BLOCK_RESOURCES:
            async def block_route(route):
                if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
                    await route.abort()
                else:
                    await route.continue_()
            await page.route("**/*", block_route)

        def on_framenavigated(frame):
            if frame == page.main_frame and "app.hidevs.xyz/login" in frame.url:
                asyncio.create_task(context.close())
                
        page.on("framenavigated", on_framenavigated)

        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(random.uniform(1.5, 3))

        try:
            await page.wait_for_load_state("networkidle", timeout=60000)
        except:
            pass
        await asyncio.sleep(random.uniform(2, 4))

        try:
            not_found = page.locator('text=/Nomination not found/i').first
            if await not_found.is_visible(timeout=2000):
                await page.reload(wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=60000)
                except:
                    pass
                await asyncio.sleep(random.uniform(2, 4))
        except:
            pass

        try:
            sign_in_loc = page.locator('text=/Sign In/i').first
            await sign_in_loc.wait_for(state="visible", timeout=2000)
            raise Exception("Sign In page detected")
        except Exception as e:
            if str(e) == "Sign In page detected":
                raise e

        btn = page.locator('button:has-text("Cast your vote")')
        try:
            await btn.wait_for(state="visible", timeout=5000)
        except:
            for fallback in [
                'button:has-text("cast your vote")',
                'button:has-text("Vote")',
                'text=/cast\\s+your\\s+vote/i',
                'button.bg-slate-900',
                'button[type="button"]:has-text("vote")',
            ]:
                try:
                    btn = page.locator(fallback).first
                    if await btn.is_visible(timeout=3000):
                        break
                except:
                    continue
            else:
                stats["fail"] += 1
                await context.close()
                return

        if await btn.is_disabled():
            stats["fail"] += 1
            await context.close()
            return

        await btn.scroll_into_view_if_needed()
        await asyncio.sleep(random.uniform(0.5, 1.5))
        await btn.click(force=True)
        await asyncio.sleep(random.uniform(1, 2))
        
        stats["success"] += 1
        await context.close()
    except Exception as e:
        stats["fail"] += 1
        try:
            await context.close()
        except:
            pass


async def run_voting():
    global TOTAL_SESSIONS, PROXY_POOL
    stats = {"success": 0, "fail": 0}
    loop_count = 0

    while True:
        loop_count += 1
        print(f"\n{'*'*50}")
        print(f"🔄 STARTING VOTING LOOP ITERATION {loop_count}")
        print(f"{'*'*50}")

        # --- Fetch/Reload proxies for this iteration ---
        if USE_PROXIES:
            print("Fetching proxies...")
            PROXY_POOL = fetch_free_proxies()
        else:
            print("[proxy] Skipping (USE_PROXIES=False)")
            PROXY_POOL = []

        # Dynamically set total sessions based on live proxies for all modes
        if PROXY_POOL:
            TOTAL_SESSIONS = len(PROXY_POOL)
            print(f"[config] TOTAL_SESSIONS set to {TOTAL_SESSIONS} to match live proxies.")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=HEADLESS, slow_mo=30)
            
            for i in range(0, TOTAL_SESSIONS, CONCURRENT_BROWSERS):
                batch_size = min(CONCURRENT_BROWSERS, TOTAL_SESSIONS - i)
                tasks = []
                
                for j in range(batch_size):
                    session_idx = i + j
                    tasks.append(run_single_session(session_idx, browser, stats))
                
                await asyncio.gather(*tasks)
                
                if i + batch_size < TOTAL_SESSIONS:
                    await asyncio.sleep(random.uniform(1, 3))

            await browser.close()

        # ---- SUMMARY ----
        print(f"\n{'='*50}")
        print(f"📊 SUMMARY (AFTER ITERATION {loop_count})")
        print(f"  ✅ Successful: {stats['success']}")
        print(f"  ❌ Failed: {stats['fail']}")
        print(f"  📋 Total Attempted: {stats['success'] + stats['fail']}")
        print(f"{'='*50}")
        
        print("\n⏳ Loop iteration finished. Restarting in 5 seconds... (Press Ctrl+C to stop)")
        await asyncio.sleep(5)

# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    asyncio.run(run_voting())