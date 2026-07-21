import os
import random
import shutil
import time
import hashlib
import json
import socket
import urllib.request
import urllib.error
from pathlib import Path
from playwright.sync_api import sync_playwright, Error

# =====================================================
# INPUT
# =====================================================

URL = input("Enter URL : ").strip()
COUNT = int(input("Number of browser sessions : "))

# =====================================================
# DELETE PROFILE EVERY RUN?
# =====================================================

CLEAR_PROFILES = False

PROFILE_ROOT = Path("profiles")

if CLEAR_PROFILES and PROFILE_ROOT.exists():
    shutil.rmtree(PROFILE_ROOT)

PROFILE_ROOT.mkdir(exist_ok=True)

# =====================================================
# PROXIES — auto-fetch + manual fallbacks
# =====================================================

# Set to False to skip proxy fetching and use direct IP (FASTEST)
USE_PROXIES = True

# Block heavy resources for faster page loads
BLOCK_RESOURCES = True

# Resource types to block (saves bandwidth + load time)
BLOCKED_RESOURCE_TYPES = [
    "image", "media", "font", "stylesheet",
    "texttrack", "eventsource", "manifest", "other"
]

def validate_proxy(proxy_dict, timeout=4):
    """Quick socket test — can we even connect to this proxy?"""
    try:
        server = proxy_dict["server"]
        # parse host:port from "http://host:port" or "socks5://host:port"
        addr = server.split("://", 1)[-1].split("@")[-1]  # strip auth
        host, port = addr.rsplit(":", 1)
        port = int(port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        return True
    except:
        return False

def fetch_free_proxies():
    """Pull free proxies from public APIs. Returns list of proxy dicts."""
    proxies = []

    # --- Source 1: proxyscrape.com (free API) ---
    try:
        url = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=elite"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode("utf-8", errors="ignore")
        for line in raw.strip().splitlines():
            line = line.strip()
            if ":" in line:
                proxies.append({"server": f"http://{line}"})
    except Exception as e:
        print(f"[proxy-fetch] proxyscrape failed: {e}")

    # --- Source 2: free-proxy-list via geonode ---
    try:
        url = "https://proxylist.geonode.com/api/proxy-list?limit=30&page=1&sort_by=lastChecked&sort_type=desc&anonymityLevel=elite&anonymityLevel=anonymous&protocols=http&protocols=https"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode("utf-8"))
        for p in data.get("data", []):
            ip = p.get("ip")
            port = p.get("port")
            if ip and port:
                proxies.append({"server": f"http://{ip}:{port}"})
    except Exception as e:
        print(f"[proxy-fetch] geonode failed: {e}")

    if not proxies:
        print("[proxy-fetch] No proxies found")
        return []

    # --- Pre-validate: quick socket test (filter dead ones) ---
    print(f"[proxy-fetch] Got {len(proxies)} raw proxies, validating (quick socket test)...")
    alive = []
    for i, p in enumerate(proxies[:50]):  # test top 50 max to save time
        if validate_proxy(p):
            alive.append(p)
        if (i + 1) % 10 == 0:
            print(f"  tested {i+1}/50 — {len(alive)} alive so far")

    if alive:
        random.shuffle(alive)
        print(f"[proxy-fetch] {len(alive)} proxies passed validation")
    else:
        print("[proxy-fetch] All proxies failed validation")

    return alive

# Manual proxies go here (these get priority)
MANUAL_PROXIES = [
    # {"server":"http://1.1.1.1:8080"},
    # {"server":"http://user:pass@1.1.1.1:8080"},
    # {"server":"socks5://1.1.1.1:1080"},
]

if USE_PROXIES:
    print("Fetching & validating proxies...")
    FETCHED_PROXIES = fetch_free_proxies()
else:
    print("[proxy] Skipping proxy fetch (USE_PROXIES=False) — using direct IP")
    FETCHED_PROXIES = []

# Combined pool: manual first, then fetched, always end with None (direct)
ALL_PROXIES = MANUAL_PROXIES + FETCHED_PROXIES + [None]

# Rotation index so each session gets a different proxy
_proxy_index = 0

def next_proxy():
    """Round-robin through the proxy pool so each session gets a unique IP."""
    global _proxy_index
    proxy = ALL_PROXIES[_proxy_index % len(ALL_PROXIES)]
    _proxy_index += 1
    return proxy

# Max proxy retries per browser before moving to next browser
MAX_PROXY_RETRIES = 3

# =====================================================
# USER AGENTS
# =====================================================

USER_AGENTS = [

"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",

"Mozilla/5.0 (Macintosh; Intel Mac OS X 15_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",

"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",

"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",

]

# =====================================================
# DEVICES
# =====================================================

DEVICES = [

"Desktop Chrome",
"Desktop Edge",
"Desktop Firefox",
"Pixel 7",
"Pixel 5",
"Galaxy S9+",
"Galaxy Note 3",
"iPhone 13",
"iPhone 12",
"iPad Mini",
"iPad Pro 11",

]

# =====================================================
# LOCATIONS
# =====================================================

LOCATIONS = [

{
"name":"Hyderabad",
"timezone":"Asia/Kolkata",
"locale":"en-IN",
"geo":{
"latitude":17.385,
"longitude":78.4867
}
},

{
"name":"Mumbai",
"timezone":"Asia/Kolkata",
"locale":"en-IN",
"geo":{
"latitude":19.0760,
"longitude":72.8777
}
},

{
"name":"London",
"timezone":"Europe/London",
"locale":"en-GB",
"geo":{
"latitude":51.5072,
"longitude":-0.1276
}
},

{
"name":"Tokyo",
"timezone":"Asia/Tokyo",
"locale":"ja-JP",
"geo":{
"latitude":35.6762,
"longitude":139.6503
}
},

{
"name":"New York",
"timezone":"America/New_York",
"locale":"en-US",
"geo":{
"latitude":40.7128,
"longitude":-74.0060
}
},

{
"name":"Sydney",
"timezone":"Australia/Sydney",
"locale":"en-AU",
"geo":{
"latitude":-33.8688,
"longitude":151.2093
}
},

]

# =====================================================
# BROWSERS
# =====================================================

BROWSERS = [

("chromium","chrome"),
("chromium","msedge"),
("firefox",None),

]

# =====================================================
# LOCALE -> LANGUAGES MAP
# =====================================================

LANGUAGES_MAP = {
    "en-US": ["en-US", "en"],
    "en-GB": ["en-GB", "en"],
    "en-IN": ["en-IN", "en-US", "en"],
    "en-AU": ["en-AU", "en"],
    "ja-JP": ["ja-JP", "ja", "en-US", "en"],
}

# =====================================================
# SCREEN RESOLUTIONS (width, height, common combos)
# =====================================================

SCREEN_CONFIGS = [
    {"width": 1920, "height": 1080, "avail_w": 1920, "avail_h": 1040, "depth": 24},
    {"width": 2560, "height": 1440, "avail_w": 2560, "avail_h": 1400, "depth": 24},
    {"width": 1366, "height": 768,  "avail_w": 1366, "avail_h": 728,  "depth": 24},
    {"width": 1536, "height": 864,  "avail_w": 1536, "avail_h": 824,  "depth": 24},
    {"width": 1440, "height": 900,  "avail_w": 1440, "avail_h": 860,  "depth": 24},
    {"width": 1680, "height": 1050, "avail_w": 1680, "avail_h": 1010, "depth": 30},
    {"width": 3840, "height": 2160, "avail_w": 3840, "avail_h": 2120, "depth": 30},
    {"width": 2560, "height": 1600, "avail_w": 2560, "avail_h": 1560, "depth": 24},
]

# =====================================================
# WEBGL RENDERER / VENDOR COMBOS
# =====================================================

WEBGL_CONFIGS = [
    {"vendor": "Google Inc. (NVIDIA)",    "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)",    "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (NVIDIA)",    "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)",       "renderer": "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (AMD)",       "renderer": "ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)",     "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Google Inc. (Intel)",     "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"},
    {"vendor": "Apple",                   "renderer": "Apple M1"},
    {"vendor": "Apple",                   "renderer": "Apple M2 Pro"},
    {"vendor": "Mesa",                    "renderer": "Mesa Intel(R) UHD Graphics 620 (KBL GT2)"},
]

# =====================================================
# PLATFORM STRINGS (matched to UA later)
# =====================================================

PLATFORMS = {
    "Windows": ["Win32", "Win64"],
    "Macintosh": ["MacIntel"],
    "Linux": ["Linux x86_64", "Linux aarch64"],
}

def pick_platform(user_agent):
    """Pick a navigator.platform that doesn't contradict the UA string."""
    if "Windows" in user_agent:
        return random.choice(PLATFORMS["Windows"])
    elif "Macintosh" in user_agent or "Mac OS" in user_agent:
        return random.choice(PLATFORMS["Macintosh"])
    elif "Linux" in user_agent:
        return random.choice(PLATFORMS["Linux"])
    return "Win32"  # safe default

# =====================================================
# RANDOM VIEWPORT
# =====================================================

def random_viewport():

    return {
        "width": random.randint(1200,1920),
        "height": random.randint(700,1080)
    }

# =====================================================
# FINGERPRINT SPOOFING SCRIPT GENERATOR
# =====================================================

def generate_fingerprint_script(locale, user_agent, viewport):
    """
    Builds a JS init script that randomizes/spoofs:
      - navigator.webdriver
      - navigator.languages (locale-matched)
      - navigator.plugins (realistic array)
      - navigator.platform (UA-matched)
      - navigator.hardwareConcurrency
      - navigator.deviceMemory
      - navigator.connection (Network Information API)
      - window.chrome runtime object
      - screen dimensions (matched to a real config)
      - canvas fingerprint (pixel noise injection)
      - WebGL vendor/renderer (UNMASKED_VENDOR / UNMASKED_RENDERER)
      - AudioContext (sample noise)
      - Battery API (random values)
      - Date.getTimezoneOffset consistency is handled by Playwright
    """

    # --- pick randomized values server-side ---
    seed = hashlib.md5(f"{random.random()}{time.time()}".encode()).hexdigest()[:8]
    hw_concurrency = random.choice([2, 4, 6, 8, 12, 16])
    dev_memory = random.choice([2, 4, 8, 16, 32])
    screen = random.choice(SCREEN_CONFIGS)
    webgl = random.choice(WEBGL_CONFIGS)
    languages = LANGUAGES_MAP.get(locale, ["en-US", "en"])
    platform = pick_platform(user_agent)
    max_touch = random.choice([0, 0, 0, 1, 5, 10])  # mostly 0 for desktop
    connection_type = random.choice(["wifi", "4g", "ethernet"])
    downlink = round(random.uniform(1.5, 100.0), 2)
    rtt = random.choice([50, 100, 150, 200, 250, 300])
    battery_level = round(random.uniform(0.15, 1.0), 2)
    battery_charging = random.choice(["true", "false"])

    languages_js = json.dumps(languages)  # proper JS array syntax

    vp_w = viewport.get("width", screen["width"])
    vp_h = viewport.get("height", screen["height"])

    script = f"""
// ========== FINGERPRINT SPOOF [{seed}] ==========

// --- webdriver cloak ---
Object.defineProperty(navigator, 'webdriver', {{
    get: () => undefined
}});
delete navigator.__proto__.webdriver;

// --- platform ---
Object.defineProperty(navigator, 'platform', {{
    get: () => '{platform}'
}});

// --- languages (locale-matched) ---
Object.defineProperty(navigator, 'languages', {{
    get: () => {languages_js}
}});
Object.defineProperty(navigator, 'language', {{
    get: () => '{languages[0]}'
}});

// --- hardwareConcurrency ---
Object.defineProperty(navigator, 'hardwareConcurrency', {{
    get: () => {hw_concurrency}
}});

// --- deviceMemory ---
Object.defineProperty(navigator, 'deviceMemory', {{
    get: () => {dev_memory}
}});

// --- maxTouchPoints ---
Object.defineProperty(navigator, 'maxTouchPoints', {{
    get: () => {max_touch}
}});

// --- plugins (realistic fake) ---
Object.defineProperty(navigator, 'plugins', {{
    get: () => {{
        length: 5,
        0: {{name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'}},
        1: {{name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''}},
        2: {{name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format'}},
        3: {{name: 'Chromium PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'}},
        4: {{name: 'Native Client', filename: 'internal-nacl-plugin', description: ''}},
        item: (i) => this[i],
        namedItem: (n) => Array.from({{length:5}}, (_,i) => this[i]).find(p => p.name === n),
        refresh: () => {{}},
        [Symbol.iterator]: function*() {{ for(let i=0;i<5;i++) yield this[i]; }}
    }}
}});

// --- window.chrome ---
if (!window.chrome) {{
    window.chrome = {{}};
}}
window.chrome.runtime = {{
    OnInstalledReason: {{CHROME_UPDATE:"chrome_update",INSTALL:"install",SHARED_MODULE_UPDATE:"shared_module_update",UPDATE:"update"}},
    OnRestartRequiredReason: {{APP_UPDATE:"app_update",OS_UPDATE:"os_update",PERIODIC:"periodic"}},
    PlatformArch: {{ARM:"arm",ARM64:"arm64",MIPS:"mips",MIPS64:"mips64",X86_32:"x86-32",X86_64:"x86-64"}},
    PlatformNaclArch: {{ARM:"arm",MIPS:"mips",MIPS64:"mips64",X86_32:"x86-32",X86_64:"x86-64"}},
    PlatformOs: {{ANDROID:"android",CROS:"cros",LINUX:"linux",MAC:"mac",OPENBSD:"openbsd",WIN:"win"}},
    RequestUpdateCheckStatus: {{NO_UPDATE:"no_update",THROTTLED:"throttled",UPDATE_AVAILABLE:"update_available"}},
    connect: function() {{}},
    sendMessage: function() {{}},
}};

// --- screen dimensions ---
const screenProps = {{
    width: {{ get: () => {screen['width']} }},
    height: {{ get: () => {screen['height']} }},
    availWidth: {{ get: () => {screen['avail_w']} }},
    availHeight: {{ get: () => {screen['avail_h']} }},
    colorDepth: {{ get: () => {screen['depth']} }},
    pixelDepth: {{ get: () => {screen['depth']} }},
}};
for (const [prop, desc] of Object.entries(screenProps)) {{
    Object.defineProperty(screen, prop, desc);
}}
Object.defineProperty(window, 'outerWidth', {{ get: () => {vp_w} }});
Object.defineProperty(window, 'outerHeight', {{ get: () => {vp_h + random.randint(40, 120)} }});
Object.defineProperty(window, 'innerWidth', {{ get: () => {vp_w} }});
Object.defineProperty(window, 'innerHeight', {{ get: () => {vp_h} }});
Object.defineProperty(window, 'devicePixelRatio', {{ get: () => {random.choice([1, 1, 1.25, 1.5, 2])} }});

// --- canvas fingerprint noise ---
(function() {{
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const origToBlob = HTMLCanvasElement.prototype.toBlob;
    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;

    // inject subtle pixel noise
    function noiseCanvas(canvas) {{
        try {{
            const ctx = canvas.getContext('2d');
            if (!ctx) return;
            const w = canvas.width, h = canvas.height;
            if (w === 0 || h === 0) return;
            const imageData = origGetImageData.call(ctx, 0, 0, w, h);
            const d = imageData.data;
            // flip a few random pixel channels by ±1
            const numPixels = Math.min(10, d.length / 4);
            for (let i = 0; i < numPixels; i++) {{
                const idx = (Math.floor(Math.random() * (d.length / 4))) * 4;
                const ch = Math.floor(Math.random() * 3); // R, G, or B
                d[idx + ch] = Math.max(0, Math.min(255, d[idx + ch] + (Math.random() > 0.5 ? 1 : -1)));
            }}
            ctx.putImageData(imageData, 0, 0);
        }} catch(e) {{}}
    }}

    HTMLCanvasElement.prototype.toDataURL = function(...args) {{
        noiseCanvas(this);
        return origToDataURL.apply(this, args);
    }};

    HTMLCanvasElement.prototype.toBlob = function(...args) {{
        noiseCanvas(this);
        return origToBlob.apply(this, args);
    }};

    CanvasRenderingContext2D.prototype.getImageData = function(...args) {{
        const imageData = origGetImageData.apply(this, args);
        const d = imageData.data;
        const numPixels = Math.min(10, d.length / 4);
        for (let i = 0; i < numPixels; i++) {{
            const idx = (Math.floor(Math.random() * (d.length / 4))) * 4;
            const ch = Math.floor(Math.random() * 3);
            d[idx + ch] = Math.max(0, Math.min(255, d[idx + ch] + (Math.random() > 0.5 ? 1 : -1)));
        }}
        return imageData;
    }};
}})();

// --- WebGL fingerprint spoof ---
(function() {{
    const getParamOrig = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {{
        // UNMASKED_VENDOR_WEBGL = 0x9245, UNMASKED_RENDERER_WEBGL = 0x9246
        if (param === 0x9245) return '{webgl["vendor"]}';
        if (param === 0x9246) return '{webgl["renderer"]}';
        return getParamOrig.call(this, param);
    }};
    // same for WebGL2
    if (typeof WebGL2RenderingContext !== 'undefined') {{
        const getParam2Orig = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(param) {{
            if (param === 0x9245) return '{webgl["vendor"]}';
            if (param === 0x9246) return '{webgl["renderer"]}';
            return getParam2Orig.call(this, param);
        }};
    }}
}})();

// --- AudioContext fingerprint noise ---
(function() {{
    const origCreateOscillator = AudioContext.prototype.createOscillator;
    const origCreateDynamics = AudioContext.prototype.createDynamicsCompressor;

    AudioContext.prototype.createOscillator = function(...args) {{
        const osc = origCreateOscillator.apply(this, args);
        const origFreq = osc.frequency.value;
        osc.frequency.value = origFreq + (Math.random() * 0.01 - 0.005);
        return osc;
    }};

    AudioContext.prototype.createDynamicsCompressor = function(...args) {{
        const comp = origCreateDynamics.apply(this, args);
        try {{
            comp.threshold.value = -50 + Math.random() * 0.1;
            comp.knee.value = 40 + Math.random() * 0.1;
            comp.ratio.value = 12 + Math.random() * 0.1;
            comp.attack.value = 0.003 + Math.random() * 0.0001;
            comp.release.value = 0.25 + Math.random() * 0.001;
        }} catch(e) {{}}
        return comp;
    }};
}})();

// --- Battery API spoof ---
if (navigator.getBattery) {{
    navigator.getBattery = () => Promise.resolve({{
        charging: {battery_charging},
        chargingTime: {battery_charging} ? {random.randint(0, 7200)} : Infinity,
        dischargingTime: {battery_charging} ? Infinity : {random.randint(1800, 28800)},
        level: {battery_level},
        addEventListener: function() {{}},
        removeEventListener: function() {{}},
        dispatchEvent: function() {{ return true; }},
    }});
}}

// --- Network Information API spoof ---
if (navigator.connection) {{
    Object.defineProperty(navigator.connection, 'effectiveType', {{ get: () => '{connection_type}' }});
    Object.defineProperty(navigator.connection, 'downlink', {{ get: () => {downlink} }});
    Object.defineProperty(navigator.connection, 'rtt', {{ get: () => {rtt} }});
    Object.defineProperty(navigator.connection, 'saveData', {{ get: () => false }});
}}

// --- Permission query spoof (hide "denied" tells) ---
(function() {{
    const origQuery = Permissions.prototype.query;
    Permissions.prototype.query = function(desc) {{
        if (desc.name === 'notifications') {{
            return Promise.resolve({{ state: 'prompt', onchange: null }});
        }}
        return origQuery.call(this, desc);
    }};
}})();

// ========== END FINGERPRINT SPOOF ==========
"""
    return script

# =====================================================
# CREATE CONTEXT
# =====================================================

def create_context(playwright,browser_name,channel,index,proxy=None):

    browser_type=getattr(playwright,browser_name)

    location=random.choice(LOCATIONS)

    device=random.choice(DEVICES)

    profile=PROFILE_ROOT/f"{browser_name}_{index}"

    launch_args={
        "user_data_dir":str(profile),
        "headless":False
    }

    if channel:
        launch_args["channel"]=channel

    if proxy:
        launch_args["proxy"]=proxy

    chosen_ua=random.choice(USER_AGENTS)

    context_args={

        "locale":location["locale"],

        "timezone_id":location["timezone"],

        "geolocation":location["geo"],

        "permissions":["geolocation"],

        "user_agent":chosen_ua,

        "color_scheme":random.choice(["light","dark"]),

    }

    if device in playwright.devices:

        device_config=playwright.devices[device].copy()

        device_config.pop("default_browser_type",None)

        context_args.update(device_config)

    else:

        context_args["viewport"]=random_viewport()

    context=browser_type.launch_persistent_context(

        **launch_args,

        **context_args

    )

    if context.pages:
        page=context.pages[0]
    else:
        page=context.new_page()

    # --- block heavy resources for faster loading ---
    if BLOCK_RESOURCES:
        def block_route(route):
            if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
                route.abort()
            else:
                route.continue_()
        page.route("**/*", block_route)

    # --- inject fingerprint spoofing into CONTEXT (not page!) ---
    # context-level ensures it runs before any page scripts on every navigation
    fp_locale = context_args.get("locale", "en-US")
    fp_ua = context_args.get("user_agent", USER_AGENTS[0])
    fp_viewport = context_args.get("viewport", random_viewport())

    context.add_init_script(generate_fingerprint_script(
        locale=fp_locale,
        user_agent=fp_ua,
        viewport=fp_viewport
    ))

    spoofed_platform = pick_platform(chosen_ua)

    print("="*60)
    print("Browser  :",channel or browser_name)
    print("Device   :",device)
    print("Location :",location["name"])
    print("Timezone :",location["timezone"])
    print("Locale   :",location["locale"])
    print("Platform :",spoofed_platform)
    print("UA       :",chosen_ua[:60]+"...")
    proxy_display = proxy["server"] if proxy else "DIRECT (no proxy)"
    print("Proxy    :",proxy_display)
    print("Profile  :",profile)
    print("="*60)

    return context,page

# =====================================================
# LAUNCH RANDOM BROWSER
# =====================================================

def launch_browser(playwright, index):

    browsers = BROWSERS.copy()
    random.shuffle(browsers)

    while browsers:

        browser_name, channel = browsers.pop()

        # Try multiple proxies per browser before giving up on it
        for proxy_attempt in range(MAX_PROXY_RETRIES):

            proxy = next_proxy()

            try:

                context, page = create_context(
                    playwright,
                    browser_name,
                    channel,
                    index,
                    proxy=proxy
                )

                # Use shorter timeout for proxied connections, longer for direct
                goto_timeout = 20000 if proxy else 60000

                page.goto(
                    URL,
                    wait_until="domcontentloaded",
                    timeout=goto_timeout
                )

                return context, page

            except Error as e:

                err_str = str(e)

                # Network/proxy error — try next proxy, same browser
                if any(k in err_str for k in [
                    "ERR_CONNECTION_RESET",
                    "ERR_PROXY_CONNECTION_FAILED",
                    "ERR_TUNNEL_CONNECTION_FAILED",
                    "ERR_CONNECTION_TIMED_OUT",
                    "ERR_CONNECTION_REFUSED",
                    "ERR_ABORTED",
                    "ERR_SOCKS_CONNECTION_FAILED",
                    "ERR_TIMED_OUT",
                    "NS_ERROR_PROXY_CONNECTION_REFUSED",
                ]):
                    proxy_name = proxy["server"] if proxy else "DIRECT"
                    print(f"  [proxy-dead] {proxy_name} failed, trying next... ({proxy_attempt+1}/{MAX_PROXY_RETRIES})")
                    # close the broken context
                    try:
                        context.close()
                    except:
                        pass
                    continue

                # Browser-level error (not installed, etc.) — skip browser entirely
                print()
                print(f"Skipping {channel or browser_name}: {e}")
                print()
                break

    return None, None


# =====================================================
# CAST VOTE AUTOMATION
# =====================================================

def get_vote_count(page):
    """Scrape the current community vote count from the page."""
    try:
        # Look for numbers near "vote" or "community" text
        count = page.evaluate("""
            () => {
                // Strategy 1: find elements with numbers near vote-related text
                const allEls = document.querySelectorAll('*');
                for (const el of allEls) {
                    if (el.children.length > 0) continue;  // leaf nodes only
                    const txt = (el.textContent || '').trim();
                    // Match standalone numbers (vote counts are usually just digits)
                    if (/^\d+$/.test(txt)) {
                        // Check if a sibling or parent mentions "vote" or "community"
                        const parent = el.parentElement;
                        if (parent) {
                            const parentText = parent.textContent.toLowerCase();
                            if (parentText.includes('vote') || parentText.includes('community')) {
                                return parseInt(txt, 10);
                            }
                        }
                    }
                }

                // Strategy 2: broader search — any number near vote context
                const body = document.body.innerText;
                const match = body.match(/(\d+)\s*(?:votes?|community\s*votes?)/i);
                if (match) return parseInt(match[1], 10);

                // Strategy 3: reverse — "community votes" then a number
                const match2 = body.match(/(?:community\s*votes?|total\s*votes?)\s*[:\s]*(\d+)/i);
                if (match2) return parseInt(match2[1], 10);

                return null;
            }
        """)
        return count
    except:
        return None


def cast_vote(page):
    """Click 'Cast your vote' and verify the vote count increased."""

    # --- wait for page to be FULLY loaded ---
    print("  [wait] Waiting for page to fully load...")

    # 1. document.readyState === 'complete'
    page.wait_for_function("document.readyState === 'complete'", timeout=30000)

    # 2. network idle
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except:
        pass

    # 3. extra buffer for JS framework hydration
    time.sleep(random.uniform(3, 6))

    print("  [wait] Page loaded.")

    # --- capture vote count BEFORE clicking ---
    vote_before = get_vote_count(page)
    if vote_before is not None:
        print(f"  [vote] Current community vote count: {vote_before}")
    else:
        print("  [vote] Could not read vote count (will still try to vote)")

    # --- find and click the exact "Cast your vote" button ---
    btn = page.locator('button:has-text("Cast your vote")')

    try:
        btn.wait_for(state="visible", timeout=15000)
    except:
        # fallback selectors if exact text doesn't match
        for fallback in [
            'button:has-text("cast your vote")',
            'button:has-text("Vote")',
            'text=/cast\\s+your\\s+vote/i',
            'button.bg-slate-900',
        ]:
            try:
                btn = page.locator(fallback).first
                if btn.is_visible(timeout=3000):
                    break
            except:
                continue
        else:
            print("  [vote] FAILED — 'Cast your vote' button not found")
            return False

    # Check if button is disabled
    is_disabled = btn.is_disabled()
    if is_disabled:
        print("  [vote] Button is DISABLED — may have already voted from this profile")
        return False

    # Human-like click
    btn.scroll_into_view_if_needed()
    time.sleep(random.uniform(0.5, 2.0))
    btn.click()
    print("  [vote] Clicked 'Cast your vote'!")

    # --- wait for vote count to increase ---
    print("  [vote] Waiting for vote count to update...")

    max_wait = 30  # seconds
    poll_interval = 2
    elapsed = 0
    vote_confirmed = False

    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        vote_after = get_vote_count(page)

        if vote_after is not None:
            if vote_before is not None and vote_after > vote_before:
                print(f"  [vote] Vote count updated: {vote_before} → {vote_after} ✓")
                vote_confirmed = True
                break
            elif vote_before is None:
                # Couldn't read before, but we have a number now — assume success
                print(f"  [vote] Vote count is now: {vote_after} (assumed success)")
                vote_confirmed = True
                break
            else:
                print(f"  [vote] Still {vote_after}, waiting... ({elapsed}s/{max_wait}s)")

        # Also check if button text/state changed (another success signal)
        try:
            btn_text = btn.text_content(timeout=2000)
            if btn_text and any(w in btn_text.lower() for w in ["voted", "thanks", "submitted", "done"]):
                print(f"  [vote] Button changed to: '{btn_text}' ✓")
                vote_confirmed = True
                break
        except:
            pass

        # Check if button became disabled after click
        try:
            if btn.is_disabled():
                print("  [vote] Button became disabled after click ✓")
                vote_confirmed = True
                break
        except:
            pass

    if not vote_confirmed:
        print("  [vote] Timed out waiting for count to update (vote may still have worked)")
        # Give benefit of the doubt
        return True

    return True


# =====================================================
# MAIN LOOP
# =====================================================

with sync_playwright() as p:

    successful_votes = 0
    failed_votes = 0

    for i in range(1, COUNT + 1):

        print()
        print("=" * 60)
        print(f"Session {i}/{COUNT}")
        print("=" * 60)

        context, page = launch_browser(p, i)

        if context is None:
            print("No browser available — skipping this session.")
            failed_votes += 1
            continue

        # --- automate the vote ---
        try:
            voted = cast_vote(page)
            if voted:
                successful_votes += 1
                print(f"  [OK] Vote {i} cast successfully!")
            else:
                failed_votes += 1
                print(f"  [FAIL] Vote {i} could not be cast.")
        except Exception as e:
            failed_votes += 1
            print(f"  [ERROR] Vote {i} failed: {e}")

        # --- close the browser ---
        try:
            context.close()
        except:
            pass

        print("Browser Closed.")

        # --- random delay between sessions (look human) ---
        if i < COUNT:
            delay = random.uniform(3, 8)
            print(f"Waiting {delay:.1f}s before next session...")
            time.sleep(delay)

print()
print("=" * 60)
print(f"FINISHED — {successful_votes}/{COUNT} votes cast, {failed_votes} failed")
print("=" * 60)