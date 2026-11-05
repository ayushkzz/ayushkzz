"""Build the SVG graphics used by the profile README.

Each graphic is written twice, as `<name>-dark.svg` and `<name>-light.svg`,
and the README picks one with <picture> based on the viewer's GitHub theme.

GitHub READMEs cannot load web fonts, so every SVG embeds the fonts it needs,
subset to just the characters it uses (Space Grotesk, Inter, JetBrains Mono;
all SIL Open Font License, see fonts/).

Usage:  pip install fonttools brotli && python assets/build.py
"""

import base64
import io
from html import escape
from pathlib import Path

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

HERE = Path(__file__).parent
FONT_DIR = HERE / "fonts"

FONTS = {
    "display": "space-grotesk-latin-700-normal.woff2",
    "display-m": "space-grotesk-latin-500-normal.woff2",
    "body": "inter-latin-400-normal.woff2",
    "body-m": "inter-latin-500-normal.woff2",
    "body-sb": "inter-latin-600-normal.woff2",
    "mono": "jetbrains-mono-latin-400-normal.woff2",
    "mono-sb": "jetbrains-mono-latin-600-normal.woff2",
}
_loaded = {k: TTFont(FONT_DIR / v) for k, v in FONTS.items()}

THEMES = {
    "dark": dict(
        surface="#10141d", surface2="#151a26", border="#242b3b", grid="#1c2230",
        text="#e8eaf0", muted="#9aa3b5", faint="#5f6880",
        a1="#8b5cf6", a2="#22d3ee", a3="#f472b6",
        orb=0.55, pill="#8b5cf6", pill_text="#c4b5fd",
        kw="#f472b6", cls="#22d3ee", str="#a5e075", attr="#e8eaf0", fn="#8b5cf6",
    ),
    "light": dict(
        surface="#ffffff", surface2="#f6f7fb", border="#e3e6ee", grid="#eef0f5",
        text="#0e1220", muted="#5a6378", faint="#9aa3b5",
        a1="#7c3aed", a2="#0891b2", a3="#db2777",
        orb=0.28, pill="#7c3aed", pill_text="#6d28d9",
        kw="#db2777", cls="#0891b2", str="#2f7d32", attr="#0e1220", fn="#7c3aed",
    ),
}


# ---------------------------------------------------------------- helpers
def text_width(s, font, size):
    f = _loaded[font]
    cmap, hmtx = f.getBestCmap(), f["hmtx"]
    upm = f["head"].unitsPerEm
    return sum(hmtx[cmap.get(ord(c), ".notdef")][0] for c in s) * size / upm


def wrap(s, font, size, max_w):
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if text_width(trial, font, size) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + [cur]


class Svg:
    """Collects SVG markup and the characters each font has to render."""

    def __init__(self, w, h, title):
        self.w, self.h, self.title = w, h, title
        self.parts, self.defs, self.css, self.chars = [], [], [], {}

    def add(self, markup):
        self.parts.append(markup)

    def text(self, x, y, s, font, size, fill, anchor="start", extra=""):
        self.chars.setdefault(font, set()).update(s)
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" class="f-{font}" font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}" {extra}>{escape(s)}</text>'
        )

    def tspans(self, x, y, segments, font, size, extra=""):
        """One line made of differently coloured segments."""
        self.chars.setdefault(font, set()).update("".join(s for s, _ in segments))
        spans = "".join(f'<tspan fill="{c}">{escape(s)}</tspan>' for s, c in segments)
        self.add(f'<text x="{x}" y="{y}" class="f-{font}" font-size="{size}" '
                 f'xml:space="preserve" {extra}>{spans}</text>')

    def _font_css(self):
        out = []
        for font, chars in self.chars.items():
            opts = Options()
            opts.flavor = "woff2"
            opts.layout_features = ["kern", "liga", "calt"]
            sub = Subsetter(opts)
            f = TTFont(FONT_DIR / FONTS[font])
            sub.populate(text="".join(chars) + " ")
            sub.subset(f)
            buf = io.BytesIO()
            f.flavor = "woff2"
            f.save(buf)
            b64 = base64.b64encode(buf.getvalue()).decode()
            fam = {"display": "'Space Grotesk'", "display-m": "'Space Grotesk'",
                   "mono": "'JetBrains Mono'", "mono-sb": "'JetBrains Mono'"}.get(font, "Inter")
            out.append(f"@font-face{{font-family:'{font}';src:url(data:font/woff2;base64,{b64}) format('woff2')}}"
                       f".f-{font}{{font-family:'{font}',{fam},system-ui,sans-serif}}")
        return "".join(out)

    def save(self, path):
        css = self._font_css() + "".join(self.css)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(self.title)}">'
            f"<title>{escape(self.title)}</title><style>{css}</style>"
            f"<defs>{''.join(self.defs)}</defs>{''.join(self.parts)}</svg>"
        )
        Path(path).write_text(svg, encoding="utf-8")


def accent_gradient(svg, gid, t, x2="100%", y2="0%"):
    svg.defs.append(
        f'<linearGradient id="{gid}" x1="0%" y1="0%" x2="{x2}" y2="{y2}">'
        f'<stop offset="0%" stop-color="{t["a1"]}"/><stop offset="55%" stop-color="{t["a2"]}"/>'
        f'<stop offset="100%" stop-color="{t["a3"]}"/></linearGradient>'
    )


def panel(svg, t, x, y, w, h, r=18):
    svg.add(f'<rect x="{x + .5}" y="{y + .5}" width="{w - 1}" height="{h - 1}" rx="{r}" '
            f'fill="{t["surface"]}" stroke="{t["border"]}"/>')


def pill(svg, t, x, y, label, font="mono", size=12, h=26, pad=11, dot=None):
    w = text_width(label, font, size) + pad * 2 + (14 if dot else 0)
    if dot:  # neutral chip with a coloured dot
        svg.add(f'<rect x="{x + .5}" y="{y + .5}" width="{w - 1:.1f}" height="{h - 1}" rx="{(h - 1) / 2}" '
                f'fill="{t["surface2"]}" fill-opacity="0.85" stroke="{t["border"]}"/>')
    else:  # tinted accent tag
        svg.add(f'<rect x="{x}" y="{y}" width="{w:.1f}" height="{h}" rx="{h / 2}" '
                f'fill="{t["pill"]}" fill-opacity="0.12" stroke="{t["pill"]}" stroke-opacity="0.28"/>')
    tx = x + pad
    if dot:
        svg.add(f'<circle cx="{x + pad + 4}" cy="{y + h / 2}" r="4" fill="{dot}"/>')
        tx += 14
    svg.text(tx, y + h / 2 + size * 0.36, label, font, size, t["pill_text"] if not dot else t["text"])
    return w


REDUCED_MOTION = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"


# ---------------------------------------------------------------- graphics
def hero(t, path):
    W, H = 1000, 340
    s = Svg(W, H, "Ayush Kumar: coding enthusiast, learning to bring some change in the world")
    accent_gradient(s, "name", t)
    s.defs.append(f'<clipPath id="clip"><rect width="{W}" height="{H}" rx="24"/></clipPath>'
                  f'<filter id="blur" x="-50%" y="-50%" width="200%" height="200%">'
                  f'<feGaussianBlur stdDeviation="55"/></filter>'
                  f'<pattern id="grid" width="36" height="36" patternUnits="userSpaceOnUse">'
                  f'<path d="M36 0H0V36" fill="none" stroke="{t["grid"]}" stroke-width="1"/></pattern>'
                  f'<radialGradient id="fade" cx="78%" cy="40%" r="70%">'
                  f'<stop offset="0%" stop-color="#fff" stop-opacity="1"/>'
                  f'<stop offset="100%" stop-color="#fff" stop-opacity="0"/></radialGradient>'
                  f'<mask id="gridmask"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask>')
    s.css.append(
        "@keyframes drift1{from{transform:translate(0,0)}to{transform:translate(-60px,40px)}}"
        "@keyframes drift2{from{transform:translate(0,0)}to{transform:translate(50px,-35px)}}"
        "@keyframes drift3{from{transform:translate(0,0)}to{transform:translate(-40px,-30px)}}"
        "@keyframes rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}"
        "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}"
        ".o1{animation:drift1 9s ease-in-out infinite alternate}"
        ".o2{animation:drift2 11s ease-in-out infinite alternate}"
        ".o3{animation:drift3 13s ease-in-out infinite alternate}"
        ".r1{animation:rise .9s cubic-bezier(.2,.7,.2,1) both}"
        ".r2{animation:rise .9s .15s cubic-bezier(.2,.7,.2,1) both}"
        ".r3{animation:rise .9s .3s cubic-bezier(.2,.7,.2,1) both}"
        ".cursor{animation:blink 1.1s steps(1) infinite}" + REDUCED_MOTION
    )
    s.add('<g clip-path="url(#clip)">')
    s.add(f'<rect width="{W}" height="{H}" fill="{t["surface"]}"/>')
    s.add(f'<rect width="{W}" height="{H}" fill="url(#grid)" mask="url(#gridmask)"/>')
    s.add(f'<g filter="url(#blur)" opacity="{t["orb"]}">'
          f'<circle class="o1" cx="820" cy="90" r="130" fill="{t["a1"]}"/>'
          f'<circle class="o2" cx="940" cy="290" r="110" fill="{t["a2"]}"/>'
          f'<circle class="o3" cx="660" cy="320" r="95" fill="{t["a3"]}"/></g>')
    s.add("</g>")
    s.add(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="24" fill="none" stroke="{t["border"]}"/>')

    # prompt line
    s.add('<g class="r1">')
    s.tspans(64, 84, [("~/ayushkzz ", t["muted"]), ("$ ", t["a1"]), ("whoami", t["text"])], "mono", 16)
    cx = 64 + text_width("~/ayushkzz $ whoami ", "mono", 16)
    s.add(f'<rect class="cursor" x="{cx:.1f}" y="70" width="9" height="18" rx="1" fill="{t["a2"]}"/>')
    s.add("</g>")

    s.add('<g class="r2">')
    s.text(60, 172, "Ayush Kumar", "display", 80, "url(#name)", extra='letter-spacing="-2"')
    s.text(64, 216, "Coding enthusiast. Learning to bring some change in the world.", "body", 20, t["muted"])
    s.add("</g>")

    s.add('<g class="r3">')
    x = 64
    for label, color in (("AI / Machine Learning", t["a1"]), ("Full-Stack Web", t["a2"]), ("DevOps & CI/CD", t["a3"])):
        x += pill(s, t, x, 252, label, font="body-m", size=14, h=34, pad=15, dot=color) + 10
    s.add("</g>")
    s.save(path)


def heading(t, path, number, title):
    W, H = 1000, 64
    s = Svg(W, H, title)
    accent_gradient(s, "line", t)
    s.defs.append(f'<linearGradient id="fadeline" x1="0" x2="1"><stop offset="0" stop-color="{t["a1"]}"/>'
                  f'<stop offset="1" stop-color="{t["a2"]}" stop-opacity="0"/></linearGradient>')
    s.text(0, 42, number, "mono-sb", 14, t["a1"])
    s.text(34, 44, title, "display", 30, t["text"], extra='letter-spacing="-0.5"')
    end = 34 + text_width(title, "display", 30) - 0.5 * len(title) + 22
    s.add(f'<rect x="{end:.1f}" y="33" width="{W - end:.1f}" height="2" rx="1" fill="url(#fadeline)" opacity=".7"/>')
    s.save(path)


def about(t, path):
    W = 1000
    code_w, gap = 590, 20
    side_x, side_w = code_w + gap, W - code_w - gap
    c = lambda k: t[k]
    code = [
        [("class ", c("kw")), ("AyushKumar", c("cls")), (":", c("muted"))],
        [("    def ", c("kw")), ("__init__", c("fn")), ("(self):", c("muted"))],
        [("        self.", c("muted")), ("role", c("attr")), ("      = ", c("muted")), ('"Developer & lifelong learner"', c("str"))],
        [("        self.", c("muted")), ("languages", c("attr")), (" = ", c("muted")), ('["Python", "Java", "JavaScript"]', c("str"))],
        [("        self.", c("muted")), ("building", c("attr")), ("  = ", c("muted")), ('"AI tools for everyday problems"', c("str"))],
        [("        self.", c("muted")), ("learning", c("attr")), ("  = ", c("muted")), ('["LLM apps", "MLOps", "Cloud"]', c("str"))],
        [],
        [("    def ", c("kw")), ("say_hi", c("fn")), ("(self):", c("muted"))],
        [("        print", c("fn")), ("(", c("muted")), ('"Thanks for stopping by!"', c("str")), (")", c("muted"))],
    ]
    focus = [
        ("AI / Machine Learning", t["a1"], "XGBoost forecasting, NLP pipelines, CNNs and LLM-powered apps with Gemini."),
        ("Full-Stack Web", t["a2"], "React front ends backed by Flask, FastAPI or Node and MongoDB."),
        ("DevOps & CI/CD", t["a3"], "Jenkins pipelines, Docker images and zero-downtime Nginx deploys."),
    ]
    blocks = [wrap(d, "body", 14, side_w - 56) for _, _, d in focus]
    side_h = 66 + sum(26 + 21 * len(b) + 18 for b in blocks) + 4
    code_h = 58 + len(code) * 25 + 24
    H = max(side_h, code_h)

    s = Svg(W, H, "About Ayush Kumar")
    panel(s, t, 0, 0, code_w, H, 16)
    s.add(f'<path d="M16.5 .5H{code_w - 16.5}A16 16 0 0 1 {code_w - .5} 16.5V40.5H.5V16.5A16 16 0 0 1 16.5 .5Z" '
          f'fill="{t["surface2"]}" stroke="{t["border"]}"/>')
    for i, col in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        s.add(f'<circle cx="{22 + i * 18}" cy="21" r="5.5" fill="{col}"/>')
    s.text(code_w / 2, 26, "about.py", "mono", 13, t["muted"], anchor="middle")
    for i, line in enumerate(code):
        y = 74 + i * 25
        s.text(22, y, str(i + 1), "mono", 13, t["faint"], anchor="end")
        if line:
            s.tspans(36, y, line, "mono", 14)

    panel(s, t, side_x, 0, side_w, H, 16)
    s.text(side_x + 28, 44, "What I work on", "display", 21, t["text"])
    y = 66
    for (title, color, _), lines in zip(focus, blocks):
        s.add(f'<rect x="{side_x + 28}" y="{y + 6}" width="10" height="10" rx="3" fill="{color}"/>')
        s.text(side_x + 48, y + 16, title, "body-sb", 15, t["text"])
        for j, ln in enumerate(lines):
            s.text(side_x + 48, y + 40 + j * 21, ln, "body", 14, t["muted"])
        y += 26 + 21 * len(lines) + 18
    s.save(path)


def toolbox(t, path):
    W, label_w, pad = 1000, 150, 28
    groups = [
        ("LANGUAGES", [("Python", "#3776ab"), ("Java", "#ed8b00"), ("JavaScript", "#f7df1e"),
                       ("TypeScript", "#3178c6"), ("HTML & CSS", "#e34f26"), ("Bash", "#4eaa25")]),
        ("AI / ML", [("TensorFlow", "#ff6f00"), ("Keras", "#d00000"), ("scikit-learn", "#f7931e"),
                     ("XGBoost", "#189fdd"), ("NLTK", "#4b8bbe"), ("Pandas", "#e70488"), ("NumPy", "#4dabcf"),
                     ("Gemini API", "#8e75b2"), ("Jupyter", "#f37626")]),
        ("WEB", [("React", "#61dafb"), ("Vite", "#646cff"), ("Tailwind", "#06b6d4"), ("Chakra UI", "#319795"),
                 ("Node.js", "#5fa04e"), ("Express", "#9aa3b5"), ("Flask", "#9aa3b5"), ("FastAPI", "#009688"),
                 ("Streamlit", "#ff4b4b"), ("Socket.io", "#9aa3b5")]),
        ("DEVOPS & DATA", [("Docker", "#2496ed"), ("Jenkins", "#d24939"), ("Nginx", "#009639"),
                           ("Maven", "#c71a36"), ("JUnit 5", "#25a162"), ("Git", "#f05032"),
                           ("GitHub Actions", "#2088ff"), ("MongoDB", "#47a248"), ("Linux", "#fcc624")]),
    ]
    chip_h, gap, row_gap = 32, 8, 10
    avail = W - pad * 2 - label_w

    # lay out first to know the height
    layout, y = [], pad
    for label, chips in groups:
        x, row_y, placed = 0, y, []
        for name, color in chips:
            w = text_width(name, "body-m", 14) + 22 + 14
            if x + w > avail:
                x, row_y = 0, row_y + chip_h + gap
            placed.append((x, row_y, name, color))
            x += w + gap
        layout.append((label, y, placed))
        y = row_y + chip_h + row_gap + 12
    H = y - row_gap - 12 + pad

    s = Svg(W, H, "Tech stack")
    panel(s, t, 0, 0, W, H, 18)
    for i, (label, gy, placed) in enumerate(layout):
        if i:
            s.add(f'<line x1="{pad}" x2="{W - pad}" y1="{gy - 11}" y2="{gy - 11}" stroke="{t["border"]}"/>')
        s.text(pad, gy + 21, label, "mono-sb", 12, t["muted"], extra='letter-spacing="1"')
        for x, ry, name, color in placed:
            pill(s, t, pad + label_w + x, ry, name, font="body-m", size=14, h=chip_h, pad=11, dot=color)
    s.save(path)


def project(t, path, p, w, h=None):
    pad = 28
    lines = wrap(p["desc"], "body", 15, w - pad * 2)
    H = h or (128 + 23 * len(lines) + 62)
    s = Svg(w, H, f'{p["name"]}: {p["desc"]}')
    accent_gradient(s, "top", t)
    s.defs.append(f'<clipPath id="c"><rect width="{w}" height="{H}" rx="18"/></clipPath>')
    panel(s, t, 0, 0, w, H, 18)
    s.add(f'<rect width="{w}" height="3" fill="url(#top)" clip-path="url(#c)"/>')
    s.text(pad, 46, p["tag"].upper(), "mono-sb", 12, t["a1"], extra='letter-spacing="1.2"')
    # arrow
    ax, ay = w - pad - 14, 32
    s.add(f'<path d="M{ax} {ay + 14}L{ax + 14} {ay}M{ax + 4} {ay}H{ax + 14}V{ay + 10}" fill="none" '
          f'stroke="{t["muted"]}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')
    s.text(pad, 86, p["name"], "display", 26, t["text"], extra='letter-spacing="-0.4"')
    for i, ln in enumerate(lines):
        s.text(pad, 120 + i * 23, ln, "body", 15, t["muted"])
    x = pad
    for tech in p["tech"]:
        x += pill(s, t, x, H - pad - 26, tech) + 8
    s.save(path)


def outro(t, path):
    W, H = 1000, 210
    s = Svg(W, H, "Thanks for stopping by. Find me on GitHub at github.com/ayushkzz")
    accent_gradient(s, "btn", t)
    s.defs.append(f'<clipPath id="c"><rect width="{W}" height="{H}" rx="24"/></clipPath>'
                  f'<filter id="b" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="50"/></filter>')
    s.add('<g clip-path="url(#c)">')
    s.add(f'<rect width="{W}" height="{H}" fill="{t["surface"]}"/>')
    s.add(f'<g filter="url(#b)" opacity="{t["orb"] * .7:.2f}"><circle cx="140" cy="210" r="110" fill="{t["a1"]}"/>'
          f'<circle cx="880" cy="0" r="110" fill="{t["a2"]}"/></g></g>')
    s.add(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="24" fill="none" stroke="{t["border"]}"/>')
    s.text(W / 2, 78, "Let’s build something useful.", "display", 32, t["text"], anchor="middle", extra='letter-spacing="-0.5"')
    s.text(W / 2, 110, "Thanks for stopping by. If one of my projects helps you, a star means a lot.",
           "body", 16, t["muted"], anchor="middle")
    label = "github.com/ayushkzz"
    bw = text_width(label, "mono-sb", 15) + 48
    bx = (W - bw) / 2
    s.add(f'<rect x="{bx:.1f}" y="134" width="{bw:.1f}" height="44" rx="22" fill="url(#btn)"/>')
    s.text(W / 2, 161, label, "mono-sb", 15, "#ffffff", anchor="middle")
    s.save(path)


PROJECTS = {
    "aqi": dict(name="Adaptive AQI Assistant", tag="AI · Forecasting",
                desc="Real-time air quality for Delhi: live readings from 14 stations, XGBoost AQI forecasts "
                     "on an interactive map, and personal health advice from Gemini.",
                tech=["Python", "Streamlit", "XGBoost", "Folium", "Gemini"]),
    "pair": dict(name="AI Pair Programmer Pro", tag="AI · Developer tools",
                 desc="An LLM coding partner with six modes (review, explain, refactor, find bugs, write tests, "
                      "optimize) that can also run Python and C++ snippets.",
                 tech=["FastAPI", "Gemini", "JavaScript"]),
    "edu": dict(name="AI-Powered Education Feedback", tag="AI · Education",
                desc="A coding practice platform for students: questions beside a Monaco editor, with instant "
                     "feedback on their code from a Phi-2-based model.",
                tech=["React 19", "Vite", "Chakra UI", "Monaco", "Flask"]),
    "bluegreen": dict(name="Blue-Green Deployments", tag="DevOps · CI/CD",
                      desc="Zero-downtime releases for a Java app: Jenkins builds and tests with Maven, ships a "
                           "Docker image to the idle environment, then Nginx switches traffic.",
                      tech=["Jenkins", "Maven", "Docker", "Nginx", "Java 17"]),
    "alumni": dict(name="Alumni-Student Platform", tag="Full-Stack · Community",
                   desc="Connects students with alumni for mentorship, with sign-in, profiles, alumni search and "
                        "real-time chat over Socket.io.",
                   tech=["Node.js", "Express", "MongoDB", "Socket.io", "Handlebars"]),
}

if __name__ == "__main__":
    out = HERE
    half_w = 490
    half_h = max(128 + 23 * len(wrap(PROJECTS[k]["desc"], "body", 15, half_w - 56)) + 62
                 for k in ("aqi", "pair", "edu", "bluegreen"))
    for mode, t in THEMES.items():
        hero(t, out / f"hero-{mode}.svg")
        about(t, out / f"about-{mode}.svg")
        toolbox(t, out / f"toolbox-{mode}.svg")
        outro(t, out / f"outro-{mode}.svg")
        for n, (key, title) in enumerate((("about", "About me"), ("toolbox", "Toolbox"),
                                          ("work", "Featured work"), ("activity", "GitHub activity")), 1):
            heading(t, out / f"h-{key}-{mode}.svg", f"0{n}", title)
        for key, p in PROJECTS.items():
            if key == "alumni":
                project(t, out / f"project-{key}-{mode}.svg", p, 1000)
            else:
                project(t, out / f"project-{key}-{mode}.svg", p, half_w, half_h)
    print("built", len(list(out.glob("*.svg"))), "SVGs")
