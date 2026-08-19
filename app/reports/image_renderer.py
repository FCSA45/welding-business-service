import subprocess
import shutil
from pathlib import Path
from urllib.parse import quote

from app.errors import AppError
from app.reports.browser_fullpage import render_full_page


class HtmlToPngRenderer:
    """Render trusted, locally generated HTML to PNG via an isolated browser process."""

    def __init__(self, *, command: str, script_path: str | Path, timeout_seconds: int = 30) -> None:
        self.command = command
        self.script_path = Path(script_path).resolve()
        self.timeout_seconds = timeout_seconds

    def render(self, html: str, output_path: str | Path, *, width: int = 1200) -> tuple[Path, Path]:
        if not html.strip():
            raise AppError("REPORT_HTML_EMPTY", "报表内容为空，不能生成图片", status_code=422)
        if not 800 <= width <= 2400:
            raise AppError("REPORT_IMAGE_WIDTH_INVALID", "报表图片宽度超出允许范围", status_code=422)
        png_path = Path(output_path).resolve()
        png_path.parent.mkdir(parents=True, exist_ok=True)
        html_path = png_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")
        if not self.script_path.is_file():
            fallback_error = self._render_with_installed_browser(html_path, png_path, width)
            if png_path.is_file() and png_path.stat().st_size > 0:
                return html_path, png_path
            raise AppError(
                "REPORT_RENDERER_NOT_FOUND",
                "报表图片渲染程序不存在，且未找到可用的本地浏览器",
                status_code=503,
                details={"browser_fallback_error": fallback_error[-500:]},
            )
        try:
            result = subprocess.run(
                [self.command, str(self.script_path), str(html_path), str(png_path), str(width)],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AppError("REPORT_RENDER_FAILED", "报表图片生成失败", status_code=503) from exc
        if result.returncode != 0 or not png_path.is_file() or png_path.stat().st_size == 0:
            fallback_error = self._render_with_installed_browser(html_path, png_path, width)
            if png_path.is_file() and png_path.stat().st_size > 0:
                return html_path, png_path
            raise AppError(
                "REPORT_RENDER_FAILED",
                "报表图片生成失败",
                status_code=503,
                details={
                    "renderer_error": result.stderr[-500:],
                    "browser_fallback_error": fallback_error[-500:],
                },
            )
        return html_path, png_path

    @staticmethod
    def _render_with_installed_browser(html_path: Path, png_path: Path, width: int) -> str:
        candidates = (
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            *(Path(found) for name in (
                "chromium", "chromium-browser", "google-chrome", "google-chrome-stable"
            ) if (found := shutil.which(name))),
        )
        browser = next((path for path in candidates if path.is_file()), None)
        if browser is None:
            return "no supported local browser found"
        success, detail = render_full_page(browser, html_path, png_path, width)
        if success:
            return detail
        # Last-resort viewport capture for environments where DevTools is disabled.
        file_url = "file:///" + quote(html_path.as_posix(), safe="/:()")
        try:
            fallback = subprocess.run(
                [
                    str(browser), "--headless=new", "--disable-gpu", "--no-sandbox",
                    f"--window-size={width},2400", f"--screenshot={png_path}", file_url,
                ],
                check=False, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"{detail}; {type(exc).__name__}"
        return f"{detail}; {fallback.stderr}"
