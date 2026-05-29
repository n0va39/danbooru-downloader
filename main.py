"""Danbooru Clean Downloader — 단부루 API 기반 이미지 다운로더."""

import os
import json
import time
import re
import threading
import queue
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from curl_cffi import requests as curl_requests

import customtkinter as ctk
from tkinter import filedialog, messagebox

# ── 설정 ─────────────────────────────────────────────

CONFIG_FILE = "config.json"
DANBOORU_API = "https://danbooru.donmai.us"
APP_UA = "danbooru-clean-downloader/1.0"

LANG_LABELS = {"ko": "한국어", "en": "English"}
LABEL_LANGS = {v: k for k, v in LANG_LABELS.items()}

NAMING_LABELS = {
    "ko": {"id": "ID만", "tags_id": "태그+ID", "original": "원본 이름"},
    "en": {"id": "ID only", "tags_id": "Tags + ID", "original": "Original name"},
}
NAMING_VALUES = {
    lang: {label: key for key, label in labels.items()}
    for lang, labels in NAMING_LABELS.items()
}

DEFAULT_TAG_CATEGORY_ORDER = ["meta", "artist", "character", "copyright", "general"]
TAG_CATEGORY_LABELS = {
    "meta": "Meta",
    "artist": "Artist",
    "character": "Character",
    "copyright": "Copyright",
    "general": "General",
}
TAG_CATEGORY_KEYS = {
    "meta": "tag_string_meta",
    "artist": "tag_string_artist",
    "character": "tag_string_character",
    "copyright": "tag_string_copyright",
    "general": "tag_string_general",
}

TEXT = {
    "ko": {
        "title": "Danbooru Downloader",
        "search_settings": "검색 설정",
        "include_tags": "포함 태그:",
        "count": "개수 조회",
        "secondary_filter": "2차 필터:",
        "ratings": "레이팅:",
        "download_limit": "다운로드 수:",
        "delay": "지연 시간(초):",
        "naming": "파일명 규칙:",
        "save_settings": "저장 설정",
        "save_path": "저장 경로:",
        "browse": "선택",
        "account": "Danbooru 계정 (선택):",
        "save_txt": "태그 .txt 파일 동시 저장 (Lora 학습용)",
        "replace_underscores": "태그 저장 시 _ 를 공백으로 변환",
        "artist_prefix": "Artist 태그 접두사:",
        "tag_categories": "저장할 태그 항목 (드래그로 순서 변경):",
        "download": "다운로드",
        "downloading": "다운로드 중...",
        "stop": "중지",
        "idle": "대기 중",
        "err": "오류",
        "need_tags": "태그를 입력하세요.",
        "need_path": "저장 경로를 지정하세요.",
        "bad_limit": "다운로드 수는 1 이상 정수여야 합니다.",
        "bad_delay": "지연 시간은 0 이상의 숫자여야 합니다.",
        "need_rating": "레이팅을 하나 이상 선택하세요.",
        "need_category": "저장할 태그 항목을 하나 이상 선택하세요.",
        "query_log": "검색: {query}",
        "api_error": "API 오류: {error}",
        "found": "대상 {total}개 확보",
        "none": "대상 없음",
        "result": "성공 {ok} / 실패 {fail}",
        "fail_item": "[실패] {name}: {error}",
        "counting": "'{tags}' 개수 조회 중...",
        "count_result": "결과: {count:,}개",
        "count_title": "조회 결과",
        "count_body": "{tags}\n\n{count:,}개",
        "count_fail": "조회 실패: {error}",
        "done_title": "완료",
        "end_title": "종료",
        "move_up": "위로",
        "move_down": "아래로",
    },
    "en": {
        "title": "Danbooru Downloader",
        "search_settings": "Search Settings",
        "include_tags": "Include Tags:",
        "count": "Count",
        "secondary_filter": "Secondary Filter:",
        "ratings": "Ratings:",
        "download_limit": "Download Limit:",
        "delay": "Delay (sec):",
        "naming": "Filename Rule:",
        "save_settings": "Save Settings",
        "save_path": "Save Path:",
        "browse": "Browse",
        "account": "Danbooru Account (optional):",
        "save_txt": "Save tag .txt files for LoRA training",
        "replace_underscores": "Replace _ with spaces in saved tags",
        "artist_prefix": "Artist tag prefix:",
        "tag_categories": "Tag categories to save (drag to reorder):",
        "download": "Download",
        "downloading": "Downloading...",
        "stop": "Stop",
        "idle": "Idle",
        "err": "Error",
        "need_tags": "Enter tags.",
        "need_path": "Choose a save path.",
        "bad_limit": "Download limit must be a positive integer.",
        "bad_delay": "Delay must be a number greater than or equal to 0.",
        "need_rating": "Select at least one rating.",
        "need_category": "Select at least one tag category.",
        "query_log": "Search: {query}",
        "api_error": "API error: {error}",
        "found": "Found {total} target posts",
        "none": "No targets",
        "result": "Success {ok} / Failed {fail}",
        "fail_item": "[Failed] {name}: {error}",
        "counting": "Counting '{tags}'...",
        "count_result": "Result: {count:,}",
        "count_title": "Count Result",
        "count_body": "{tags}\n\n{count:,} posts",
        "count_fail": "Count failed: {error}",
        "done_title": "Done",
        "end_title": "Stopped",
        "move_up": "Move up",
        "move_down": "Move down",
    },
}


def load_config():
    defaults = {
        "tags": "", "exclude_tags": "",
        "download_path": str(Path.home() / "Downloads" / "Danbooru"),
        "limit": 100, "ratings": ["g", "s"],
        "username": "", "api_key": "",
        "naming": "id", "save_txt": True, "replace_tag_underscores": True,
        "artist_prefix": "",
        "tag_categories": ["general"],
        "tag_category_order": DEFAULT_TAG_CATEGORY_ORDER.copy(),
        "delay": 0.5, "language": "ko",
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            has_tag_categories = "tag_categories" in cfg
            for k, v in defaults.items():
                cfg.setdefault(k, v)
            if not has_tag_categories:
                cfg["tag_categories"] = (
                    ["general"] if cfg.get("save_general_only", True)
                    else DEFAULT_TAG_CATEGORY_ORDER.copy()
                )
            cfg["tag_category_order"] = normalize_tag_category_order(
                cfg.get("tag_category_order", DEFAULT_TAG_CATEGORY_ORDER)
            )
            return cfg
        except Exception:
            pass
    return defaults


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def normalize_tag_category_order(order):
    normalized = [key for key in order if key in DEFAULT_TAG_CATEGORY_ORDER]
    normalized.extend(key for key in DEFAULT_TAG_CATEGORY_ORDER if key not in normalized)
    return normalized


def format_saved_tag(tag):
    return tag.replace("_", " ")


# ── Danbooru API 클라이언트 ──────────────────────────

class DanbooruAPI:
    """Danbooru 공식 API 규격에 맞춘 HTTP 클라이언트."""

    def __init__(self, username="", api_key=""):
        self.session = curl_requests.Session(impersonate="chrome")
        self.auth = (username, api_key) if username and api_key else None
        name = username or "anonymous"
        self.session.headers.update({
            "User-Agent": f"{APP_UA} (by {name})",
            "Accept": "application/json",
        })

    def get(self, endpoint, params=None, timeout=15):
        """GET 요청 + 429 Retry-After 자동 처리."""
        url = f"{DANBOORU_API}/{endpoint}"
        for _ in range(3):
            r = self.session.get(url, params=params, auth=self.auth, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "5"))
                time.sleep(wait)
                continue
            r.raise_for_status()
        return r

    def count_posts(self, tags):
        r = self.get("counts/posts.json", {"tags": tags})
        return r.json().get("counts", {}).get("posts", 0)

    def search_posts(self, tags, limit=100, page=None):
        params = {"tags": tags, "limit": min(limit, 200)}
        if page is not None:
            params["page"] = page
        r = self.get("posts.json", params)
        return r.json()

    def download_file(self, url, dest, stop_check=None):
        r = self.session.get(url, auth=self.auth, stream=True, timeout=30)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                if stop_check and stop_check():
                    return False
                f.write(chunk)
        return True


# ── 다운로드 엔진 ────────────────────────────────────

class Downloader:
    def __init__(self, api, tags, exclude, path, limit, ratings,
                 naming, save_txt, replace_tag_underscores, tag_categories,
                 artist_prefix, delay, language, log, progress, on_done):
        self.api = api
        self.tags = tags
        self.exclude = exclude
        self.path = Path(path)
        self.limit = limit
        self.ratings = set(ratings)
        self.naming = naming
        self.save_txt = save_txt
        self.replace_tag_underscores = replace_tag_underscores
        self.tag_categories = tag_categories
        self.artist_prefix = artist_prefix
        self.delay = delay
        self.language = language
        self.log = log
        self.progress = progress
        self.on_done = on_done
        self.stop = False
        self.ok = 0
        self.fail = 0

    def _t(self, key, **kwargs):
        return TEXT[self.language][key].format(**kwargs)

    def build_query(self):
        parts = [t.strip() for t in re.split(r'[\s,]+', self.tags) if t.strip()]
        return " ".join(parts)

    def _post_tags(self, post):
        return set(post.get("tag_string", "").split())

    def _match_secondary_filter(self, post):
        expr = self.exclude.strip()
        if not expr:
            return True

        post_tags = self._post_tags(post)
        groups = [g.strip() for g in re.split(r'[\s,]+', expr) if g.strip()]
        for group in groups:
            exclude = group.startswith("-")
            raw = group[1:] if exclude else group
            options = [t.strip() for t in raw.split("|") if t.strip()]
            if not options:
                continue

            matched = any(tag in post_tags for tag in options)
            if exclude and matched:
                return False
            if not exclude and not matched:
                return False
        return True

    def run(self):
        self.path.mkdir(parents=True, exist_ok=True)
        query = self.build_query()
        self.log(self._t("query_log", query=query))

        # 포스트 수집 (페이지네이션)
        posts = []
        last_id = None
        while len(posts) < self.limit and not self.stop:
            need = 200
            page = f"b{last_id}" if last_id else 1
            try:
                batch = self.api.search_posts(query, limit=need, page=page)
            except Exception as e:
                self.log(self._t("api_error", error=e), "ERROR")
                break
            if not batch:
                break
            for p in batch:
                if p.get("rating") not in self.ratings:
                    continue
                if not (p.get("file_url") or p.get("large_file_url")):
                    continue
                if not self._match_secondary_filter(p):
                    continue
                posts.append(p)
                if len(posts) >= self.limit:
                    break
            last_id = batch[-1].get("id")
            time.sleep(1.0)

        total = len(posts)
        self.log(self._t("found", total=total))
        if total == 0:
            self.on_done(True, self._t("none"))
            return

        # 멀티스레드 다운로드
        done = 0
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(self._dl, p): p for p in posts}
            for f in as_completed(futures):
                if self.stop:
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                try:
                    if f.result():
                        self.ok += 1
                    else:
                        self.fail += 1
                except Exception:
                    self.fail += 1
                done += 1
                self.progress(done / total)

        msg = self._t("result", ok=self.ok, fail=self.fail)
        self.log(msg, "SUCCESS" if not self.stop else "WARNING")
        self.on_done(not self.stop, msg)

    def _dl(self, post):
        if self.stop:
            return False
        pid = post["id"]
        url = post.get("file_url") or post.get("large_file_url")
        ext = post.get("file_ext", url.rsplit(".", 1)[-1].split("?")[0])
        if self.naming == "original":
            # 메타데이터를 사용하여 원본 파일명 형식을 복원하되, 고유 식별자는 MD5 대신 포스트 ID(pid) 사용
            chars = post.get("tag_string_character", "").split()
            copys = post.get("tag_string_copyright", "").split()
            artists = post.get("tag_string_artist", "").split()
            
            parts = []
            if chars:
                parts.extend(chars)
            if copys:
                parts.extend(copys)
            if not parts:
                parts.extend(post.get("tag_string_general", "").split()[:4])
            
            desc = "_".join(parts)
            if artists:
                desc = f"{desc}_drawn_by_" + "_".join(artists)
            
            desc = re.sub(r'_+', '_', desc).strip('_')
            if desc:
                name = f"__{desc}__{pid}.{ext}"
            else:
                name = f"{pid}.{ext}"
            
            name = re.sub(r'[\\/*?:"<>|]', "", name)
            # 윈도우 경로 길이 에러 방지 위해 파일명 길이 제어
            if len(name) > 160:
                name = f"__{name[2:100]}__{pid}.{ext}"
                name = re.sub(r'[\\/*?:"<>|]', "", name)
        elif self.naming == "tags_id":
            tags = "_".join(post.get("tag_string", "").split()[:4])
            tags = re.sub(r'[\\/*?:"<>|]', "", tags)[:50]
            name = f"{tags}_{pid}.{ext}"
        else:
            name = f"{pid}.{ext}"
        dest = self.path / name

        if dest.exists():
            if self.save_txt:
                self._save_txt(post, dest)
            return True

        try:
            ok = self.api.download_file(url, dest, lambda: self.stop)
            if ok and self.save_txt:
                self._save_txt(post, dest)
            if self.delay > 0:
                time.sleep(self.delay)
            return ok
        except Exception as e:
            self.log(self._t("fail_item", name=name, error=e), "ERROR")
            if dest.exists():
                dest.unlink(missing_ok=True)
            return False

    def _save_txt(self, post, img_path):
        txt = img_path.with_suffix(".txt")
        if txt.exists():
            return
        selected = set(self.tag_categories)
        tags = []
        for category in self.tag_categories:
            if category in selected and category in TAG_CATEGORY_KEYS:
                for tag in post.get(TAG_CATEGORY_KEYS[category], "").split():
                    if self.replace_tag_underscores:
                        tag = format_saved_tag(tag)
                    if category == "artist" and self.artist_prefix:
                        tag = f"{self.artist_prefix}{tag}"
                    tags.append(tag)
        tags = ", ".join(tags)
        txt.write_text(tags, encoding="utf-8")


# ── GUI ──────────────────────────────────────────────

class App(ctk.CTk):
    BG = "#101116"
    CARD = "#1a1b23"
    INPUT = "#262833"
    BORDER = "#2b2d3d"
    PURPLE = "#a855f7"
    GREEN = "#10b981"
    RED = "#ef4444"
    TEXT = "#e2e8f0"
    DIM = "#94a3b8"
    SELECTED = "#2a1f3d"
    DRAGGING = "#3b275d"

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.lang = self.cfg.get("language", "ko")
        if self.lang not in TEXT:
            self.lang = "ko"
        self.title(self._t("title"))
        self.geometry("960x720")
        self.minsize(900, 680)
        self.configure(fg_color=self.BG)

        self.dl_thread = None
        self.downloader = None
        self.running = False
        self.log_q = queue.Queue()

        self._build_ui()
        self._load_cfg()
        self.after(100, self._poll_log)

    def _t(self, key, **kwargs):
        return TEXT[self.lang][key].format(**kwargs)

    def _change_language(self, label):
        new_lang = LABEL_LANGS.get(label, "ko")
        if new_lang == self.lang:
            return
        self._save_cfg()
        self.lang = new_lang
        self.cfg["language"] = self.lang
        save_config(self.cfg)
        for child in self.winfo_children():
            child.destroy()
        self.title(self._t("title"))
        self._build_ui()
        self._load_cfg()

    def _naming_key(self):
        value = self.m_naming.get()
        if value in NAMING_VALUES[self.lang]:
            return NAMING_VALUES[self.lang][value]
        if "태그" in value or "Tags" in value:
            return "tags_id"
        if "원본" in value or "Original" in value:
            return "original"
        return "id"

    # ── UI 빌드 ──

    def _build_ui(self):
        # 헤더
        hdr = ctk.CTkFrame(self, height=60, fg_color=self.CARD, corner_radius=10, border_width=1, border_color=self.BORDER)
        hdr.pack(fill="x", padx=12, pady=(12, 8))
        ctk.CTkLabel(hdr, text="DANBOORU DOWNLOADER", font=("Segoe UI", 20, "bold"), text_color="#fff").pack(side="left", padx=16, pady=10)
        self.m_lang = ctk.CTkOptionMenu(hdr, values=list(LANG_LABELS.values()),
                                        fg_color=self.INPUT, button_color=self.BORDER,
                                        button_hover_color="#3e415b",
                                        dropdown_fg_color=self.CARD,
                                        dropdown_hover_color="#3e415b",
                                        dropdown_text_color=self.TEXT,
                                        height=30, width=110,
                                        command=self._change_language)
        self.m_lang.pack(side="right", padx=16, pady=10)

        # 본문 2단
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        left_col = ctk.CTkFrame(body, fg_color="transparent")
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 6))
        right = ctk.CTkFrame(body, fg_color=self.CARD, corner_radius=10, border_width=1, border_color=self.BORDER)
        right.pack(side="right", fill="both", expand=True, padx=(6, 0))

        left = ctk.CTkFrame(left_col, fg_color=self.CARD, corner_radius=10, border_width=1, border_color=self.BORDER)
        left.pack(fill="x", padx=0, pady=(0, 8))
        dl_status = ctk.CTkFrame(left_col, fg_color=self.CARD, corner_radius=10, border_width=1, border_color=self.BORDER)
        dl_status.pack(fill="both", expand=True)

        self._build_left(left)
        self._build_right(right)
        self._build_download_status(dl_status)

    def _build_download_status(self, bot):
        self.status = ctk.CTkLabel(bot, text=self._t("idle"), font=("Segoe UI", 11, "bold"), text_color=self.DIM)
        self.status.pack(anchor="w", padx=12, pady=(8, 4))

        self.pbar = ctk.CTkProgressBar(bot, fg_color="#1f2937", progress_color=self.PURPLE, height=6)
        self.pbar.pack(fill="x", padx=12, pady=4)
        self.pbar.set(0)

        self.console = ctk.CTkTextbox(bot, fg_color="#0e0f14", text_color=self.TEXT,
                                       font=("Consolas", 11), corner_radius=6,
                                       border_width=1, border_color="#1e2030")
        self.console.pack(fill="both", expand=True, padx=12, pady=(4, 8))
        self.console.configure(state="disabled")

    def _entry(self, parent, placeholder="", **kw):
        return ctk.CTkEntry(parent, placeholder_text=placeholder,
                            fg_color=self.INPUT, border_color=self.BORDER,
                            text_color="#fff", placeholder_text_color="#8e9bb0",
                            height=30, **kw)

    def _label(self, parent, text):
        return ctk.CTkLabel(parent, text=text, font=("Segoe UI", 11, "bold"), text_color="#cbd5e1")

    def _build_left(self, f):
        ctk.CTkLabel(f, text=self._t("search_settings"), font=("Segoe UI", 14, "bold"), text_color="#fff").pack(anchor="w", padx=12, pady=(12, 8))

        self._label(f, self._t("include_tags")).pack(anchor="w", padx=12)
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 8))
        self.e_tags = self._entry(row, "1girl solo long_hair")
        self.e_tags.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(row, text=self._t("count"), width=70, height=30,
                       fg_color=self.BORDER, hover_color="#3e415b", text_color="#fff",
                       font=("Segoe UI", 11, "bold"), command=self._count).pack(side="right")

        self._label(f, self._t("secondary_filter")).pack(anchor="w", padx=12)
        self.e_exc = self._entry(f, "-comic -chibi cat_ears|dog_ears")
        self.e_exc.pack(fill="x", padx=12, pady=(0, 8))

        self._label(f, self._t("ratings")).pack(anchor="w", padx=12)
        rf = ctk.CTkFrame(f, fg_color="transparent")
        rf.pack(fill="x", padx=12, pady=(0, 8))
        self.rv = {}
        for code, label in [("g", "General"), ("s", "Sensitive"), ("q", "Questionable"), ("e", "Explicit")]:
            v = ctk.StringVar(value="off")
            self.rv[code] = v
            ctk.CTkCheckBox(rf, text=label, variable=v, onvalue="on", offvalue="off",
                            text_color="#cbd5e1", font=("Segoe UI", 10), border_color=self.BORDER).pack(side="left", expand=True)

        row2 = ctk.CTkFrame(f, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(0, 8))
        
        col1 = ctk.CTkFrame(row2, fg_color="transparent")
        col1.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._label(col1, self._t("download_limit")).pack(anchor="w")
        self.e_limit = self._entry(col1)
        self.e_limit.pack(fill="x")

        col2 = ctk.CTkFrame(row2, fg_color="transparent")
        col2.pack(side="left", fill="x", expand=True, padx=(4, 4))
        self._label(col2, self._t("delay")).pack(anchor="w")
        self.e_delay = self._entry(col2, "0.5")
        self.e_delay.pack(fill="x")

        col3 = ctk.CTkFrame(row2, fg_color="transparent")
        col3.pack(side="right", fill="x", expand=True, padx=(4, 0))
        self._label(col3, self._t("naming")).pack(anchor="w")
        self.m_naming = ctk.CTkOptionMenu(col3, values=list(NAMING_LABELS[self.lang].values()),
                                           fg_color=self.INPUT, button_color=self.BORDER,
                                           button_hover_color="#3e415b",
                                           dropdown_fg_color=self.CARD,
                                           dropdown_hover_color="#3e415b",
                                           dropdown_text_color=self.TEXT, height=30)
        self.m_naming.pack(fill="x")

    def _build_right(self, f):
        ctk.CTkLabel(f, text=self._t("save_settings"), font=("Segoe UI", 14, "bold"), text_color="#fff").pack(anchor="w", padx=12, pady=(12, 8))

        self._label(f, self._t("save_path")).pack(anchor="w", padx=12)
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 8))
        self.e_path = self._entry(row)
        self.e_path.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(row, text=self._t("browse"), width=60, height=30,
                       fg_color=self.BORDER, hover_color="#3e415b", text_color="#fff",
                       command=self._browse_dir).pack(side="right")

        self._label(f, self._t("account")).pack(anchor="w", padx=12)
        auth = ctk.CTkFrame(f, fg_color="transparent")
        auth.pack(fill="x", padx=12, pady=(0, 8))
        self.e_user = self._entry(auth, "Username")
        self.e_user.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.e_key = self._entry(auth, "API Key")
        self.e_key.configure(show="*")
        self.e_key.pack(side="right", fill="x", expand=True, padx=(4, 0))

        self.v_txt = ctk.StringVar(value="on")
        self.cb_txt = ctk.CTkCheckBox(f, text=self._t("save_txt"),
                                      variable=self.v_txt, onvalue="on", offvalue="off",
                                      text_color=self.PURPLE, font=("Segoe UI", 11, "bold"),
                                      border_color=self.BORDER)
        self.cb_txt.pack(anchor="w", padx=12, pady=(0, 6))

        self.v_replace_underscores = ctk.StringVar(value="on")
        self.cb_replace_underscores = ctk.CTkCheckBox(f, text=self._t("replace_underscores"),
                                                      variable=self.v_replace_underscores,
                                                      onvalue="on", offvalue="off",
                                                      text_color="#cbd5e1", font=("Segoe UI", 11, "bold"),
                                                      border_color=self.BORDER)
        self.cb_replace_underscores.pack(anchor="w", padx=12, pady=(0, 6))

        self._label(f, self._t("artist_prefix")).pack(anchor="w", padx=12)
        self.e_artist_prefix = self._entry(f, "@")
        self.e_artist_prefix.pack(fill="x", padx=12, pady=(0, 8))

        self._label(f, self._t("tag_categories")).pack(anchor="w", padx=12)
        self.cat_list = ctk.CTkFrame(f, fg_color="transparent")
        self.cat_list.pack(fill="x", padx=12, pady=(0, 12))
        self.tag_cat_vars = {}
        self.tag_cat_checks = []
        self.tag_cat_rows = {}
        self.tag_cat_handles = {}
        self.tag_cat_check_map = {}
        self.tag_cat_move_buttons = {}
        self.tag_category_order = DEFAULT_TAG_CATEGORY_ORDER.copy()
        self.drag_category = None
        for key in DEFAULT_TAG_CATEGORY_ORDER:
            v = ctk.StringVar(value="off")
            self.tag_cat_vars[key] = v
        self._render_tag_category_rows()

        btns = ctk.CTkFrame(f, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 12))
        self.b_start = ctk.CTkButton(btns, text=self._t("download"), font=("Segoe UI", 13, "bold"),
                                      fg_color=self.PURPLE, hover_color="#9333ea",
                                      text_color="#fff", height=36, command=self._start)
        self.b_start.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.b_stop = ctk.CTkButton(btns, text=self._t("stop"), font=("Segoe UI", 13, "bold"),
                                     fg_color="#374151", hover_color=self.RED,
                                     text_color="#fff", height=36, state="disabled",
                                     command=self._stop)
        self.b_stop.pack(side="right", fill="x", expand=True, padx=(4, 0))

    def _render_tag_category_rows(self):
        for child in self.cat_list.winfo_children():
            child.destroy()
        self.tag_cat_checks = []
        self.tag_cat_rows = {}
        self.tag_cat_handles = {}
        self.tag_cat_check_map = {}
        self.tag_cat_move_buttons = {}

        for key in self.tag_category_order:
            selected = self.tag_cat_vars[key].get() == "on"
            dragging = key == self.drag_category
            row_color = self.DRAGGING if dragging else (self.SELECTED if selected else self.INPUT)
            border_color = self.PURPLE if selected or dragging else self.BORDER
            row = ctk.CTkFrame(self.cat_list, fg_color=row_color, corner_radius=6,
                               border_width=1, border_color=border_color)
            row.pack(fill="x", pady=2)
            handle = ctk.CTkLabel(row, text="::", width=24,
                                  text_color=self.PURPLE if selected or dragging else self.DIM,
                                  font=("Segoe UI", 12, "bold"))
            handle.pack(side="left", padx=(8, 0), pady=4)
            cb = ctk.CTkCheckBox(row, text=TAG_CATEGORY_LABELS[key],
                                 variable=self.tag_cat_vars[key],
                                 onvalue="on", offvalue="off",
                                 text_color="#fff" if selected else "#cbd5e1",
                                 font=("Segoe UI", 10, "bold" if selected else "normal"),
                                 border_color=self.PURPLE if selected else self.BORDER,
                                 command=self._refresh_tag_category_selection)
            cb.pack(side="left", fill="x", expand=True, padx=8, pady=4)
            up_btn = ctk.CTkButton(row, text="↑", width=28, height=24,
                                   fg_color=self.BORDER, hover_color="#3e415b",
                                   text_color="#fff",
                                   command=lambda category=key: self._move_category_button(category, -1))
            up_btn.pack(side="left", padx=(0, 4), pady=4)
            down_btn = ctk.CTkButton(row, text="↓", width=28, height=24,
                                     fg_color=self.BORDER, hover_color="#3e415b",
                                     text_color="#fff",
                                     command=lambda category=key: self._move_category_button(category, 1))
            down_btn.pack(side="left", padx=(0, 8), pady=4)

            for widget in (row, handle):
                widget.bind("<ButtonPress-1>", lambda event, category=key: self._start_category_drag(category))
                widget.bind("<B1-Motion>", self._move_category_drag)
                widget.bind("<ButtonRelease-1>", self._finish_category_drag)

            self.tag_cat_rows[key] = row
            self.tag_cat_handles[key] = handle
            self.tag_cat_check_map[key] = cb
            self.tag_cat_move_buttons[key] = (up_btn, down_btn)
            self.tag_cat_checks.append(cb)

    def _refresh_tag_category_selection(self):
        if not hasattr(self, "tag_cat_rows"):
            return
        for key, row in self.tag_cat_rows.items():
            selected = self.tag_cat_vars[key].get() == "on"
            dragging = key == self.drag_category
            row.configure(
                fg_color=self.DRAGGING if dragging else (self.SELECTED if selected else self.INPUT),
                border_color=self.PURPLE if selected or dragging else self.BORDER,
            )
            self.tag_cat_handles[key].configure(text_color=self.PURPLE if selected or dragging else self.DIM)
            self.tag_cat_check_map[key].configure(
                text_color="#fff" if selected else "#cbd5e1",
                font=("Segoe UI", 10, "bold" if selected else "normal"),
                border_color=self.PURPLE if selected else self.BORDER,
            )

    def _move_category_button(self, category, delta):
        if self.running:
            return
        idx = self.tag_category_order.index(category)
        new_idx = max(0, min(len(self.tag_category_order) - 1, idx + delta))
        if idx == new_idx:
            return
        self.tag_category_order.pop(idx)
        self.tag_category_order.insert(new_idx, category)
        self._pack_tag_category_rows()

    def _start_category_drag(self, category):
        if self.running:
            return
        self.drag_category = category
        self._refresh_tag_category_selection()
        self.bind_all("<B1-Motion>", self._move_category_drag)
        self.bind_all("<ButtonRelease-1>", self._finish_category_drag)

    def _move_category_drag(self, event):
        if self.running or not self.drag_category:
            return

        target = len(self.tag_category_order) - 1
        for idx, key in enumerate(self.tag_category_order):
            row = self.tag_cat_rows[key]
            midpoint = row.winfo_rooty() + (row.winfo_height() / 2)
            if event.y_root < midpoint:
                target = idx
                break

        category = self.drag_category
        old = self.tag_category_order.index(category)
        if target > old:
            target -= 1
        if target == old:
            return

        self.tag_category_order.pop(old)
        self.tag_category_order.insert(target, category)
        self._pack_tag_category_rows()

    def _finish_category_drag(self, event):
        if self.drag_category:
            self.drag_category = None
            self._refresh_tag_category_selection()
        self.unbind_all("<B1-Motion>")
        self.unbind_all("<ButtonRelease-1>")

    def _pack_tag_category_rows(self):
        for key in self.tag_category_order:
            self.tag_cat_rows[key].pack_forget()
            self.tag_cat_rows[key].pack(fill="x", pady=2)

    # ── 설정 로드/저장 ──

    def _load_cfg(self):
        c = self.cfg
        self.m_lang.set(LANG_LABELS.get(self.lang, LANG_LABELS["ko"]))
        self.e_tags.insert(0, c["tags"])
        self.e_exc.insert(0, c["exclude_tags"])
        self.e_path.insert(0, c["download_path"])
        self.e_limit.insert(0, str(c["limit"]))
        self.e_delay.insert(0, str(c.get("delay", 0.5)))
        self.e_user.insert(0, c["username"])
        self.e_key.insert(0, c["api_key"])
        for code in "gsqe":
            self.rv[code].set("on" if code in c["ratings"] else "off")
        self.v_txt.set("on" if c["save_txt"] else "off")
        self.v_replace_underscores.set("on" if c.get("replace_tag_underscores", True) else "off")
        self.e_artist_prefix.insert(0, c.get("artist_prefix", ""))
        self.tag_category_order = normalize_tag_category_order(
            c.get("tag_category_order", DEFAULT_TAG_CATEGORY_ORDER)
        )
        selected_categories = set(c.get("tag_categories", ["general"]))
        for key, v in self.tag_cat_vars.items():
            v.set("on" if key in selected_categories else "off")
        self._render_tag_category_rows()
        self.m_naming.set(NAMING_LABELS[self.lang].get(c["naming"], NAMING_LABELS[self.lang]["id"]))

    def _save_cfg(self):
        self.cfg.update({
            "tags": self.e_tags.get().strip(),
            "exclude_tags": self.e_exc.get().strip(),
            "download_path": self.e_path.get().strip(),
            "limit": int(self.e_limit.get().strip() or "100"),
            "delay": float(self.e_delay.get().strip() or "0.5"),
            "ratings": [c for c in "gsqe" if self.rv[c].get() == "on"],
            "username": self.e_user.get().strip(),
            "api_key": self.e_key.get().strip(),
            "save_txt": self.v_txt.get() == "on",
            "replace_tag_underscores": self.v_replace_underscores.get() == "on",
            "artist_prefix": self.e_artist_prefix.get(),
            "tag_categories": self._selected_tag_categories(),
            "tag_category_order": self.tag_category_order,
            "naming": self._naming_key(),
            "language": self.lang,
        })
        save_config(self.cfg)

    def _selected_tag_categories(self):
        return [key for key in self.tag_category_order
                if self.tag_cat_vars[key].get() == "on"]

    # ── 로깅 ──

    def _log(self, msg, level="INFO"):
        self.log_q.put((msg, level))

    def _poll_log(self):
        while not self.log_q.empty():
            msg, level = self.log_q.get_nowait()
            self.console.configure(state="normal")
            ts = time.strftime("[%H:%M:%S]")
            line = f"{ts} [{level}] {msg}\n"
            start = self.console.index("end-1c")
            self.console.insert("end", line)
            end = self.console.index("end-1c")
            color = {"SUCCESS": self.GREEN, "WARNING": "#eab308", "ERROR": self.RED}.get(level, "#cbd5e1")
            tag = f"t{id(msg)}"
            self.console.tag_add(tag, start, end)
            self.console.tag_config(tag, foreground=color)
            self.console.see("end")
            self.console.configure(state="disabled")
        self.after(100, self._poll_log)

    # ── 개수 조회 ──

    def _count(self):
        tags = self.e_tags.get().strip()
        if not tags:
            messagebox.showerror(self._t("err"), self._t("need_tags"))
            return
        threading.Thread(target=self._count_thread, args=(tags,), daemon=True).start()

    def _count_thread(self, tags):
        self._log(self._t("counting", tags=tags))
        try:
            api = DanbooruAPI(self.e_user.get().strip(), self.e_key.get().strip())
            n = api.count_posts(tags)
            self._log(self._t("count_result", count=n), "SUCCESS")
            self.after(0, lambda: messagebox.showinfo(
                self._t("count_title"),
                self._t("count_body", tags=tags, count=n),
            ))
        except Exception as e:
            self._log(self._t("count_fail", error=e), "ERROR")

    # ── 다운로드 ──

    def _start(self):
        if self.dl_thread and self.dl_thread.is_alive():
            return
        path = self.e_path.get().strip()
        if not path:
            messagebox.showerror(self._t("err"), self._t("need_path"))
            return
        try:
            limit = int(self.e_limit.get().strip() or "100")
            assert limit > 0
        except (ValueError, AssertionError):
            messagebox.showerror(self._t("err"), self._t("bad_limit"))
            return
        try:
            delay = float(self.e_delay.get().strip() or "0.5")
            assert delay >= 0
        except (ValueError, AssertionError):
            messagebox.showerror(self._t("err"), self._t("bad_delay"))
            return
        ratings = [c for c in "gsqe" if self.rv[c].get() == "on"]
        if not ratings:
            messagebox.showerror(self._t("err"), self._t("need_rating"))
            return
        if self.v_txt.get() == "on" and not self._selected_tag_categories():
            messagebox.showerror(self._t("err"), self._t("need_category"))
            return

        self._save_cfg()
        self._set_running(True)
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

        api = DanbooruAPI(self.e_user.get().strip(), self.e_key.get().strip())
        self.downloader = Downloader(
            api=api,
            tags=self.e_tags.get().strip(),
            exclude=self.e_exc.get().strip(),
            path=path, limit=limit, ratings=ratings,
            naming=self._naming_key(),
            save_txt=self.v_txt.get() == "on",
            replace_tag_underscores=self.v_replace_underscores.get() == "on",
            tag_categories=self._selected_tag_categories(),
            artist_prefix=self.e_artist_prefix.get(),
            delay=delay,
            language=self.lang,
            log=self._log,
            progress=lambda v: self.after(0, lambda: self.pbar.set(v)),
            on_done=lambda ok, msg: self.after(0, lambda: self._done(ok, msg)),
        )
        self.dl_thread = threading.Thread(target=self.downloader.run, daemon=True)
        self.dl_thread.start()

    def _stop(self):
        if self.downloader:
            self.downloader.stop = True
            self.b_stop.configure(state="disabled")

    def _done(self, ok, msg):
        self._set_running(False)
        self.status.configure(text=msg)
        if ok:
            self.pbar.set(1.0)
            messagebox.showinfo(self._t("done_title"), msg)
        else:
            messagebox.showwarning(self._t("end_title"), msg)
        self.downloader = None

    def _set_running(self, on):
        self.running = on
        s = "disabled" if on else "normal"
        for w in (self.e_tags, self.e_exc, self.e_limit, self.e_delay, self.e_path,
                  self.e_user, self.e_key, self.m_naming, self.cb_txt,
                  self.cb_replace_underscores, self.e_artist_prefix, *self.tag_cat_checks):
            w.configure(state=s)
        for buttons in self.tag_cat_move_buttons.values():
            for button in buttons:
                button.configure(state=s)
        self.b_start.configure(state=s, text=self._t("downloading") if on else self._t("download"))
        self.b_stop.configure(state="normal" if on else "disabled")
        if on:
            self.pbar.set(0)
            self.status.configure(text=self._t("downloading"))

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.e_path.get())
        if d:
            self.e_path.delete(0, "end")
            self.e_path.insert(0, d)


if __name__ == "__main__":
    App().mainloop()
