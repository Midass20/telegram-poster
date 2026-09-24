"""
Публикует один пост с новостью про IT/ИИ в Telegram-канал.
Источники: RSS-ленты новостных сайтов. Без LLM — берёт заголовок и
описание прямо из RSS, картинку из RSS-enclosure или og:image статьи.
Запускается по расписанию через Windows Task Scheduler (см. setup_schedule.ps1).
"""
import html
import json
import os
import random
import re
import sys
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
HISTORY_FILE = BASE_DIR / "history.json"
LOG_FILE = BASE_DIR / "post_log.txt"

# (url, lang) — английские источники переводятся на русском через MyMemory.
# Только тематические ленты (IT/AI), не общесайтовые — иначе залетают промо/шопинг-статьи.
FEEDS = [
    ("https://habr.com/ru/rss/hubs/artificial_intelligence/articles/all/?fl=ru", "ru"),
    ("https://vc.ru/rss/all", "ru"),
    ("https://www.ixbt.com/export/news.rss", "ru"),
    ("https://3dnews.ru/news/rss/", "ru"),
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "en"),
    ("https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "en"),
    ("https://www.wired.com/feed/tag/ai/latest/rss", "en"),
    ("https://feeds.arstechnica.com/arstechnica/technology-lab", "en"),
]

MIN_TEXT_LEN = 500  # если из RSS вышло меньше — пробуем дотянуть текст со страницы статьи
FALLBACK_IMAGE_QUERY_DEFAULT = "technology artificial intelligence"

# страховка от рекламных/шопинг-статей, которые иногда просачиваются даже в тематические ленты
OFFTOPIC_TITLE_RE = re.compile(
    r"\b(promo code|discount|coupon|% off|deal of the day|best deals|sale)\b|"
    r"(промокод|скидк\w+ %|распродаж)",
    re.I,
)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) telegram-poster-bot/1.0"
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096
READ_MORE_LABEL = "Читать далее..."


def log(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    if sys.stdout is not None:
        try:
            print(line)
        except Exception:
            pass
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_env() -> dict:
    env = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def load_history() -> list:
    if not HISTORY_FILE.exists():
        return []
    return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))


def save_history(history: list) -> None:
    history = history[-200:]
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def http_get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


# подписи под фото вида "Источник изображения: ...", "Фото: ...", ссылки-источники
IMAGE_CREDIT_RE = re.compile(
    r"^(источник\s*(изображени|фото|картинк)|фото\s*:|изображени\w*\s*:|photo\s*:|image\s*:|credit\s*:)",
    re.I,
)


BOILERPLATE_KEYWORDS = (
    "роскомнадзор", "учредитель сми", "регистрационный номер",
    "адрес редакции", "все права защищены", "свидетельство о регистрации",
    "erid:", "реклама.", "18+",
)


def is_image_credit_line(text: str) -> bool:
    if IMAGE_CREDIT_RE.match(text.strip()):
        return True
    # строки вида "ithome // Corsair // https://..." — перечисление источников через //
    if "//" in text and len(text) < 200 and re.search(r"https?://", text):
        return True
    lowered = text.lower()
    if any(kw in lowered for kw in BOILERPLATE_KEYWORDS):
        return True
    return False


def clean_html_block(html_str: str) -> str:
    """Разбивает HTML-блок на параграфы и убирает подписи-источники фото."""
    if not html_str:
        return ""
    paragraphs = re.findall(r"<p\b[^>]*>(.*?)</p>", html_str, re.I | re.S)
    if not paragraphs:
        return strip_html(html_str)
    parts = [strip_html(p) for p in paragraphs]
    parts = [p for p in parts if p and not is_image_credit_line(p)]
    return " ".join(parts)


def parse_feed(xml_bytes: bytes) -> list:
    ns = {
        "media": "http://search.yahoo.com/mrss/",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = clean_html_block(item.findtext("description") or "")
        content_encoded = clean_html_block(item.findtext("content:encoded", None, ns) or "")
        if len(content_encoded) > len(desc):
            desc = content_encoded
        image = None
        enclosure = item.find("enclosure")
        if enclosure is not None and "image" in (enclosure.get("type") or ""):
            image = enclosure.get("url")
        if image is None:
            media_content = item.find("media:content", ns)
            if media_content is not None and "image" in (media_content.get("type") or media_content.get("medium") or "image"):
                image = media_content.get("url")
        if title and link:
            items.append({"title": title, "link": link, "desc": desc, "image": image})
    return items


def find_og_image(article_url: str) -> str | None:
    page = fetch_article_html(article_url)
    if not page:
        return None
    m = re.search(r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', page, re.I)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']og:image["\']', page, re.I)
    return m.group(1) if m else None


_article_html_cache: dict[str, str] = {}


def fetch_article_html(article_url: str) -> str | None:
    if article_url in _article_html_cache:
        return _article_html_cache[article_url]
    try:
        page = http_get(article_url, timeout=10).decode("utf-8", errors="ignore")
    except Exception as e:
        log(f"  page fetch failed for {article_url}: {e}")
        page = None
    _article_html_cache[article_url] = page
    return page


def extract_article_text(article_url: str, max_len: int = 1200) -> str:
    page = fetch_article_html(article_url)
    if not page:
        return ""
    paragraphs = re.findall(r"<p\b[^>]*>(.*?)</p>", page, re.I | re.S)
    text_parts = []
    total = 0
    for raw in paragraphs:
        clean = strip_html(raw)
        if len(clean) < 40:
            continue
        if is_image_credit_line(clean):
            continue
        text_parts.append(clean)
        total += len(clean)
        if total >= max_len:
            break
    return " ".join(text_parts)


def translate_chunk(text: str, source_lang: str, target_lang: str = "ru") -> str:
    params = urllib.parse.urlencode({"q": text, "langpair": f"{source_lang}|{target_lang}"})
    url = f"https://api.mymemory.translated.net/get?{params}"
    try:
        data = json.loads(http_get(url, timeout=15).decode())
        translated = data.get("responseData", {}).get("translatedText", "")
        return html.unescape(translated) if translated else text
    except Exception as e:
        log(f"  translation chunk failed: {e}")
        return text


def translate_text(text: str, source_lang: str = "en") -> str:
    if not text:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) + 1 > 450:
            if current:
                chunks.append(current)
            current = s
        else:
            current = f"{current} {s}".strip()
    if current:
        chunks.append(current)
    return " ".join(translate_chunk(c, source_lang) for c in chunks)


def fallback_image(query: str) -> str | None:
    q = urllib.parse.quote(query or FALLBACK_IMAGE_QUERY_DEFAULT)
    url = f"https://api.openverse.org/v1/images/?q={q}&license_type=commercial,modification&page_size=5"
    try:
        data = json.loads(http_get(url, timeout=10).decode())
        results = data.get("results") or []
        for r in results:
            img_url = r.get("url")
            if img_url:
                return img_url
    except Exception as e:
        log(f"  fallback image search failed: {e}")
    return None


def image_search_query(title: str, lang: str) -> str:
    if lang == "en":
        words = re.findall(r"[A-Za-z][A-Za-z0-9']{2,}", title)
        stop = {"the", "and", "for", "with", "from", "this", "that", "new", "how", "why", "what"}
        words = [w for w in words if w.lower() not in stop]
        if words:
            return " ".join(words[:4])
    else:
        latin = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", title)
        if latin:
            return " ".join(latin[:3])
    return FALLBACK_IMAGE_QUERY_DEFAULT


def pick_article(history: list) -> dict | None:
    seen_urls = {h["url"] for h in history}
    feeds = FEEDS[:]
    random.shuffle(feeds)
    for feed_url, lang in feeds:
        try:
            xml_bytes = http_get(feed_url)
            items = parse_feed(xml_bytes)
        except Exception as e:
            log(f"Feed failed: {feed_url} ({e})")
            continue
        for item in items:
            if item["link"] not in seen_urls:
                if OFFTOPIC_TITLE_RE.search(item["title"]):
                    log(f"  skipping off-topic: {item['title'][:60]}")
                    continue
                if len(item["desc"]) < MIN_TEXT_LEN:
                    fuller = extract_article_text(item["link"])
                    if len(fuller) > len(item["desc"]):
                        item["desc"] = fuller
                img_query = image_search_query(item["title"], lang)
                if lang == "en":
                    log(f"  translating from en: {item['title'][:60]}")
                    item["title"] = translate_text(item["title"], "en")
                    item["desc"] = translate_text(item["desc"], "en")
                if not item["image"]:
                    item["image"] = find_og_image(item["link"])
                if not item["image"]:
                    item["image"] = fallback_image(img_query)
                item["feed"] = feed_url
                return item
    return None


def truncate_to_sentence(text: str, room: int) -> str:
    if len(text) <= room:
        return text
    cut = text[:room]
    # ищем конец последнего полного предложения в пределах бюджета
    matches = list(re.finditer(r"[.!?](?:\s|$)", cut))
    if matches:
        end = matches[-1].end()
        return cut[:end].rstrip()
    # ни одного целого предложения не влезло — обрезаем по границе слова
    return cut.rsplit(" ", 1)[0].rstrip()


HASHTAG_RULES = [
    (re.compile(r"\bИИ\b|искусственн\w+ интеллект|нейросет\w+|neural|GPT|LLM|Claude|Gemini|Grok", re.I), "#ИИ"),
    (re.compile(r"смартфон|iphone|android|процессор|видеокарт|ноутбук|гаджет|chip|processor", re.I), "#гаджеты"),
    (re.compile(r"стартап|инвестици|венчур|startup|funding|раунд", re.I), "#стартапы"),
    (re.compile(r"игр\w+|game|steam|playstation|xbox", re.I), "#игры"),
    (re.compile(r"приложени\w+|app store|google play|обновлени\w+", re.I), "#приложения"),
]


def pick_hashtags(title: str, desc: str, max_tags: int = 3) -> list[str]:
    text = f"{title} {desc}"
    tags = ["#технологии"]
    for pattern, tag in HASHTAG_RULES:
        if pattern.search(text) and tag not in tags:
            tags.append(tag)
        if len(tags) >= max_tags:
            break
    return tags


def build_caption(item: dict, has_image: bool) -> str:
    title = item["title"]
    desc = item["desc"]
    link = item["link"]
    hashtags = " ".join(pick_hashtags(title, desc))
    # Telegram считает лимит по видимому тексту, ссылка в href в него не входит.
    limit = CAPTION_LIMIT if has_image else TEXT_LIMIT
    header = f"<b>{html.escape(title)}</b>\n\n"
    read_more = f"\n\n<a href=\"{html.escape(link)}\">{READ_MORE_LABEL}</a>"
    footer = f"\n\n{hashtags}"
    visible_len = len(title) + 2 + 2 + len(READ_MORE_LABEL) + len(hashtags) + 2
    room = limit - visible_len - 10
    if room < 0:
        room = 0
    desc = truncate_to_sentence(desc, room)
    return header + html.escape(desc) + read_more + footer


def telegram_call(url: str, params: dict) -> dict:
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")
        try:
            return json.loads(body)
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}: {body[:300]}"}


def telegram_call_multipart(url: str, fields: dict, file_field: str, filename: str, file_bytes: bytes) -> dict:
    boundary = "----telegrampostboundary"
    parts = []
    for key, value in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode())
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n".encode()
    )
    parts.append(file_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": UA,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode(errors="ignore")
        try:
            return json.loads(body_txt)
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}: {body_txt[:300]}"}


def download_image(url: str, max_bytes: int = 9_000_000) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes or len(data) == 0:
                return None
            return data
    except Exception as e:
        log(f"  image download failed for {url}: {e}")
        return None


def telegram_post(token: str, chat_id: str, item: dict) -> dict:
    api = f"https://api.telegram.org/bot{token}"
    image_bytes = None
    if item.get("image"):
        image_bytes = download_image(item["image"])
        if image_bytes is None:
            log("  could not download image, posting without photo")

    caption = build_caption(item, has_image=bool(image_bytes))

    if image_bytes:
        result = telegram_call_multipart(
            f"{api}/sendPhoto",
            {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            "photo", "image.jpg", image_bytes,
        )
        if not result.get("ok"):
            log(f"  sendPhoto (upload) failed ({result.get('description')}), falling back to sendMessage")
            result = telegram_call(f"{api}/sendMessage", {
                "chat_id": chat_id,
                "text": caption,
                "parse_mode": "HTML",
            })
    else:
        result = telegram_call(f"{api}/sendMessage", {
            "chat_id": chat_id,
            "text": caption,
            "parse_mode": "HTML",
        })
    return result


MIN_INTERVAL_MIN = 110  # расписание тикает чаще, чем постим: пост не раньше чем через ~2ч после прошлого


def minutes_since_last_post(history: list) -> float | None:
    dates = []
    for h in history:
        try:
            dates.append(datetime.fromisoformat(h["date"]))
        except (KeyError, ValueError):
            continue
    if not dates:
        return None
    return (datetime.now(timezone.utc) - max(dates)).total_seconds() / 60


def main() -> int:
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        log("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env")
        return 1

    history = load_history()

    if os.environ.get("FORCE_POST") != "1":
        since = minutes_since_last_post(history)
        if since is not None and since < MIN_INTERVAL_MIN:
            log(f"Not due yet: last post {since:.0f} min ago (< {MIN_INTERVAL_MIN}), skipping")
            return 0

    item = pick_article(history)
    if item is None:
        log("No new article found across all feeds (all already posted recently)")
        return 1

    log(f"Selected: {item['title']} ({item['link']}) image={'yes' if item['image'] else 'no'}")
    result = telegram_post(token, chat_id, item)
    if result.get("ok"):
        log(f"Posted OK: message_id={result['result'].get('message_id')}")
        history.append({
            "url": item["link"],
            "title": item["title"],
            "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        save_history(history)
        return 0
    else:
        log(f"Telegram API error: {result}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
