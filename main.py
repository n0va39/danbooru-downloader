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


def load_config():
    defaults = {
        "tags": "", "exclude_tags": "",
        "download_path": str(Path.home() / "Downloads" / "Danbooru"),
        "limit": 100, "ratings": ["g", "s"],
        "username": "", "api_key": "",
        "naming": "id", "save_txt": True, "replace_tag_underscores": True,
        "tag_categories": ["general"], "delay": 0.5,
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
                    else ["meta", "artist", "copyright", "general"]
                )
            return cfg
        except Exception:
            pass
    return defaults


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


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
                 delay, log, progress, on_done):
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
        self.delay = delay
        self.log = log
        self.progress = progress
        self.on_done = on_done
        self.stop = False
        self.ok = 0
        self.fail = 0

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
        self.log(f"검색: {query}")

        # 포스트 수집 (페이지네이션)
        posts = []
        last_id = None
        while len(posts) < self.limit and not self.stop:
            need = 200
            page = f"b{last_id}" if last_id else 1
            try:
                batch = self.api.search_posts(query, limit=need, page=page)
            except Exception as e:
                self.log(f"API 오류: {e}", "ERROR")
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
        self.log(f"대상 {total}개 확보")
        if total == 0:
            self.on_done(True, "대상 없음")
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

        msg = f"성공 {self.ok} / 실패 {self.fail}"
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
            self.log(f"[실패] {name}: {e}", "ERROR")
            if dest.exists():
                dest.unlink(missing_ok=True)
            return False

    def _save_txt(self, post, img_path):
        txt = img_path.with_suffix(".txt")
        if txt.exists():
            return
        ordered_keys = [
            ("meta", "tag_string_meta"),
            ("artist", "tag_string_artist"),
            ("copyright", "tag_string_copyright"),
            ("general", "tag_string_general"),
        ]
        selected = set(self.tag_categories)
        tags = []
        for category, tag_key in ordered_keys:
            if category in selected:
                for tag in post.get(tag_key, "").split():
                    if self.replace_tag_underscores:
                        tag = format_saved_tag(tag)
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

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.title("Danbooru Downloader")
        self.geometry("960x600")
        self.minsize(900, 560)
        self.configure(fg_color=self.BG)

        self.dl_thread = None
        self.downloader = None
        self.log_q = queue.Queue()

        self._build_ui()
        self._load_cfg()
        self.after(100, self._poll_log)

    # ── UI 빌드 ──

    def _build_ui(self):
        # 헤더
        hdr = ctk.CTkFrame(self, height=60, fg_color=self.CARD, corner_radius=10, border_width=1, border_color=self.BORDER)
        hdr.pack(fill="x", padx=12, pady=(12, 8))
        ctk.CTkLabel(hdr, text="DANBOORU DOWNLOADER", font=("Segoe UI", 20, "bold"), text_color="#fff").pack(side="left", padx=16, pady=10)

        # 본문 2단
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=4)
        left = ctk.CTkFrame(body, fg_color=self.CARD, corner_radius=10, border_width=1, border_color=self.BORDER)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        right = ctk.CTkFrame(body, fg_color=self.CARD, corner_radius=10, border_width=1, border_color=self.BORDER)
        right.pack(side="right", fill="both", expand=True, padx=(6, 0))

        self._build_left(left)
        self._build_right(right)

        # 하단 콘솔
        bot = ctk.CTkFrame(self, fg_color=self.CARD, corner_radius=10, border_width=1, border_color=self.BORDER)
        bot.pack(fill="both", expand=True, padx=12, pady=(8, 12))

        self.status = ctk.CTkLabel(bot, text="대기 중", font=("Segoe UI", 11, "bold"), text_color=self.DIM)
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
        ctk.CTkLabel(f, text="🔍 검색 설정", font=("Segoe UI", 14, "bold"), text_color="#fff").pack(anchor="w", padx=12, pady=(12, 8))

        self._label(f, "포함 태그:").pack(anchor="w", padx=12)
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 8))
        self.e_tags = self._entry(row, "1girl solo long_hair")
        self.e_tags.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(row, text="개수 조회", width=70, height=30,
                       fg_color=self.BORDER, hover_color="#3e415b", text_color="#fff",
                       font=("Segoe UI", 11, "bold"), command=self._count).pack(side="right")

        self._label(f, "2차 필터:").pack(anchor="w", padx=12)
        self.e_exc = self._entry(f, "-comic -chibi cat_ears|dog_ears")
        self.e_exc.pack(fill="x", padx=12, pady=(0, 8))

        self._label(f, "레이팅:").pack(anchor="w", padx=12)
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
        self._label(col1, "다운로드 수:").pack(anchor="w")
        self.e_limit = self._entry(col1)
        self.e_limit.pack(fill="x")

        col2 = ctk.CTkFrame(row2, fg_color="transparent")
        col2.pack(side="left", fill="x", expand=True, padx=(4, 4))
        self._label(col2, "지연 시간(초):").pack(anchor="w")
        self.e_delay = self._entry(col2, "0.5")
        self.e_delay.pack(fill="x")

        col3 = ctk.CTkFrame(row2, fg_color="transparent")
        col3.pack(side="right", fill="x", expand=True, padx=(4, 0))
        self._label(col3, "파일명 규칙:").pack(anchor="w")
        self.m_naming = ctk.CTkOptionMenu(col3, values=["ID만", "태그+ID", "원본 이름"],
                                           fg_color=self.INPUT, button_color=self.BORDER,
                                           button_hover_color="#3e415b",
                                           dropdown_fg_color=self.CARD,
                                           dropdown_hover_color="#3e415b",
                                           dropdown_text_color=self.TEXT, height=30)
        self.m_naming.pack(fill="x")

    def _build_right(self, f):
        ctk.CTkLabel(f, text="💾 저장 설정", font=("Segoe UI", 14, "bold"), text_color="#fff").pack(anchor="w", padx=12, pady=(12, 8))

        self._label(f, "저장 경로:").pack(anchor="w", padx=12)
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 8))
        self.e_path = self._entry(row)
        self.e_path.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(row, text="선택", width=60, height=30,
                       fg_color=self.BORDER, hover_color="#3e415b", text_color="#fff",
                       command=self._browse_dir).pack(side="right")

        self._label(f, "Danbooru 계정 (선택):").pack(anchor="w", padx=12)
        auth = ctk.CTkFrame(f, fg_color="transparent")
        auth.pack(fill="x", padx=12, pady=(0, 8))
        self.e_user = self._entry(auth, "Username")
        self.e_user.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.e_key = self._entry(auth, "API Key")
        self.e_key.configure(show="*")
        self.e_key.pack(side="right", fill="x", expand=True, padx=(4, 0))

        self.v_txt = ctk.StringVar(value="on")
        self.cb_txt = ctk.CTkCheckBox(f, text="태그 .txt 파일 동시 저장 (Lora 학습용)",
                                      variable=self.v_txt, onvalue="on", offvalue="off",
                                      text_color=self.PURPLE, font=("Segoe UI", 11, "bold"),
                                      border_color=self.BORDER)
        self.cb_txt.pack(anchor="w", padx=12, pady=(0, 6))

        self.v_replace_underscores = ctk.StringVar(value="on")
        self.cb_replace_underscores = ctk.CTkCheckBox(f, text="태그 저장 시 _ 를 공백으로 변환",
                                                      variable=self.v_replace_underscores,
                                                      onvalue="on", offvalue="off",
                                                      text_color="#cbd5e1", font=("Segoe UI", 11, "bold"),
                                                      border_color=self.BORDER)
        self.cb_replace_underscores.pack(anchor="w", padx=12, pady=(0, 6))

        self._label(f, "저장할 태그 항목:").pack(anchor="w", padx=12)
        cat_row = ctk.CTkFrame(f, fg_color="transparent")
        cat_row.pack(fill="x", padx=12, pady=(0, 12))
        self.tag_cat_vars = {}
        self.tag_cat_checks = []
        for key, label in [("meta", "Meta"), ("artist", "Artist"), ("copyright", "Copyright"), ("general", "General")]:
            v = ctk.StringVar(value="off")
            self.tag_cat_vars[key] = v
            cb = ctk.CTkCheckBox(cat_row, text=label, variable=v, onvalue="on", offvalue="off",
                                 text_color="#cbd5e1", font=("Segoe UI", 10),
                                 border_color=self.BORDER)
            cb.pack(side="left", expand=True)
            self.tag_cat_checks.append(cb)

        btns = ctk.CTkFrame(f, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 12))
        self.b_start = ctk.CTkButton(btns, text="⚡ 다운로드", font=("Segoe UI", 13, "bold"),
                                      fg_color=self.PURPLE, hover_color="#9333ea",
                                      text_color="#fff", height=36, command=self._start)
        self.b_start.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.b_stop = ctk.CTkButton(btns, text="중지", font=("Segoe UI", 13, "bold"),
                                     fg_color="#374151", hover_color=self.RED,
                                     text_color="#fff", height=36, state="disabled",
                                     command=self._stop)
        self.b_stop.pack(side="right", fill="x", expand=True, padx=(4, 0))

    # ── 설정 로드/저장 ──

    def _load_cfg(self):
        c = self.cfg
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
        selected_categories = set(c.get("tag_categories", ["general"]))
        for key, v in self.tag_cat_vars.items():
            v.set("on" if key in selected_categories else "off")
        naming_map = {"id": "ID만", "tags_id": "태그+ID", "original": "원본 이름"}
        self.m_naming.set(naming_map.get(c["naming"], "ID만"))

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
            "tag_categories": self._selected_tag_categories(),
            "naming": "tags_id" if "태그" in self.m_naming.get() else ("original" if "원본" in self.m_naming.get() else "id"),
        })
        save_config(self.cfg)

    def _selected_tag_categories(self):
        return [key for key in ("meta", "artist", "copyright", "general")
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
            messagebox.showerror("오류", "태그를 입력하세요.")
            return
        threading.Thread(target=self._count_thread, args=(tags,), daemon=True).start()

    def _count_thread(self, tags):
        self._log(f"'{tags}' 개수 조회 중...")
        try:
            api = DanbooruAPI(self.e_user.get().strip(), self.e_key.get().strip())
            n = api.count_posts(tags)
            self._log(f"결과: {n:,}개", "SUCCESS")
            self.after(0, lambda: messagebox.showinfo("조회 결과", f"{tags}\n\n{n:,}개"))
        except Exception as e:
            self._log(f"조회 실패: {e}", "ERROR")

    # ── 다운로드 ──

    def _start(self):
        if self.dl_thread and self.dl_thread.is_alive():
            return
        path = self.e_path.get().strip()
        if not path:
            messagebox.showerror("오류", "저장 경로를 지정하세요.")
            return
        try:
            limit = int(self.e_limit.get().strip() or "100")
            assert limit > 0
        except (ValueError, AssertionError):
            messagebox.showerror("오류", "다운로드 수는 1 이상 정수여야 합니다.")
            return
        try:
            delay = float(self.e_delay.get().strip() or "0.5")
            assert delay >= 0
        except (ValueError, AssertionError):
            messagebox.showerror("오류", "지연 시간은 0 이상의 숫자여야 합니다.")
            return
        ratings = [c for c in "gsqe" if self.rv[c].get() == "on"]
        if not ratings:
            messagebox.showerror("오류", "레이팅을 하나 이상 선택하세요.")
            return
        if self.v_txt.get() == "on" and not self._selected_tag_categories():
            messagebox.showerror("오류", "저장할 태그 항목을 하나 이상 선택하세요.")
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
            naming="tags_id" if "태그" in self.m_naming.get() else ("original" if "원본" in self.m_naming.get() else "id"),
            save_txt=self.v_txt.get() == "on",
            replace_tag_underscores=self.v_replace_underscores.get() == "on",
            tag_categories=self._selected_tag_categories(),
            delay=delay,
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
            messagebox.showinfo("완료", msg)
        else:
            messagebox.showwarning("종료", msg)
        self.downloader = None

    def _set_running(self, on):
        s = "disabled" if on else "normal"
        for w in (self.e_tags, self.e_exc, self.e_limit, self.e_delay, self.e_path,
                  self.e_user, self.e_key, self.m_naming, self.cb_txt,
                  self.cb_replace_underscores, *self.tag_cat_checks):
            w.configure(state=s)
        self.b_start.configure(state=s, text="다운로드 중..." if on else "⚡ 다운로드")
        self.b_stop.configure(state="normal" if on else "disabled")
        if on:
            self.pbar.set(0)
            self.status.configure(text="다운로드 중...")

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.e_path.get())
        if d:
            self.e_path.delete(0, "end")
            self.e_path.insert(0, d)


if __name__ == "__main__":
    App().mainloop()
