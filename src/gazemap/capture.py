"""Above-the-fold page capture and DOM lookup with Playwright."""

import io
from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


@dataclass(frozen=True)
class Viewport:
    name: str
    width: int
    height: int
    is_mobile: bool


VIEWPORTS = {
    "desktop": Viewport("desktop", 1440, 900, is_mobile=False),
    "mobile": Viewport("mobile", 390, 844, is_mobile=True),
}

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


class CaptureError(Exception):
    """Navigation or capture failed in a way the user needs to act on."""


@dataclass
class ElementInfo:
    tag: str
    selector: str
    text: str


@dataclass
class Window:
    scroll_y: int  # page offset of this screen
    image: np.ndarray  # viewport-sized crop, height x width x 3


@dataclass
class Capture:
    url: str
    final_url: str
    status: int | None
    viewport: Viewport
    image: np.ndarray  # captured page, height x width x 3, uint8 RGB
    page_height: int  # full document height, even when only the first screen was captured
    windows: list[Window]
    warnings: list[str] = field(default_factory=list)


PAGE_HEIGHT_JS = "Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)"

ELEMENT_AT_JS = """
([x, y, viewportHeight]) => {
  // points in the first screen are looked up as is, so fixed elements resolve;
  // deeper points are scrolled to the middle of the viewport first
  window.scrollTo(0, y < viewportHeight ? 0 : Math.max(0, y - Math.floor(viewportHeight / 2)));
  const el = document.elementFromPoint(x, y - window.scrollY);
  if (!el) return null;
  const part = (e) => {
    if (e.id) return '#' + CSS.escape(e.id);
    let s = e.tagName.toLowerCase();
    const cls = [...e.classList].slice(0, 2).map((c) => '.' + CSS.escape(c)).join('');
    if (cls) return s + cls;
    const parent = e.parentElement;
    if (parent) {
      const same = [...parent.children].filter((c) => c.tagName === e.tagName);
      if (same.length > 1) s += `:nth-of-type(${same.indexOf(e) + 1})`;
    }
    return s;
  };
  const parts = [];
  let cur = el;
  while (cur && cur.tagName !== 'HTML' && parts.length < 3) {
    parts.unshift(part(cur));
    if (cur.id) break;
    cur = cur.parentElement;
  }
  const raw = el.innerText || el.getAttribute('alt') || el.getAttribute('aria-label') || el.getAttribute('title') || '';
  const text = raw.replace(/\\s+/g, ' ').trim().slice(0, 80);
  return { tag: el.tagName.toLowerCase(), selector: parts.join(' > '), text };
}
"""


class PageSession:
    """Open a page, capture the viewport, and keep it open for DOM queries."""

    def __init__(
        self,
        url: str,
        viewport: Viewport,
        wait_ms: int = 0,
        hide: list[str] | tuple[str, ...] = (),
        timeout_ms: int = 30000,
        full_page: bool = False,
        max_screens: int = 20,
    ):
        self.url = url
        self.viewport = viewport
        self.wait_ms = wait_ms
        self.hide = list(hide)
        self.timeout_ms = timeout_ms
        self.full_page = full_page
        self.max_screens = max_screens
        self.capture: Capture | None = None
        self._playwright = None
        self._browser = None
        self._page = None

    def __enter__(self) -> "PageSession":
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=True)
            self._page = self._open_page()
            self.capture = self._capture()
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._page = None

    def _open_page(self):
        vp = self.viewport
        major = self._browser.version.split(".")[0]
        context_args = {
            "viewport": {"width": vp.width, "height": vp.height},
            "device_scale_factor": 1,
            "is_mobile": vp.is_mobile,
            "has_touch": vp.is_mobile,
            "user_agent": MOBILE_USER_AGENT
            if vp.is_mobile
            else (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
            ),
        }
        context = self._browser.new_context(**context_args)
        page = context.new_page()
        page.set_default_timeout(self.timeout_ms)
        try:
            response = page.goto(self.url, wait_until="load", timeout=self.timeout_ms)
        except PlaywrightTimeoutError as exc:
            raise CaptureError(
                f"{self.url} did not finish loading within {self.timeout_ms} ms "
                "(check the URL, or raise the timeout)"
            ) from exc
        except PlaywrightError as exc:
            raise CaptureError(_explain_navigation_error(self.url, str(exc))) from exc
        self._response = response
        try:
            page.wait_for_load_state("networkidle", timeout=min(10000, self.timeout_ms))
        except PlaywrightTimeoutError:
            pass
        if self.wait_ms:
            page.wait_for_timeout(self.wait_ms)
        for selector in self.hide:
            page.add_style_tag(content=f"{selector} {{ display: none !important; }}")
        if self.hide:
            page.wait_for_timeout(100)
        return page

    def _capture(self) -> Capture:
        page = self._page
        status = self._response.status if self._response is not None else None
        warnings = []
        if status is not None and status >= 400:
            warnings.append(f"server returned HTTP {status}; the page may block headless browsers")
        title = page.title()
        if "just a moment" in title.lower() or "access denied" in title.lower():
            warnings.append(f'page title is "{title}", which looks like a bot challenge')

        vh = self.viewport.height
        page_height = int(page.evaluate(PAGE_HEIGHT_JS))
        if self.full_page:
            page_height = self._scroll_through(page_height)
            captured_height = max(vh, min(page_height, self.max_screens * vh))
            if captured_height < page_height:
                warnings.append(
                    f"page is {page_height} px tall; captured the first {self.max_screens} screens "
                    f"({captured_height} px), raise --max-screens to capture more"
                )
            png = page.screenshot(type="png", full_page=True, animations="disabled", caret="hide")
        else:
            captured_height = vh
            png = page.screenshot(type="png", animations="disabled", caret="hide")
        image = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
        image = _fit_height(image, captured_height)

        offsets = list(range(0, captured_height - vh + 1, vh))
        if offsets[-1] + vh < captured_height:
            offsets.append(captured_height - vh)
        windows = [Window(scroll_y=top, image=image[top : top + vh]) for top in offsets]
        return Capture(
            url=self.url,
            final_url=page.url,
            status=status,
            viewport=self.viewport,
            image=image,
            page_height=page_height,
            windows=windows,
            warnings=warnings,
        )

    def _scroll_through(self, page_height: int) -> int:
        """Scroll the whole page once so lazy content loads, then return to the top."""
        page = self._page
        vh = self.viewport.height
        for top in range(0, page_height, vh):
            page.evaluate("y => window.scrollTo(0, y)", top)
            page.wait_for_timeout(100)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(250)
        return int(page.evaluate(PAGE_HEIGHT_JS))

    def locate(self, selector: str) -> tuple[int, int, int, int] | None:
        """Page-coordinate box (x, y, width, height) of the first match of a Playwright selector."""
        if self._page is None:
            raise RuntimeError("page session is closed")
        page = self._page
        page.evaluate("window.scrollTo(0, 0)")
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                return None
            box = locator.bounding_box(timeout=2000)
        except PlaywrightError:
            return None
        if box is None:
            return None
        scroll_y = page.evaluate("window.scrollY")
        return (round(box["x"]), round(box["y"] + scroll_y), round(box["width"]), round(box["height"]))

    def element_at(self, x: int, y: int) -> ElementInfo | None:
        """Topmost DOM element under a viewport pixel, or None outside the document."""
        if self._page is None:
            raise RuntimeError("page session is closed")
        result = self._page.evaluate(ELEMENT_AT_JS, [int(x), int(y), self.viewport.height])
        if result is None:
            return None
        return ElementInfo(tag=result["tag"], selector=result["selector"], text=result["text"])


def _fit_height(image: np.ndarray, height: int) -> np.ndarray:
    """Crop or white-pad an image to exactly ``height`` rows."""
    if image.shape[0] >= height:
        return image[:height]
    pad = np.full((height - image.shape[0], image.shape[1], 3), 255, dtype=np.uint8)
    return np.concatenate([image, pad], axis=0)


def _explain_navigation_error(url: str, message: str) -> str:
    if "ERR_NAME_NOT_RESOLVED" in message:
        return f"could not resolve the host of {url}"
    if "ERR_CONNECTION_REFUSED" in message:
        return f"connection refused by {url} (is the server running?)"
    if "ERR_INTERNET_DISCONNECTED" in message or "ERR_NETWORK_CHANGED" in message:
        return f"no network connection while loading {url}"
    if "ERR_CERT" in message or "SSL" in message:
        return f"TLS certificate problem loading {url}"
    first_line = message.strip().splitlines()[0]
    return f"navigation to {url} failed: {first_line}"
