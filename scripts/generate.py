"""Generate the animated SVG sections for the profile README.

Pulls live data (profile, repos, languages, contribution calendar, avatar, snake)
and writes self-contained, CSS/SMIL-animated SVGs into ../assets.
Run locally or from .github/workflows/profile.yml. Needs Pillow and fonttools.
"""
import base64, hashlib, html, textwrap, io, json, math, os, re, urllib.request
from datetime import date, datetime
from PIL import Image, ImageEnhance

USER = "SaTyAbHr2005"
NAME = "Satyaranjan Behera"
TOKEN = os.environ.get("GITHUB_TOKEN")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
esc = html.escape

# GitHub dark palette (Primer)
BG, PANEL, BORDER = "#0d1117", "#161b22", "#30363d"
TEXT, MUTED = "#e6edf3", "#7d8590"
GREEN, BLUE, PURPLE, YELLOW = "#3fb950", "#58a6ff", "#a371f7", "#d29922"
LEVELS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
DISP = "MonaSans,'Mona Sans','Segoe UI',Helvetica,Arial,sans-serif"
MONO_W = 0.62  # Monaspace advance width, in em
MONO = "Monaspace,ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

# ---------------------------------------------------------------- data

def get(url, raw=False):
    h = {"User-Agent": "profile-gen"}
    if TOKEN and "api.github.com" in url:
        h["Authorization"] = "Bearer " + TOKEN
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
        d = r.read()
    return d if raw else json.loads(d)


def contributions():
    page = get(f"https://github.com/users/{USER}/contributions", raw=True).decode()
    counts = {}
    for cid, tip in re.findall(r'for="(contribution-day-component-[\d-]+)"[^>]*>([^<]*)', page):
        first = tip.strip().split(" ")[0]
        counts[cid] = 0 if first == "No" else int(first.replace(",", ""))
    days = []
    for td in re.findall(r"<td[^>]*data-date=[^>]*>", page):
        d = re.search(r'data-date="([\d-]+)"', td).group(1)
        cid = re.search(r'id="([^"]+)"', td).group(1)
        days.append({"date": d, "count": counts.get(cid, 0)})
    return sorted(days, key=lambda x: x["date"])


def streaks(days):
    seq = [d["count"] for d in days if d["date"] <= date.today().isoformat()]
    longest = run = 0
    for c in seq:
        run = run + 1 if c else 0
        longest = max(longest, run)
    cur, i = 0, len(seq) - 1
    if i >= 0 and seq[i] == 0:  # today may not have activity yet
        i -= 1
    while i >= 0 and seq[i]:
        cur, i = cur + 1, i - 1
    return cur, longest


def load():
    user = get(f"https://api.github.com/users/{USER}")
    repos = [r for r in get(f"https://api.github.com/users/{USER}/repos?per_page=100") if not r["fork"]]
    langs = {}
    for r in repos:
        for k, v in get(r["languages_url"]).items():
            langs[k] = langs.get(k, 0) + v
    days = contributions()
    cur, longest = streaks(days)
    avatar = Image.open(io.BytesIO(get(user["avatar_url"] + "&s=460", raw=True))).convert("RGB")
    snake = get(f"https://raw.githubusercontent.com/{USER}/{USER}/output/github-contribution-grid-snake.svg", raw=True).decode()
    return {"user": user, "repos": repos, "langs": langs, "avatar": avatar, "snake": snake,
            "stars": sum(r["stargazers_count"] for r in repos), "total": sum(d["count"] for d in days),
            "streak": cur, "longest": longest, "active": sum(1 for d in days if d["count"])}

# ---------------------------------------------------------------- fonts (GitHub's own: Mona Sans + Monaspace)

FONT_URLS = {
    "MonaSans": ("https://raw.githubusercontent.com/github/mona-sans/HEAD/fonts/variable/MonaSansVF%5Bopsz%2Cwght%5D.ttf", 800),
    "Monaspace": ("https://raw.githubusercontent.com/githubnext/monaspace/HEAD/fonts/Frozen%20Fonts/Monaspace%20Neon/MonaspaceNeonFrozen-Regular.ttf", None),
}
GLYPHS = "".join(chr(c) for c in range(32, 127)) + "·◆●○✓→←▸█─│┌┐└┘├┤━•…↗%"


def font_css():
    from fontTools import subset
    from fontTools.ttLib import TTFont
    css = ""
    for fam, (url, wght) in FONT_URLS.items():
        f = TTFont(io.BytesIO(get(url, raw=True)))
        if wght and "fvar" in f:
            from fontTools.varLib import instancer
            axes = {a.axisTag: a.defaultValue for a in f["fvar"].axes}
            axes.update(wght=wght, **({"opsz": 72} if "opsz" in axes else {}))
            f = instancer.instantiateVariableFont(f, axes)
        opts = subset.Options()
        opts.flavor, opts.layout_features, opts.name_IDs = "woff", ["kern", "liga"], []
        s = subset.Subsetter(opts)
        s.populate(text=GLYPHS)
        s.subset(f)
        buf = io.BytesIO()
        f.flavor = "woff"
        f.save(buf)
        css += f"@font-face{{font-family:{fam};src:url(data:font/woff;base64,{base64.b64encode(buf.getvalue()).decode()}) format('woff')}}"
    return css

# ---------------------------------------------------------------- svg helpers

BASE_CSS = """
@keyframes reveal{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes flow{to{stroke-dashoffset:-104}}
@keyframes pulse{50%{opacity:.3}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes unspin{to{transform:rotate(-360deg)}}
@keyframes draw{0%{stroke-dashoffset:1}30%,88%{stroke-dashoffset:0}100%{stroke-dashoffset:-1}}
@keyframes blink{50%{opacity:0}}
.reveal{animation:reveal .9s cubic-bezier(.2,.7,.2,1) backwards}
.flow{animation:flow 5s linear infinite}.pulse{animation:pulse 2.8s ease-in-out infinite}
.draw{stroke-dasharray:1;animation:draw 9s ease-in-out infinite}.blink{animation:blink 1.1s steps(1) infinite}
"""
REDUCED = "@media(prefers-reduced-motion:reduce){*{animation:none!important}}"
FONTS = ""


def svg(w, h, title, body, css="", defs=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">'
            f"<title>{esc(title)}</title><defs>"
            f'<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="{MUTED}" fill-opacity=".18"/></pattern>'
            f'<linearGradient id="ink" x1="0" y1="0" x2="1" y2="0"><stop stop-color="{GREEN}"/><stop offset=".55" stop-color="{BLUE}"/><stop offset="1" stop-color="{PURPLE}"/></linearGradient>'
            f"{defs}</defs><style>{FONTS if 'font-family' in body else ''}{BASE_CSS}{css}{REDUCED}</style>{body}</svg>")


def card(w, h):
    return (f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="12" fill="{BG}" stroke="{BORDER}"/>'
            f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="12" fill="url(#dots)"/>')


def header(eyebrow, title, w, right=f"@{USER}"):
    return (f'<text x="40" y="46" fill="{MUTED}" font-family="{MONO}" font-size="11" letter-spacing="2.5">{esc(eyebrow)}</text>'
            f'<text x="{w-40}" y="46" text-anchor="end" fill="{MUTED}" font-family="{MONO}" font-size="11">{esc(right)}</text>'
            f'<text x="40" y="88" fill="{TEXT}" font-family="{DISP}" font-size="30" font-weight="800">{esc(title)}</text>')


def window(w, h, title):
    return (f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="12" fill="{BG}" stroke="{BORDER}"/>'
            f'<path d="M.5 12.5a12 12 0 0 1 12-12h{w-25}a12 12 0 0 1 12 12v24H.5z" fill="{PANEL}"/><path d="M.5 36.5H{w-.5}" stroke="{BORDER}"/>'
            f'<circle cx="22" cy="18.5" r="6" fill="#ff5f57"/><circle cx="42" cy="18.5" r="6" fill="#febc2e"/><circle cx="62" cy="18.5" r="6" fill="#28c840"/>'
            f'<text x="{w/2}" y="23" text-anchor="middle" fill="{MUTED}" font-family="{MONO}" font-size="12">{esc(title)}</text>')


def seq_css(prefix, n, period, start, step, hold=0.93):
    """Per-item keyframes: lines appear one at a time, hold, then the whole cycle loops."""
    out = []
    for i in range(n):
        a = (start + i * step) / period * 100
        out.append(f"@keyframes {prefix}{i}{{0%,{a:.2f}%{{opacity:0;transform:translateX(-8px)}}"
                   f"{a+1.8:.2f}%,{hold*100:.0f}%{{opacity:1;transform:none}}100%{{opacity:0}}}}"
                   f".{prefix}{i}{{animation:{prefix}{i} {period}s linear infinite}}")
    return "".join(out)


def odometer(x, y, value, size, uid, delay=0.0, color=TEXT):
    """Rolling-digit counter. Monospace digits share one advance width, so positions are exact."""
    s, cw, lh = f"{value:,}", size * MONO_W, size * 1.15
    out = f'<clipPath id="o{uid}"><rect x="{x-2}" y="{y-size}" width="{len(s)*cw+4:.0f}" height="{lh:.1f}"/></clipPath><g clip-path="url(#o{uid})" font-family="{MONO}" font-size="{size}" fill="{color}" font-weight="700">'
    for i, ch in enumerate(s):
        cx = x + i * cw
        if not ch.isdigit():
            out += f'<text x="{cx:.1f}" y="{y}">{ch}</text>'
            continue
        col = "".join(f'<text x="{cx:.1f}" y="{y+k*lh:.1f}">{k % 10}</text>' for k in range(10 + int(ch) + 1))
        out += f'<g class="roll r{ch}" transform="translate(0 -{(10+int(ch))*lh:.1f})" style="animation-delay:{delay+i*.12:.2f}s">{col}</g>'
    return out + "</g>"


def odometer_css(size):
    lh = size * 1.15
    return "".join(f"@keyframes r{d}{{0%{{transform:translateY(0)}}28%,88%{{transform:translateY(-{(10+d)*lh:.1f}px)}}100%{{transform:translateY(-{(10+d)*lh:.1f}px)}}}}"
                   f".r{d}{{animation:r{d} 9s cubic-bezier(.3,.1,.2,1) infinite backwards}}" for d in range(10))


def true_color(rgb):
    """Original avatar colour, with dim pixels lifted so they read on a dark card."""
    m = max(rgb) or 1
    k = max(1.0, 170 / m)
    return "#%02x%02x%02x" % tuple(min(255, int(c * k)) for c in rgb)


def lum(rgb):
    r, g, b = rgb
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255

# ---------------------------------------------------------------- sections

def hero(d):
    W, H = 1000, 600
    u = d["user"]
    # avatar rebuilt from contribution-graph squares
    N, P, S = 48, 8, 6.4
    im = ImageEnhance.Color(ImageEnhance.Contrast(d["avatar"]).enhance(1.3)).enhance(1.5).resize((N, N), Image.LANCZOS)
    ox, oy = 572, 104
    cells = []
    for y in range(N):
        for x in range(N):
            px = im.getpixel((x, y))
            if lum(px) >= .14:
                cells.append(f'<rect class="k d{(x+y)//4}" x="{ox+x*P}" y="{oy+y*P}" width="{S}" height="{S}" rx="1.4" fill="{true_color(px)}"/>')
    grid = (f'<pattern id="empty" x="{ox}" y="{oy}" width="{P}" height="{P}" patternUnits="userSpaceOnUse">'
            f'<rect width="{S}" height="{S}" rx="1.4" fill="{PANEL}"/></pattern>')
    diag = "".join(f".d{i}{{animation-delay:{i*.07:.2f}s,{2.4+i*.09:.2f}s}}" for i in range(N // 2 + 1))
    words = ["AI systems.", "vision models.", "secure stacks.", "real products."]
    T = 12
    word_svg = "".join(f'<text class="w{" first" if i == 0 else ""}" style="animation-delay:{i*T/len(words)-.1*T-T:.1f}s" x="40" y="272" fill="url(#shine)" font-family="{DISP}" font-size="60" font-weight="800">{esc(w)}</text>' for i, w in enumerate(words))
    states = ["TRAINING", "BUILDING", "SHIPPING", "LEARNING"]
    state_svg = "".join(f'<text class="st{" first" if i == 0 else ""}" style="animation-delay:{i*2-8.8:.1f}s" x="{W-40}" y="46" text-anchor="end" fill="{GREEN}" font-family="{MONO}" font-size="11" letter-spacing="2">{s}</text>' for i, s in enumerate(states))
    tick = "  ◆  ".join(["PYTHON", "PYTORCH", "TENSORFLOW", "OPENCV", "SCIKIT-LEARN", "FASTAPI", "NODE.JS", "REACT", "NEXT.JS", "MONGODB", "POSTGRES", "DOCKER", "AWS"]) + "  ◆  "
    tw = len(tick) * 12 * MONO_W
    chips = ""
    for i, (v, lab) in enumerate([(len(d["repos"]), "REPOSITORIES"), (d["total"], "CONTRIBUTIONS"), (d["longest"], "BEST STREAK"), (u["followers"], "FOLLOWERS")]):
        x = 40 + i * 126
        chips += (f'<g class="reveal" style="animation-delay:{1.4+i*.12:.2f}s"><rect x="{x}" y="414" width="114" height="76" rx="8" fill="{PANEL}" stroke="{BORDER}"/>'
                  + odometer(x + 14, 452, v, 24, f"h{i}", 1.6 + i * .2) +
                  f'<text x="{x+14}" y="476" fill="{MUTED}" font-family="{MONO}" font-size="8.5" letter-spacing="1">{lab}</text></g>')
    css = (odometer_css(24) +
           "@keyframes in{from{opacity:0;transform:scale(.2)}to{opacity:1;transform:none}}"
           "@keyframes wave{0%,100%{opacity:1}6%{opacity:.25}12%{opacity:1}}"
           ".k{transform-box:fill-box;transform-origin:center;animation:in .5s cubic-bezier(.2,.8,.2,1.2) backwards,wave 7s ease-in-out infinite}" + diag +
           f"@keyframes w{{0%{{opacity:0;transform:translateY(60px)}}4%,22%{{opacity:1;transform:none}}26%,100%{{opacity:0;transform:translateY(-60px)}}}}.w{{opacity:0;animation:w {T}s cubic-bezier(.7,0,.2,1) infinite}}.first{{opacity:1}}"
           "@keyframes st{0%{opacity:0}3%,22%{opacity:1}25%,100%{opacity:0}}.st{opacity:0;animation:st 8s steps(1) infinite}"
           f"@keyframes tick{{to{{transform:translateX(-{tw:.1f}px)}}}}.tick{{animation:tick 40s linear infinite}}"
           "@keyframes scan{0%{transform:translateY(0);opacity:0}5%{opacity:1}45%{transform:translateY(384px);opacity:0}100%{opacity:0}}.scan{animation:scan 6s linear infinite}")
    defs = (grid + f'<clipPath id="wc"><rect x="30" y="206" width="540" height="82"/></clipPath>'
            f'<linearGradient id="shine" x1="0" y1="0" x2="1" y2="0" spreadMethod="reflect"><stop stop-color="{GREEN}"/><stop offset=".5" stop-color="{BLUE}"/><stop offset="1" stop-color="{PURPLE}"/>'
            f'<animateTransform attributeName="gradientTransform" type="translate" values="0 0;1 0;0 0" dur="8s" repeatCount="indefinite"/></linearGradient>'
            f'<linearGradient id="beam" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity=".22"/></linearGradient>'
            f'<clipPath id="tc"><rect x="1" y="{H-52}" width="{W-2}" height="51"/></clipPath>')
    body = (card(W, H) +
            f'<text x="40" y="46" fill="{MUTED}" font-family="{MONO}" font-size="11" letter-spacing="2.5">SB / {NAME.upper()}</text>'
            f'<circle class="pulse" cx="{W-128}" cy="42" r="4" fill="{GREEN}"/>{state_svg}'
            f'<g class="reveal" style="animation-delay:.1s"><text x="40" y="196" fill="{TEXT}" font-family="{DISP}" font-size="60" font-weight="800">I build</text></g>'
            f'<g clip-path="url(#wc)">{word_svg}</g>'
            f'<g class="reveal" style="animation-delay:.6s"><text x="40" y="330" fill="{TEXT}" font-family="{MONO}" font-size="14">{esc(NAME)} <tspan fill="{MUTED}">— AI/ML · Software Engineer</tspan></text>'
            f'<text x="40" y="356" fill="{MUTED}" font-family="{MONO}" font-size="13">{esc(u.get("location") or "Mumbai")}, India · B.E. Computer Engineering \'27</text></g>'
            f'<g class="reveal" style="animation-delay:.9s"><rect x="40" y="374" width="138" height="24" rx="12" fill="{GREEN}" fill-opacity=".12" stroke="{GREEN}" stroke-opacity=".5"/>'
            f'<circle class="pulse" cx="56" cy="386" r="4" fill="{GREEN}"/><text x="66" y="390" fill="{GREEN}" font-family="{MONO}" font-size="10.5" letter-spacing="1.5">OPEN TO WORK</text></g>'
            + chips +
            f'<rect x="{ox}" y="{oy}" width="{N*P}" height="{N*P}" fill="url(#empty)"/>{"".join(cells)}'
            f'<rect class="scan" x="{ox-6}" y="{oy-40}" width="{N*P+12}" height="40" fill="url(#beam)" opacity="0"/>'
            ''
            f'<path d="M1 {H-52}H{W-1}" stroke="{BORDER}"/>'
            f'<g clip-path="url(#tc)"><g class="tick" font-family="{MONO}" font-size="12" letter-spacing="0" fill="{MUTED}">'
            f'<text x="20" y="{H-21}">{esc(tick*2)}</text><text x="{20+2*tw:.1f}" y="{H-21}">{esc(tick*2)}</text></g></g>')
    return svg(W, H, f"{NAME}", body, css, defs)


BANNER = {
    "S": ["███████╗", "██╔════╝", "███████╗", "╚════██║", "███████║", "╚══════╝"],
    "A": [" █████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
    "T": ["████████╗", "╚══██╔══╝", "   ██║   ", "   ██║   ", "   ██║   ", "   ╚═╝   "],
    "Y": ["██╗   ██╗", "╚██╗ ██╔╝", " ╚████╔╝ ", "  ╚██╔╝  ", "   ██║   ", "   ╚═╝   "],
    "R": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"],
    "N": ["███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║", "██║ ╚████║", "╚═╝  ╚═══╝"],
    "J": ["     ██╗", "     ██║", "     ██║", "██   ██║", "╚█████╔╝", " ╚════╝ "],
    "B": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██████╔╝", "╚═════╝ "],
    "E": ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"],
    "H": ["██╗  ██╗", "██║  ██║", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
}


def banner(word):
    return ["".join(BANNER[ch][i] for ch in word) for i in range(6)]


def shadow_path(ch, x, y, cw, chh):
    x1, x2, y1, y2 = x + cw * .32, x + cw * .68, y + chh * .36, y + chh * .64
    r, b = x + cw, y + chh
    return {"═": f"M{x} {y1}H{r}M{x} {y2}H{r}", "║": f"M{x1} {y}V{b}M{x2} {y}V{b}",
            "╗": f"M{x} {y1}H{x2}V{b}M{x} {y2}H{x1}V{b}", "╔": f"M{r} {y1}H{x1}V{b}M{r} {y2}H{x2}V{b}",
            "╝": f"M{x} {y2}H{x2}V{y}M{x} {y1}H{x1}V{y}", "╚": f"M{r} {y2}H{x1}V{y}M{r} {y1}H{x2}V{y}"}.get(ch, "")


def wordmark(_d):
    W, cw, chh = 1000, 9.6, 17
    lines = [banner("SATYARANJAN"), banner("BEHERA")]
    H = 74 + len(lines) * 6 * chh + 26 + 64
    blocks, shadows = [], []
    for li, rows in enumerate(lines):
        ox, oy = (W - len(rows[0]) * cw) / 2, 74 + li * (6 * chh + 26)
        for ri, row in enumerate(rows):
            y = oy + ri * chh
            for m in re.finditer("█+", row):
                x = ox + m.start() * cw
                blocks.append(f'<rect class="b" style="animation-delay:{(x-ox)/900*1.6+li*.4:.2f}s" x="{x:.1f}" y="{y:.1f}" width="{len(m.group())*cw+.4:.1f}" height="{chh+.4:.1f}"/>')
            shadows += [shadow_path(ch, round(ox + ci * cw, 1), round(y, 1), cw, chh) for ci, ch in enumerate(row)]
    css = ("@keyframes b{0%{opacity:0;transform:translateY(-26px)}6%,86%{opacity:1;transform:none}92%,100%{opacity:0;transform:translateY(18px)}}"
           ".b{animation:b 11s cubic-bezier(.3,1.4,.4,1) infinite backwards}"
           "@keyframes sh{0%,6%{opacity:0}14%,86%{opacity:1}92%,100%{opacity:0}}.sh{animation:sh 11s linear infinite}")
    defs = (f'<linearGradient id="shine" x1="0" y1="0" x2="1" y2="0" spreadMethod="reflect"><stop stop-color="{GREEN}"/><stop offset=".45" stop-color="{BLUE}"/><stop offset=".85" stop-color="{PURPLE}"/><stop offset="1" stop-color="{GREEN}"/>'
            f'<animateTransform attributeName="gradientTransform" type="translate" values="0 0;1 0" dur="6s" repeatCount="indefinite"/></linearGradient>')
    body = (window(W, H, "satya@github: ~$ figlet \"Satyaranjan Behera\"") +
            f'<path class="sh" d="{"".join(shadows)}" fill="none" stroke="{MUTED}" stroke-opacity=".8" stroke-width="1.1"/>'
            f'<g fill="url(#shine)">{"".join(blocks)}</g>'
            f'<text x="{W/2}" y="{H-24}" text-anchor="middle" fill="{MUTED}" font-family="{MONO}" font-size="11" letter-spacing="4">AI/ML · SOFTWARE ENGINEER · MUMBAI<tspan class="blink" fill="{GREEN}"> █</tspan></text>')
    return svg(W, H, f"{NAME} wordmark", body, css, defs)


def terminal(d):
    """A 'training run' on me: animated epochs instead of a list that repeats the stack section."""
    W, H = 1000, 384
    live = sum(1 for c in CARDS if "LIVE" in c[4])
    epochs = [("0.842", "idea → prototype"), ("0.417", "prototype → product"),
              ("0.163", "break → rebuild"), ("0.041", "ship → learn → repeat")]
    T, start, step = 16, 1.6, .75
    lines = [
        f'<tspan fill="{MUTED}">loading dataset · </tspan>{len(d["repos"])} repos<tspan fill="{MUTED}"> · </tspan>{d["total"]:,} contributions<tspan fill="{MUTED}"> · </tspan>{live} live deployments',
        f'<tspan fill="{MUTED}">config · optimizer: </tspan><tspan fill="{PURPLE}">build-break-rebuild</tspan><tspan fill="{MUTED}"> · fuel: </tspan><tspan fill="{PURPLE}">curiosity</tspan>',
    ]
    bx, bw = 190, 230
    rows, css = "", seq_css("l", 2 + len(epochs) + 2, T, start, step)
    for i, l in enumerate(lines):
        rows += f'<g class="l{i}"><text x="40" y="{108+i*30}" font-size="14" fill="{TEXT}">{l}</text></g>'
    for k, (loss, note) in enumerate(epochs):
        i, y = 2 + k, 108 + (2 + k) * 30
        a = (start + i * step) / T * 100
        css += (f"@keyframes f{k}{{0%,{a:.2f}%{{transform:scaleX(0)}}{a+4.5:.2f}%,100%{{transform:scaleX(1)}}}}"
                f".f{k}{{transform-box:fill-box;transform-origin:left;animation:f{k} {T}s cubic-bezier(.4,0,.2,1) infinite}}")
        rows += (f'<g class="l{i}"><text x="40" y="{y}" font-size="14" fill="{TEXT}">Epoch {k+1}/{len(epochs)}</text>'
                 f'<rect x="{bx}" y="{y-11}" width="{bw}" height="12" rx="3" fill="{PANEL}" stroke="{BORDER}"/>'
                 f'<rect class="f{k}" x="{bx}" y="{y-11}" width="{bw}" height="12" rx="3" fill="url(#ink)"/>'
                 f'<text x="{bx+bw+14}" y="{y}" font-size="14" fill="{TEXT}">100% <tspan fill="{MUTED}">loss</tspan> {loss}</text>'
                 f'<text x="{bx+bw+190}" y="{y}" font-size="14" fill="{BLUE}">· {esc(note)}</text></g>')
    n = 2 + len(epochs)
    rows += (f'<g class="l{n}"><text x="40" y="{108+n*30}" font-size="14"><tspan fill="{GREEN}">✓ converged</tspan>'
             f'<tspan fill="{MUTED}"> · checkpoint saved → </tspan><tspan fill="{TEXT}">satyaranjan.vercel.app</tspan></text></g>'
             f'<g class="l{n+1}"><text x="40" y="{108+(n+1)*30}" font-size="14"><tspan fill="{MUTED}">status: </tspan>'
             f'<tspan fill="{GREEN}">● open to work</tspan><tspan fill="{MUTED}"> · {esc((d["user"].get("location") or "Mumbai") + ", India")}</tspan></text></g>')
    defs = (f'<clipPath id="cmd"><rect x="58" y="56" height="20" width="0"><animate attributeName="width" values="0;0;560;560" keyTimes="0;.02;.09;1" dur="{T}s" repeatCount="indefinite"/></rect></clipPath>')
    body = (window(W, H, "satya@github: ~/career") + f'<g font-family="{MONO}">'
            f'<text x="40" y="70" font-size="14" fill="{GREEN}">➜</text><text x="60" y="70" font-size="14" fill="{TEXT}" clip-path="url(#cmd)">python train.py --model satyaranjan --epochs {len(epochs)}</text>'
            f'{rows}<text x="40" y="{H-26}" font-size="14"><tspan fill="{GREEN}">➜</tspan><tspan class="blink" fill="{TEXT}"> █</tspan></text></g>')
    return svg(W, H, "Training run", body, css, defs)


LANG_COLORS = {"Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "C++": "#f34b7d", "HTML": "#e34c26",
               "CSS": "#663399", "Jupyter Notebook": "#DA5B0B", "C": "#555555", "Java": "#b07219", "R": "#198CE7", "Shell": "#89e051"}
RINGS = [("ML / AI", GREEN, 80, 34, ["python", "pytorch", "tensorflow", "scikitlearn", "opencv"]),
         ("BACKEND", BLUE, 136, -48, ["fastapi", "nodedotjs", "express", "mongodb", "postgresql", "apachekafka"]),
         ("FRONTEND", PURPLE, 192, 64, ["react", "nextdotjs", "typescript", "tailwindcss", "vite", "javascript"]),
         ("DEVOPS", YELLOW, 248, -84, ["docker", "git", "githubactions", "vercel", "render", "linux"])]
TITLES = {"nodedotjs": "Node.js", "nextdotjs": "Next.js", "scikitlearn": "scikit-learn", "apachekafka": "Kafka",
          "postgresql": "PostgreSQL", "githubactions": "GH Actions", "tailwindcss": "Tailwind", "opencv": "OpenCV",
          "pytorch": "PyTorch", "tensorflow": "TensorFlow", "fastapi": "FastAPI", "mongodb": "MongoDB", "typescript": "TypeScript",
          "javascript": "JavaScript"}


def icon_path(slug):
    try:
        raw = get(f"https://cdn.jsdelivr.net/npm/simple-icons@13/icons/{slug}.svg", raw=True).decode()
        return re.search(r' d="([^"]+)"', raw).group(1)
    except Exception:
        return None


def stack(d):
    W, H, cx, cy = 1000, 700, 650, 330
    orbit, legend = "", ""
    for ri, (cat, col, r, dur, slugs) in enumerate(RINGS):
        direction = "normal" if dur > 0 else "reverse"
        dur = abs(dur)
        orbit += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{col}" stroke-opacity=".28" stroke-dasharray="{"3 6" if ri % 2 else "none"}"/>'
        g = ""
        for i, slug in enumerate(slugs):
            a = 2 * math.pi * i / len(slugs) + ri * .5
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            p = icon_path(slug)
            ic = (f'<path d="{p}" fill="{TEXT}" transform="translate({x-9:.1f} {y-9:.1f}) scale(.75)"/>' if p
                  else f'<text x="{x:.1f}" y="{y+4:.1f}" text-anchor="middle" fill="{TEXT}" font-family="{MONO}" font-size="10">{slug[:2]}</text>')
            g += (f'<g class="up" style="animation-duration:{dur}s;animation-direction:{direction}">'
                  f'<circle cx="{x:.1f}" cy="{y:.1f}" r="19" fill="{PANEL}" stroke="{col}" stroke-opacity=".7"/>{ic}</g>')
        orbit += f'<g class="ring" style="animation-duration:{dur}s;animation-direction:{direction}">{g}</g>'
        ly = 150 + ri * 92
        names = " · ".join(TITLES.get(s, s.capitalize()) for s in slugs)
        legend += (f'<g class="reveal" style="animation-delay:{.2+ri*.15:.2f}s"><circle cx="48" cy="{ly-4}" r="5" fill="{col}"/>'
                   f'<text x="62" y="{ly}" fill="{TEXT}" font-family="{MONO}" font-size="12" letter-spacing="2">0{ri+1} · {cat}</text>'
                   + "".join(f'<text x="62" y="{ly+22+j*16}" fill="{MUTED}" font-family="{MONO}" font-size="10.5">{esc(t)}</text>' for j, t in enumerate(textwrap.wrap(names, 44)))
                   + "</g>")
    core = (f'<circle cx="{cx}" cy="{cy}" r="40" fill="{PANEL}" stroke="url(#ink)" stroke-width="1.5"/>'
            f'<circle class="pulse" cx="{cx}" cy="{cy}" r="48" fill="none" stroke="{GREEN}" stroke-opacity=".4"/>'
            f'<text x="{cx}" y="{cy+8}" text-anchor="middle" fill="{TEXT}" font-family="{DISP}" font-size="24" font-weight="800">SB</text>')
    total = sum(d["langs"].values()) or 1
    top = sorted(d["langs"].items(), key=lambda kv: -kv[1])[:6]
    rest = total - sum(v for _, v in top)
    segs = top + ([("Other", rest)] if rest > 0 else [])
    bx, bw, by = 40, W - 80, H - 76
    bar, leg, x = "", "", bx
    for i, (k, v) in enumerate(segs):
        w = bw * v / total
        bar += f'<rect class="seg" style="animation-delay:{.8+i*.1:.1f}s" x="{x:.1f}" y="{by}" width="{max(w-2,1):.1f}" height="8" fill="{LANG_COLORS.get(k, MUTED)}"/>'
        x += w
    lx = bx
    for k, v in segs:
        leg += (f'<circle cx="{lx+5}" cy="{by+33}" r="5" fill="{LANG_COLORS.get(k, MUTED)}"/>'
                f'<text x="{lx+16}" y="{by+37}" font-family="{MONO}" font-size="11.5" fill="{TEXT}">{esc(k)} <tspan fill="{MUTED}">{v/total*100:.1f}%</tspan></text>')
        lx += 16 + (len(k) + 7) * 11.5 * MONO_W + 18
    css = (".ring{transform-origin:%dpx %dpx;animation:spin linear infinite}.up{transform-box:fill-box;transform-origin:center;animation:unspin linear infinite}"
           "@keyframes grow{from{transform:scaleX(0)}}.seg{transform-box:fill-box;transform-origin:left;animation:grow 1s cubic-bezier(.2,.7,.2,1) backwards}" % (cx, cy))
    defs = f'<clipPath id="barc"><rect x="{bx}" y="{by}" width="{bw}" height="8" rx="4"/></clipPath>'
    body = (card(W, H) + header("TECH STACK · IN ORBIT", "The tools behind the work", W) + orbit + core + legend +
            f'<text x="40" y="{by-14}" fill="{MUTED}" font-family="{MONO}" font-size="11" letter-spacing="2">LANGUAGES · ACROSS PUBLIC REPOS</text>'
            f'<g clip-path="url(#barc)"><rect x="{bx}" y="{by}" width="{bw}" height="8" fill="{PANEL}"/>{bar}</g>{leg}')
    return svg(W, H, "Tech stack", body, css, defs)


PROJECTS = [  # name, tag, angle (deg, clockwise from east), radius fraction
    ("AirInsight", "air quality · CatBoost · IEEE paper", 25, .55),
    ("CrowdWatch AI", "crowd safety · computer vision", 75, .82),
    ("AutoSOC", "attack graphs · vuln scanning", 130, .45),
    ("SENTRIX", "data-exposure threat intel", 185, .78),
    ("EnergySense", "energy forecasting · big data", 235, .5),
    ("AutoStylist", "AI wardrobe & outfit agent", 290, .85),
    ("EnviroPulse", "district-level environment analytics", 335, .68),
]


def projects(_d):
    W, H, cx, cy, R, T = 1000, 616, 280, 340, 210, 9
    rings = "".join(f'<circle cx="{cx}" cy="{cy}" r="{R*f:.0f}" fill="none" stroke="{GREEN}" stroke-opacity="{.12 if f < 1 else .35}"/>' for f in (.25, .5, .75, 1))
    rings += f'<path d="M{cx-R} {cy}H{cx+R}M{cx} {cy-R}V{cy+R}" stroke="{GREEN}" stroke-opacity=".12"/>'
    rings += "".join(f'<path d="M{cx+R*math.cos(math.radians(a)):.1f} {cy+R*math.sin(math.radians(a)):.1f}L{cx+(R-8)*math.cos(math.radians(a)):.1f} {cy+(R-8)*math.sin(math.radians(a)):.1f}" stroke="{GREEN}" stroke-opacity=".4"/>' for a in range(0, 360, 10))
    wedge = ""
    for k in range(12):  # trailing fade behind the sweep edge
        a0, a1 = math.radians(-(k + 1) * 4), math.radians(-k * 4)
        wedge += (f'<path d="M{cx} {cy}L{cx+R*math.cos(a0):.1f} {cy+R*math.sin(a0):.1f}A{R} {R} 0 0 1 {cx+R*math.cos(a1):.1f} {cy+R*math.sin(a1):.1f}Z"'
                  f' fill="{GREEN}" fill-opacity="{.22*(1-k/12):.3f}"/>')
    wedge += f'<path d="M{cx} {cy}H{cx+R}" stroke="{GREEN}" stroke-width="2"/>'
    blips, rows = "", ""
    for i, (name, tag, ang, rf) in enumerate(PROJECTS):
        x, y = cx + R * rf * math.cos(math.radians(ang)), cy + R * rf * math.sin(math.radians(ang))
        dl = ang / 360 * T - T
        blips += (f'<circle class="ripple" style="animation-delay:{dl:.2f}s" cx="{x:.1f}" cy="{y:.1f}" r="5" fill="none" stroke="{GREEN}"/>'
                  f'<circle class="blip" style="animation-delay:{dl:.2f}s" cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{GREEN}"/>'
                  f'<text class="blip" style="animation-delay:{dl:.2f}s" x="{x+10:.1f}" y="{y-8:.1f}" fill="{TEXT}" font-family="{MONO}" font-size="10">{esc(name)}</text>')
        ry = 132 + i * 62
        rows += (f'<rect class="hl" style="animation-delay:{dl:.2f}s" x="540" y="{ry}" width="420" height="54" rx="8" fill="{GREEN}" fill-opacity=".08" stroke="{GREEN}" stroke-opacity=".5"/>'
                 f'<text x="560" y="{ry+33}" fill="{MUTED}" font-family="{MONO}" font-size="12">0{i+1}</text>'
                 f'<text class="nm" style="animation-delay:{dl:.2f}s" x="596" y="{ry+25}" fill="{TEXT}" font-family="{DISP}" font-size="19" font-weight="800">{esc(name)}</text>'
                 f'<text x="596" y="{ry+43}" fill="{MUTED}" font-family="{MONO}" font-size="10.5">{esc(tag)}</text>'
                 f'<text class="hl" style="animation-delay:{dl:.2f}s" x="944" y="{ry+32}" text-anchor="end" fill="{GREEN}" font-family="{MONO}" font-size="10" letter-spacing="1.5">● DETECTED</text>')
    css = (f".sweep{{transform-origin:{cx}px {cy}px;animation:spin {T}s linear infinite}}"
           f"@keyframes blip{{0%{{opacity:1}}35%,100%{{opacity:.3}}}}.blip{{animation:blip {T}s linear infinite}}"
           f"@keyframes ripple{{0%{{opacity:.9;transform:scale(1)}}25%,100%{{opacity:0;transform:scale(6)}}}}.ripple{{transform-box:fill-box;transform-origin:center;animation:ripple {T}s ease-out infinite}}"
           f"@keyframes hl{{0%{{opacity:1}}30%,100%{{opacity:0}}}}.hl{{animation:hl {T}s ease-out infinite}}"
           f"@keyframes nm{{0%{{fill:{GREEN}}}30%,100%{{fill:{TEXT}}}}}.nm{{animation:nm {T}s ease-out infinite}}")
    body = (card(W, H) + header("PROJECT RADAR · SCANNING", "Things I've built", W) + rings
            + f'<g class="sweep">{wedge}</g>{blips}'
            + f'<circle cx="{cx}" cy="{cy}" r="5" fill="{GREEN}"/><text x="{cx}" y="{cy+R+32}" text-anchor="middle" fill="{MUTED}" font-family="{MONO}" font-size="10" letter-spacing="1.5">RANGE · AI · CV · SECURITY · DATA</text>'
            + rows)
    return svg(W, H, "Projects", body, css)


CARDS = [  # name, repo, description, tags, badge
    ("AirInsight", "AirInsight-Intelligent-Air-Quality-Analytics-Platform",
     "CatBoost air-quality prediction network. 1st in Sustainability domain, Code Automata 2.1.",
     ["CatBoost", "real-time", "ML"], "IEEE PAPER"),
    ("CrowdWatch AI", "CrowdWatch-AI",
     "Real-time crowd monitoring, prediction and automated safety alerts for public transport.",
     ["computer vision", "WebSocket"], ""),
    ("Unmask", "Unmask",
     "Traces crypto hacks by fusing OSINT chatter with on-chain wallet trails to name the hacker.",
     ["OSINT", "blockchain", "forensics"], "● LIVE"),
    ("FwdCheck", "FwdCheck",
     "Fact-checks WhatsApp forwards claim by claim against trusted sources, in Hindi, Marathi or English.",
     ["FastAPI", "Gemini", "Next.js"], "● LIVE"),
    ("EnergySense", "Energy-Consumption-Forecasting",
     "Smart-home energy forecasting that turns household data into cost insights and trends.",
     ["forecasting", "big data", "Next.js"], "● LIVE"),
    ("AI-SDPIP", "AI-SDPIP-Smart-Data-Processing-with-Intelligent-Automation",
     "AI-powered survey data cleaning, missing-value imputation, estimation and automated reporting.",
     ["Streamlit", "imputation", "stats"], "● LIVE"),
]


def rrect(x, y, w, h, r):
    return (f"M{x+r} {y}H{x+w-r}A{r} {r} 0 0 1 {x+w} {y+r}V{y+h-r}A{r} {r} 0 0 1 {x+w-r} {y+h}"
            f"H{x+r}A{r} {r} 0 0 1 {x} {y+h-r}V{y+r}A{r} {r} 0 0 1 {x+r} {y}Z")


def cards(d):
    """One SVG per card (GitHub can't link regions of a single image), plus a section header."""
    cw, ch, m = 296, 210, 8
    by_name = {r["name"]: r for r in d["repos"]}
    accents = [GREEN, BLUE, PURPLE, GREEN, BLUE, PURPLE]
    css = ("@keyframes beam{from{stroke-dashoffset:0}to{stroke-dashoffset:-1}}.beam{stroke-dasharray:.16 .84;animation:beam 6.6s linear infinite}"
           "@keyframes ln{from{opacity:0;transform:translateX(-10px)}to{opacity:1;transform:none}}.ln{animation:ln .6s ease-out backwards}"
           "@keyframes glow{50%{fill-opacity:.32}}.glow{animation:glow 2.4s ease-in-out infinite}"
           "@keyframes nudge{0%,80%,100%{transform:none}88%{transform:translate(3px,-3px)}}.arrow{animation:nudge 3s ease-in-out infinite}")
    files = {"cards-head.svg": svg(1000, 110, "Featured projects", card(1000, 110) + header("FEATURED PROJECTS · CLICK A CARD", "Six things worth opening", 1000))}
    for i, (name, repo, desc, tags, badge) in enumerate(CARDS):
        x, y, col = m, m, accents[i]
        lang = by_name.get(repo, {}).get("language") or "—"
        dl = i * .15
        out = (f'<g class="reveal" style="animation-delay:{dl:.2f}s">'
               f'<path d="{rrect(x, y, cw, ch, 10)}" fill="{PANEL}" stroke="{BORDER}"/>'
               f'<path class="beam" style="animation-delay:{-i*1.1:.1f}s" pathLength="1" d="{rrect(x, y, cw, ch, 10)}" fill="none" stroke="{col}" stroke-width="2" stroke-linecap="round"/>'
               f'<text x="{x+20}" y="{y+32}" fill="{MUTED}" font-family="{MONO}" font-size="11">0{i+1}</text>'
               f'<circle cx="{x+52}" cy="{y+28}" r="5" fill="{LANG_COLORS.get(lang, MUTED)}"/>'
               f'<text x="{x+62}" y="{y+32}" fill="{MUTED}" font-family="{MONO}" font-size="11">{esc(lang)}</text>')
        out += f'<text x="{x+20}" y="{y+70}" fill="{TEXT}" font-family="{DISP}" font-size="24" font-weight="800">{esc(name)}</text>'
        per_line = int((cw - 40) / (11.5 * MONO_W))
        for j, line in enumerate(textwrap.wrap(desc, per_line)[:3]):
            out += f'<text class="ln" style="animation-delay:{.5+dl+j*.15:.2f}s" x="{x+20}" y="{y+98+j*18}" fill="{MUTED}" font-family="{MONO}" font-size="11.5">{esc(line)}</text>'
        tx = x + 20
        for t in tags:
            tw = len(t) * 11 * MONO_W + 18
            out += (f'<rect x="{tx:.0f}" y="{y+ch-42}" width="{tw:.0f}" height="24" rx="12" fill="{col}" fill-opacity=".1" stroke="{col}" stroke-opacity=".45"/>'
                    f'<text x="{tx+9:.0f}" y="{y+ch-26}" fill="{col}" font-family="{MONO}" font-size="11">{esc(t)}</text>')
            tx += tw + 8
        out += f'<text class="arrow" x="{x+cw-22}" y="{y+ch-24}" text-anchor="end" fill="{MUTED}" font-family="{MONO}" font-size="16">↗</text></g>'
        files[f"card-{i+1}.svg"] = svg(cw + 2 * m, ch + 2 * m, name, out, css)
    # clickable pills shown under each card (each image carries its own link in the README)
    for fname, label, col, dot in (("pill-live.svg", "LIVE", GREEN, True), ("pill-paper.svg", "IEEE PAPER", YELLOW, False),
                                   ("pill-repo.svg", "REPO", BLUE, False)):
        text = label + " ↗"
        w = round(len(text) * (12 * MONO_W + 1) + (44 if dot else 28))
        tx = 30 if dot else 14
        pill = (f'<rect class="glow" x="1" y="1" width="{w-2}" height="30" rx="15" fill="{col}" fill-opacity=".14" stroke="{col}" stroke-opacity=".7"/>'
                + (f'<circle class="pulse" cx="17" cy="16" r="4.5" fill="{col}"/>' if dot else "")
                + f'<text x="{tx}" y="21" fill="{col}" font-family="{MONO}" font-size="12" letter-spacing="1">{esc(text)}</text>')
        files[fname] = svg(w, 32, label, pill, "@keyframes glow{50%{fill-opacity:.3}}.glow{animation:glow 2.4s ease-in-out infinite}")
    return files


SHORT = {"Energy-Consumption-Forecasting": "EnergySense", "AirInsight-Intelligent-Air-Quality-Analytics-Platform": "AirInsight",
         "AutoStylist-Intelligent-Wardrobe-Outfit-Decision-Agent": "AutoStylist", "CrowdWatch-AI": "CrowdWatch AI",
         "AutoSOC---AI-Based-Unified-Security-Monitoring-and-Vulnerability-Platform": "AutoSOC",
         "SENTRIX-Sensitive-Exposure-Threat-Intelligence-System": "SENTRIX",
         "AI-SDPIP-Smart-Data-Processing-with-Intelligent-Automation": "AI-SDPIP"}
TIMELINE = set(SHORT) | {"EnviroPulse", "Portfolio", "FwdCheck", "Unmask"}  # finished work only; add new repos here


def timeline(d):
    W, H = 1000, 440
    repos = sorted((r for r in d["repos"] if r["name"] in TIMELINE), key=lambda r: r["created_at"])[-10:]
    y0, x0, x1 = 236, 90, W - 90
    step = (x1 - x0) / max(1, len(repos) - 1)
    marks, n = "", len(repos)
    for i, r in enumerate(repos):
        x, up = x0 + i * step, i % 2 == 0
        label = SHORT.get(r["name"]) or " ".join(re.split(r"[-_]+", r["name"])[:2])[:16]
        sha = hashlib.sha1(r["name"].encode()).hexdigest()[:7]
        when = datetime.strptime(r["created_at"][:10], "%Y-%m-%d").strftime("%b %d, %Y")
        cy = y0 - 104 if up else y0 + 40
        bw = 160
        bx = min(max(x - bw / 2, 24), W - 24 - bw)
        marks += (f'<g class="c{i}">'
                  f'<path d="M{x:.0f} {y0}V{cy+64 if up else cy}" stroke="{BORDER}" stroke-dasharray="3 3"/>'
                  f'<rect x="{bx:.0f}" y="{cy}" width="{bw}" height="64" rx="8" fill="{PANEL}" stroke="{BORDER}"/>'
                  f'<text x="{bx+12:.0f}" y="{cy+22}" font-family="{MONO}" font-size="11"><tspan fill="{BLUE}">{sha}</tspan><tspan fill="{MUTED}"> feat:</tspan></text>'
                  f'<text x="{bx+12:.0f}" y="{cy+41}" fill="{TEXT}" font-family="{DISP}" font-size="15" font-weight="800">{esc(label)}</text>'
                  f'<text x="{bx+12:.0f}" y="{cy+56}" fill="{MUTED}" font-family="{MONO}" font-size="9.5">{when}</text>'
                  f'<circle cx="{x:.0f}" cy="{y0}" r="8" fill="{BG}" stroke="{GREEN}" stroke-width="2.5"/></g>')
    lx = x0 + (n - 1) * step
    head = (f'<g class="c{n-1}"><rect x="{lx-44:.0f}" y="{y0+92 if n % 2 else y0-128}" width="88" height="20" rx="10" fill="{BLUE}" fill-opacity=".15" stroke="{BLUE}"/>'
            f'<text x="{lx:.0f}" y="{y0+106 if n % 2 else y0-114}" text-anchor="middle" fill="{BLUE}" font-family="{MONO}" font-size="10">HEAD → main</text></g>')
    css = (seq_css("c", n, 14, .4, .45) +
           f"@keyframes run{{from{{transform:translateX(0)}}to{{transform:translateX({x1-x0+60:.0f}px)}}}}.run{{animation:run 3.5s cubic-bezier(.5,0,.5,1) infinite}}")
    body = (card(W, H) + header("GIT LOG --GRAPH --ALL", "Shipped, in order", W)
            + f'<path d="M{x0-30} {y0}H{x1+30}" stroke="{BORDER}" stroke-width="3"/>'
            f'<path class="draw" pathLength="1" d="M{x0-30} {y0}H{x1+30}" stroke="{GREEN}" stroke-width="3"/>'
            f'<circle class="run" cx="{x0-30}" cy="{y0}" r="4" fill="{TEXT}"/>{marks}{head}')
    return svg(W, H, "Project timeline", body, css)


def stats(d):
    W, H = 1000, 390
    u = d["user"]
    tiles = [(d["total"], "contributions", "last 12 months", GREEN), (d["streak"], "current streak", "days in a row", BLUE),
             (d["longest"], "longest streak", "days", PURPLE), (d["active"], "active days", "last 12 months", GREEN),
             (len(d["repos"]), "repositories", "public, original", BLUE), (u["followers"], "followers", "and counting", PURPLE)]
    out = ""
    for i, (v, lab, sub, col) in enumerate(tiles):
        x, y = 40 + (i % 3) * 312, 124 + (i // 3) * 124
        out += (f'<g class="reveal" style="animation-delay:{i*.1:.1f}s"><rect x="{x}" y="{y}" width="296" height="108" rx="10" fill="{PANEL}" stroke="{BORDER}"/>'
                f'<rect x="{x}" y="{y+18}" width="3" height="72" rx="1.5" fill="{col}"/>'
                + odometer(x + 24, y + 62, v, 40, f"s{i}", .4 + i * .15) +
                f'<text x="{x+24}" y="{y+88}" fill="{TEXT}" font-family="{MONO}" font-size="12">{lab} <tspan fill="{MUTED}">· {sub}</tspan></text>'
                f'<circle class="pulse" cx="{x+272}" cy="{y+24}" r="4" fill="{col}" style="animation-delay:{i*.4:.1f}s"/></g>')
    body = card(W, H) + header("PROFILE SIGNAL · LIVE", "Momentum, made visible", W, f"updated {date.today():%b %d, %Y}") + out
    return svg(W, H, "Stats", body, odometer_css(40))


def snake(d):
    W, H = 1000, 360
    src = d["snake"]
    vb = re.search(r'viewBox="([^"]+)"', src).group(1)
    vx, vy, vw, vh = map(float, vb.split())
    inner = src[src.index(">", src.index("<svg")) + 1: src.rindex("</svg>")]
    inner = re.sub(r":root\{[^}]*\}", ":root{--cb:#0d111700;--cs:%s;--ce:%s;--c0:%s;--c1:%s;--c2:%s;--c3:%s;--c4:%s}" % (PURPLE, LEVELS[0], *LEVELS), inner)
    inner = re.sub(r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{:root\{[^}]*\}\}", "", inner)
    sw = W - 80
    sh = sw * vh / vw
    legend = "".join(f'<rect x="{W-196+i*16}" y="{H-36}" width="12" height="12" rx="2.5" fill="{c}"/>' for i, c in enumerate(LEVELS))
    body = (card(W, H) + header("CONTRIBUTION TRAIL", f"{d['total']:,} contributions, eaten one by one", W)
            + f'<svg x="40" y="{108}" width="{sw}" height="{sh:.0f}" viewBox="{vb}">{inner}</svg>'
            + f'<text x="40" y="{H-26}" fill="{MUTED}" font-family="{MONO}" font-size="10.5">{d["active"]} active days · longest streak {d["longest"]} · current {d["streak"]}</text>'
            + f'<text x="{W-232}" y="{H-26}" fill="{MUTED}" font-family="{MONO}" font-size="10.5">less</text>{legend}<text x="{W-110}" y="{H-26}" fill="{MUTED}" font-family="{MONO}" font-size="10.5">more</text>')
    return svg(W, H, "Contribution snake", body)


def octicon(name, x, y, size, color):
    raw = get(f"https://cdn.jsdelivr.net/npm/@primer/octicons@19/build/svg/{name}-16.svg", raw=True).decode()
    paths = "".join(f'<path d="{p}"/>' for p in re.findall(r' d="([^"]+)"', raw))
    return f'<g transform="translate({x} {y}) scale({size/16})" fill="{color}">{paths}</g>'


def social(_d):
    """Contact as a pull request: checks pass, a cursor clicks Merge, the PR flips to Merged. Loops."""
    W, H, T = 1000, 430, 12
    pct = lambda t: t / T * 100

    def win(name, a, b, fade=.25):  # visible between a and b seconds
        A, B, f = pct(a), pct(b), pct(fade)
        lead = f"0%,{max(A-f,0):.2f}%{{opacity:0}}" if a > 0 else ""
        return f"@keyframes {name}{{{lead}{A:.2f}%,{B:.2f}%{{opacity:1}}{min(B+f,100):.2f}%,100%{{opacity:0}}}}.{name}{{animation:{name} {T}s linear infinite}}"

    done, merged, end = [2.0, 3.0, 4.0], 7.8, 11.3
    css = win("open", 0, merged - .1) + win("mrg", merged, end) + win("pend", 0, 4.3) + win("pass", 4.4, end) + win("pre", 0, merged - .1)
    checks = [("portfolio", "satyaranjan.vercel.app", "0.42s"), ("linkedin", "in/satyaranjan-behera", "0.38s"),
              ("email", "satyabhr2005@gmail.com", "0.51s")]
    rows = ""
    for i, (name, val, t) in enumerate(checks):
        y = 196 + i * 40
        css += win(f"sp{i}", 0, done[i] - .05) + win(f"ok{i}", done[i], end)
        rows += (f'<path d="M56 {y-26}H944" stroke="{BORDER}"/>'
                 f'<g class="sp{i}" opacity="0"><circle class="spin" cx="66" cy="{y-6}" r="7" fill="none" stroke="{YELLOW}" stroke-width="2" stroke-dasharray="30 14"/></g>'
                 f'<g class="ok{i}">{octicon("check-circle-fill", 58, y-14, 16, GREEN)}</g>'
                 f'<text x="90" y="{y-1}" font-family="{MONO}" font-size="13" fill="{TEXT}">{name} <tspan fill="{MUTED}">/ {esc(val)}</tspan></text>'
                 f'<text class="sp{i}" opacity="0" x="930" y="{y-1}" text-anchor="end" font-family="{MONO}" font-size="12" fill="{YELLOW}">In progress…</text>'
                 f'<text class="ok{i}" x="930" y="{y-1}" text-anchor="end" font-family="{MONO}" font-size="12" fill="{MUTED}">Successful in {t}</text>')
    bx, by, bw, bh = 742, 354, 188, 36
    cx, cy = bx + bw / 2, by + bh / 2
    css += (f"@keyframes cur{{0%,{pct(5.4):.1f}%{{opacity:0;transform:translate(150px,80px)}}{pct(5.7):.1f}%{{opacity:1;transform:translate(150px,80px)}}"
            f"{pct(7.3):.1f}%{{opacity:1;transform:translate(0,0)}}{pct(7.5):.1f}%{{transform:translate(0,0) scale(.85)}}{pct(7.7):.1f}%{{transform:translate(0,0)}}"
            f"{pct(9):.1f}%{{opacity:1;transform:translate(0,0)}}{pct(9.5):.1f}%,100%{{opacity:0;transform:translate(0,0)}}}}"
            f".cur{{animation:cur {T}s cubic-bezier(.4,0,.2,1) infinite}}"
            f"@keyframes rip{{0%,{pct(7.5):.1f}%{{opacity:0;transform:scale(.3)}}{pct(7.55):.1f}%{{opacity:.7}}{pct(8.4):.1f}%,100%{{opacity:0;transform:scale(3)}}}}"
            f".rip{{transform-box:fill-box;transform-origin:center;animation:rip {T}s ease-out infinite}}"
            ".spin{transform-box:fill-box;transform-origin:center;animation:spin .9s linear infinite}")
    body = (card(W, H) +
            # status pill: Open -> Merged
            f'<g class="open"><rect x="40" y="34" width="86" height="30" rx="15" fill="#238636"/>{octicon("git-pull-request", 54, 41, 16, "#fff")}'
            f'<text x="76" y="54" font-family="{DISP}" font-size="13" font-weight="800" fill="#fff">Open</text></g>'
            f'<g class="mrg" opacity="0"><rect x="40" y="34" width="100" height="30" rx="15" fill="#8957e5"/>{octicon("git-merge", 54, 41, 16, "#fff")}'
            f'<text x="76" y="54" font-family="{DISP}" font-size="13" font-weight="800" fill="#fff">Merged</text></g>'
            f'<text x="158" y="58" font-family="{DISP}" font-size="26" font-weight="800" fill="{TEXT}">Let&#39;s build something together <tspan fill="{MUTED}" font-weight="400">#2026</tspan></text>'
            f'<text x="40" y="96" font-family="{MONO}" font-size="12.5" fill="{MUTED}"><tspan fill="{TEXT}">{USER}</tspan> wants to merge 1 commit into '
            f'<tspan fill="{BLUE}">your-team:main</tspan> from <tspan fill="{BLUE}">satya:open-to-work</tspan></text>'
            # checks panel
            f'<rect x="40" y="118" width="920" height="186" rx="8" fill="{PANEL}" stroke="{BORDER}"/>'
            f'<g class="pend"><circle class="spin" cx="66" cy="146" r="8" fill="none" stroke="{YELLOW}" stroke-width="2" stroke-dasharray="34 16"/>'
            f'<text x="90" y="151" font-family="{DISP}" font-size="15" font-weight="800" fill="{TEXT}">Some checks haven&#39;t completed yet</text></g>'
            f'<g class="pass" opacity="0">{octicon("check-circle-fill", 57, 137, 18, GREEN)}'
            f'<text x="90" y="151" font-family="{DISP}" font-size="15" font-weight="800" fill="{TEXT}">All checks have passed '
            f'<tspan font-family="{MONO}" font-size="12" font-weight="400" fill="{MUTED}">· 3 successful checks</tspan></text></g>'
            + rows +
            # merge box
            f'<rect x="40" y="320" width="920" height="88" rx="8" fill="{PANEL}" stroke="{BORDER}"/>'
            f'<g class="pre"><circle cx="72" cy="364" r="16" fill="#238636"/>{octicon("check", 64, 356, 16, "#fff")}'
            f'<text x="102" y="358" font-family="{DISP}" font-size="15" font-weight="800" fill="{TEXT}">This branch has no conflicts with the base branch</text>'
            f'<text x="102" y="378" font-family="{MONO}" font-size="12" fill="{MUTED}">Merging can be performed automatically.</text>'
            f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="6" fill="#238636"/>'
            f'<text x="{cx}" y="{cy+5}" text-anchor="middle" font-family="{DISP}" font-size="14" font-weight="800" fill="#fff">Merge pull request</text></g>'
            f'<g class="mrg" opacity="0"><circle cx="72" cy="364" r="16" fill="#8957e5"/>{octicon("git-merge", 64, 356, 16, "#fff")}'
            f'<text x="102" y="358" font-family="{DISP}" font-size="15" font-weight="800" fill="{TEXT}">Pull request merged. Let&#39;s talk.</text>'
            f'<text x="102" y="378" font-family="{MONO}" font-size="12" fill="{MUTED}">satyaranjan.vercel.app · in/satyaranjan-behera · satyabhr2005@gmail.com</text>'
            f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="6" fill="#8957e5"/>'
            f'<text x="{cx}" y="{cy+5}" text-anchor="middle" font-family="{DISP}" font-size="14" font-weight="800" fill="#fff">✓ Merged</text></g>'
            # cursor + click ripple
            f'<circle class="rip" cx="{cx+80}" cy="{cy}" r="14" fill="none" stroke="#fff" stroke-width="2" opacity="0"/>'
            f'<g class="cur" opacity="0"><path transform="translate({cx+77} {cy-4})" d="M0 0L0 20L5.5 15L9 23L12.5 21.5L9 14L16 14Z" fill="#fff" stroke="{BG}" stroke-width="1.4"/></g>')
    return svg(W, H, "Contact", body, css)


def divider(_d):
    W, H = 1000, 40
    nodes = "".join(f'<circle class="nd" style="animation-delay:{i*.25:.2f}s" cx="{100+i*100}" cy="20" r="4" fill="{BG}" stroke="{GREEN}" stroke-width="2"/>' for i in range(9))
    css = (f"@keyframes nd{{0%,100%{{fill:{BG}}}8%{{fill:{GREEN}}}20%{{fill:{BG}}}}}.nd{{animation:nd 3s linear infinite}}"
           f"@keyframes go{{from{{transform:translateX(-120px)}}to{{transform:translateX({W+120}px)}}}}.go{{animation:go 3s linear infinite}}")
    defs = f'<linearGradient id="g" x1="0" x2="1"><stop stop-color="{GREEN}" stop-opacity="0"/><stop offset="1" stop-color="{GREEN}"/></linearGradient>'
    body = f'<path d="M40 20H{W-40}" stroke="{BORDER}" stroke-width="2"/><rect class="go" x="0" y="19" width="120" height="2" fill="url(#g)"/>{nodes}'
    return svg(W, H, "divider", body, css, defs)


def main():
    global FONTS
    d = load()
    FONTS = font_css()
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):  # drop sections that no longer exist
        if f.endswith(".svg"):
            os.remove(os.path.join(OUT, f))
    for fn in (hero, wordmark, terminal, stack, projects, cards, timeline, stats, snake, social, divider):
        res = fn(d)
        for name, content in (res if isinstance(res, dict) else {fn.__name__ + ".svg": res}).items():
            with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
                fh.write(content)
            print("wrote", name)


if __name__ == "__main__":
    main()
