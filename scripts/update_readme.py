import os
import re
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import quote  # 공백/특수문자 URL 인코딩

# ===== 설정 =====
DATE_DIR_RE = re.compile(r"^25\d{4}$")  # 예: 250821
EXT_ALLOW = {".md", ".pdf", ".pptx", ".ppt", ".pptm"}

AUTO_BEGIN = "<!--AUTO-SECTION:BEGIN-->"
AUTO_END   = "<!--AUTO-SECTION:END-->"
README_PATH = Path("README.md")

REPO_URL = os.environ.get("REPO_URL", "").rstrip("/")
BRANCH_NAME = os.environ.get("BRANCH_NAME", "main")

# ===== 유틸 =====
def sh(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()

def find_uploader_for_file(path: Path) -> str:
    """
    파일 최초 추가 커밋의 Author를 우선 사용, 없으면 최신 커밋 Author.
    공백 포함 파일명도 안전(인자 리스트로 전달).
    """
    p = path.as_posix()
    # 최초 추가 작성자
    try:
        first_authors = sh(["git", "log", "--diff-filter=A", "--follow", "--format=%an", "--", p]).splitlines()
        if first_authors:
            return first_authors[-1]
    except subprocess.CalledProcessError:
        pass
    # 최신 작성자
    try:
        last_author = sh(["git", "log", "-1", "--pretty=%an", "--", p])
        if last_author:
            return last_author
    except subprocess.CalledProcessError:
        pass
    return ""

def pretty_title_from_filename(fname: str) -> str:
    """
    파일명에서 확장자 제거 후 _/-를 공백으로 바꿔 가독성 있는 제목.
    (공백 포함 파일명도 그대로 유지)
    """
    stem = Path(fname).stem
    title = re.sub(r"[_\-]+", " ", stem).strip()
    return title[:1].upper() + title[1:] if title else stem

def url_for_blob(rel_path: str) -> str:
    """
    GitHub 웹 링크 생성 시 공백/특수문자 인코딩.
    - 각 경로 세그먼트를 개별 인코딩해 슬래시는 유지.
    """
    parts = rel_path.split("/")
    encoded = "/".join(quote(p) for p in parts)
    if REPO_URL:
        return f"{REPO_URL}/blob/{quote(BRANCH_NAME)}/{encoded}"
    return rel_path

def collect_rows(repo_root: Path) -> list[tuple[str, str, str, str, str]]:
    """
    반환: (폴더날짜, 업로더, 논문명, 상대경로, 웹링크)
    - 루트에서 ^25\\d{4}$ 폴더만 스캔
    - 허용 확장자만 수집
    """
    rows = []
    date_dirs = [p for p in repo_root.iterdir() if p.is_dir() and DATE_DIR_RE.match(p.name)]
    for d in sorted(date_dirs, reverse=True):
        for f in sorted(d.rglob("*")):
            if not f.is_file():
                continue
            if f.suffix.lower() not in EXT_ALLOW:
                continue
            uploader = find_uploader_for_file(f)
            paper = pretty_title_from_filename(f.name)
            rel = f.as_posix()  # 공백 포함 가능
            url = url_for_blob(rel)
            rows.append((d.name, uploader, paper, rel, url))
    return rows

def render_table(rows: list[tuple[str, str, str, str, str]]) -> str:
    """마크다운 표 렌더링 (공백/파이프 안전화)."""
    if not rows:
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst).strftime("%Y-%m-%d %H:%M KST")
        return (
            "## 📚 스터디 업로드 목록\n\n"
            f"- 현재 기준 자동으로 수집된 항목이 없습니다. (시각: **{now}**)\n"
        )

    header = [
        "## 📚 스터디 업로드 목록\n",
        "| 폴더날짜 | 업로드한 사람 | 논문 이름 | 파일 | 링크 |",
        "|---|---|---|---|---|",
    ]
    lines = []
    for date_dir, uploader, paper, rel, url in rows:
        paper_md = paper.replace("|", "\\|")
        uploader_md = (uploader or "").replace("|", "\\|")
        rel_md = rel.replace("|", "\\|")
        # 파일 경로는 백틱으로 감싸 공백 표시도 깨지지 않게
        lines.append(f"| `{date_dir}` | {uploader_md} | {paper_md} | `{rel_md}` | [열기]({url}) |")
    return "\n".join(header + lines) + "\n"

def replace_section(orig_md: str, body_md: str) -> str:
    """AUTO 섹션만 치환. 마커가 없으면 맨 위에 추가."""
    pattern = re.compile(re.escape(AUTO_BEGIN) + r"(.*?)" + re.escape(AUTO_END), re.DOTALL)
    if pattern.search(orig_md):
        return pattern.sub(f"{AUTO_BEGIN}\n{body_md}\n{AUTO_END}", orig_md)
    else:
        return f"{AUTO_BEGIN}\n{body_md}\n{AUTO_END}\n\n{orig_md}"

def main():
    rows = collect_rows(Path("."))
    body = render_table(rows)

    if not README_PATH.exists():
        README_PATH.write_text(f"{AUTO_BEGIN}\n{body}\n{AUTO_END}\n", encoding="utf-8")
        return

    old = README_PATH.read_text(encoding="utf-8")
    new = replace_section(old, body)
    if new != old:
        README_PATH.write_text(new, encoding="utf-8")

if __name__ == "__main__":
    main()
