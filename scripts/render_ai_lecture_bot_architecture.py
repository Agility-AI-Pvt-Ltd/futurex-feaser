from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "ai-lecture-bot-high-level-architecture.png"
SCALE = 2
W, H = 1800, 1200


def c(hex_color: str) -> tuple[int, int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4)) + (255,)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "Arial Bold.ttf" if bold else "Arial.ttf"
    return ImageFont.truetype(f"/System/Library/Fonts/Supplemental/{name}", size * SCALE)


def rect(draw: ImageDraw.ImageDraw, xy, fill, outline, radius=22, width=2):
    xy = tuple(v * SCALE for v in xy)
    draw.rounded_rectangle(xy, radius=radius * SCALE, fill=fill, outline=outline, width=width * SCALE)


def line(draw: ImageDraw.ImageDraw, pts, fill, width=4, arrow=True):
    scaled = [(x * SCALE, y * SCALE) for x, y in pts]
    draw.line(scaled, fill=fill, width=width * SCALE, joint="curve")
    if not arrow or len(scaled) < 2:
        return
    x1, y1 = scaled[-2]
    x2, y2 = scaled[-1]
    dx, dy = x2 - x1, y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    size = 18 * SCALE
    wing = 9 * SCALE
    tip = (x2, y2)
    base = (x2 - ux * size, y2 - uy * size)
    draw.polygon(
        [
            tip,
            (base[0] + px * wing, base[1] + py * wing),
            (base[0] - px * wing, base[1] - py * wing),
        ],
        fill=fill,
    )


def text(draw: ImageDraw.ImageDraw, xy, value, size=20, fill="#244850", bold=False):
    draw.text((xy[0] * SCALE, xy[1] * SCALE), value, font=font(size, bold), fill=c(fill))


def wrapped(draw: ImageDraw.ImageDraw, xy, value, chars, size=20, fill="#244850", bold=False, leading=1.18):
    y = xy[1]
    for raw in value.split("\n"):
        for part in textwrap.wrap(raw, width=chars) or [""]:
            text(draw, (xy[0], y), part, size=size, fill=fill, bold=bold)
            y += int(size * leading)
    return y


def box(draw, xy, title, lines, kind="default", w=None, h=None):
    x, y, x2, y2 = xy if w is None else (xy[0], xy[1], xy[0] + w, xy[1] + h)
    palette = {
        "default": ("#ffffff", "#bfd3d1"),
        "ai": ("#f1f7ff", "#9ab9d2"),
        "store": ("#fffaf0", "#e2c878"),
        "obs": ("#f7f2ea", "#cdb889"),
    }[kind]
    rect(draw, (x + 8, y + 10, x2 + 8, y2 + 10), c("#dbe5e3"), None, radius=20, width=0)
    rect(draw, (x, y, x2, y2), c(palette[0]), c(palette[1]), radius=20, width=2)
    text(draw, (x + 28, y + 28), title, size=24, fill="#12343b", bold=True)
    yy = y + 68
    for item in lines:
        yy = wrapped(draw, (x + 28, yy), item, chars=max(25, int((x2 - x - 56) / 12)), size=17, fill="#35565d")
        yy += 4


img = Image.new("RGBA", (W * SCALE, H * SCALE), c("#f3f6f2"))
draw = ImageDraw.Draw(img)

for yy in range(H * SCALE):
    t = yy / (H * SCALE)
    r = int(246 * (1 - t) + 232 * t)
    g = int(241 * (1 - t) + 240 * t)
    b = int(232 * (1 - t) + 247 * t)
    draw.line([(0, yy), (W * SCALE, yy)], fill=(r, g, b, 255))

rect(draw, (70, 54, 1730, 174), c("#0f513f"), None, radius=28, width=0)
draw.rectangle((900 * SCALE, 54 * SCALE, 1730 * SCALE, 174 * SCALE), fill=c("#24496c"))
text(draw, (115, 88), "AI Lecture Bot: High Level Architecture", size=45, fill="#ffffff", bold=True)
text(draw, (118, 139), "ClassCatchup flow: transcript ingestion, grounded RAG chat, summaries, memory, and persistence", size=20, fill="#eaf7f4")

rect(draw, (70, 218, 390, 1010), (255, 255, 255, 105), c("#ccd8d6"), radius=24, width=2)
text(draw, (100, 248), "CLIENT + EDGE API", size=20, fill="#0f513f", bold=True)
box(draw, (112, 292, 348, 442), "Student / Admin", ["ClassCatchup chat UI", "Lecturebot admin upload", "Next.js pages"])
box(draw, (112, 492, 348, 682), "Next.js API", ["/classcatchup/upload", "/classcatchup/chat", "/sessions, /transcripts", "auth + internal JWT"])
box(draw, (112, 742, 348, 884), "Redis Cache", ["session lists", "messages + transcripts"], "store")

rect(draw, (445, 218, 1286, 1010), (255, 255, 255, 112), c("#ccd8d6"), radius=24, width=2)
text(draw, (478, 248), "FASTAPI BACKEND (/api)", size=20, fill="#0f513f", bold=True)
box(draw, (500, 292, 785, 452), "API Router", ["rate limit dependency", "payload dispatch", "lecture chat vs feasibility flow"])
box(draw, (500, 512, 785, 786), "Transcript Ingestion", ["accept .txt / .vtt upload", "convert VTT + clean text", "create asset + metadata rows", "chunk transcript", "FastEmbed vectors", "BAAI/bge-small-en-v1.5, 384 dims"])
box(draw, (500, 824, 785, 960), "Lifecycle", ["metadata PATCH", "reprocess via shadow collection"])
box(draw, (890, 292, 1238, 960), "Lecture LangGraph", ["1. analyze question + history", "2A. whole transcript summary", "2B. retrieve top-k chunks", "3. relevance gate", "4. grounded answer / refusal", "5. summarize memory", "compiled in lecturebot/graph.py"], "ai")

rect(draw, (1330, 218, 1730, 1010), (255, 255, 255, 112), c("#ccd8d6"), radius=24, width=2)
text(draw, (1360, 248), "DATA + SERVICES", size=20, fill="#0f513f", bold=True)
box(draw, (1372, 292, 1688, 454), "PostgreSQL", ["lecture_chat_sessions", "lecture_messages", "assets + metadata", "summary cache + memory"], "store")
box(draw, (1372, 486, 1688, 638), "Qdrant", ["lecture_transcripts", "top-k vector search", "local or remote backend"], "store")
box(draw, (1372, 670, 1688, 812), "OpenAI LLM", ["question analysis", "answers", "summary generation"], "ai")
box(draw, (1372, 844, 1688, 986), "Observability", ["HTTP logs", "LangSmith / Axiom", "RAG metrics"], "obs")

box(draw, (500, 1030, 785, 1150), "Transcript Text", ["stored on metadata rows with object_path"], "store")
box(draw, (890, 1030, 1238, 1150), "Qdrant Backup", ["Docker sidecar snapshots to GCS when configured"], "store")

blue = c("#244850")
teal = c("#0d7464")
gold = (140, 100, 24, 210)
line(draw, [(348, 366), (500, 366)], blue)
text(draw, (390, 332), "requests", size=15, fill="#496970", bold=True)
line(draw, [(348, 590), (430, 590), (430, 404), (500, 404)], blue)
text(draw, (360, 562), "proxy + JWT", size=15, fill="#496970", bold=True)
line(draw, [(642, 452), (642, 512)], teal)
text(draw, (660, 474), "upload", size=15, fill="#496970", bold=True)
line(draw, [(785, 632), (890, 632)], teal)
text(draw, (802, 606), "clean chunks", size=15, fill="#496970", bold=True)
line(draw, [(785, 366), (890, 366)], blue)
text(draw, (812, 332), "chat invoke", size=15, fill="#496970", bold=True)

line(draw, [(785, 598), (830, 598), (830, 250), (1372, 372)], gold, width=2)
text(draw, (1032, 268), "asset rows + text", size=15, fill="#6e5a2b", bold=True)
line(draw, [(785, 706), (840, 706), (840, 998), (1290, 998), (1290, 558), (1372, 558)], gold, width=2)
line(draw, [(785, 892), (858, 892), (858, 1018), (1310, 1018), (1310, 412), (1372, 412)], gold, width=2)

line(draw, [(1238, 382), (1372, 382)], blue, width=3)
text(draw, (1260, 334), "load session", size=15, fill="#496970", bold=True)
line(draw, [(1238, 630), (1372, 562)], blue, width=3)
text(draw, (1256, 588), "retrieve", size=15, fill="#496970", bold=True)
line(draw, [(1238, 732), (1372, 734)], blue, width=3)
text(draw, (1260, 706), "LLM calls", size=15, fill="#496970", bold=True)
line(draw, [(1238, 842), (1372, 424)], blue, width=3)
text(draw, (1256, 804), "save memory", size=15, fill="#496970", bold=True)
line(draw, [(1238, 902), (1372, 914)], blue, width=3)

line(draw, [(348, 812), (500, 1092)], blue, width=3)
text(draw, (358, 868), "cached UI reads", size=15, fill="#496970", bold=True)
line(draw, [(1064, 1030), (1372, 590)], gold, width=2)

rect(draw, (86, 1040, 390, 1136), c("#fffdf7"), c("#d4c6a4"), radius=18, width=2)
rect(draw, (112, 1062, 188, 1092), teal, None, radius=14, width=0)
text(draw, (128, 1069), "MAIN", size=15, fill="#ffffff", bold=True)
text(draw, (208, 1067), "green = ingestion", size=17, fill="#5d4a22", bold=True)
rect(draw, (112, 1100, 188, 1130), blue, None, radius=14, width=0)
text(draw, (129, 1107), "CHAT", size=15, fill="#ffffff", bold=True)
text(draw, (208, 1105), "blue = question flow", size=17, fill="#5d4a22", bold=True)

img = img.resize((W, H), Image.Resampling.LANCZOS)
img.save(OUT)
print(OUT)
