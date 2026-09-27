"""UEyes (Jiang et al., CHI 2023): human eye tracking on 1,980 UI screenshots, CC BY 4.0.

The dataset ships as one 12.9 GB zip. Only the index, the screenshots, and one duration's
fixation and heat maps are needed to score a model, about 1 GB for everything and 60 MB
for the test split, so members are read straight out of the remote zip with HTTP range
requests instead of downloading the archive.
"""

import csv
import http.client
import io
import struct
import sys
import time
import urllib.error
import urllib.request
import zipfile
import zlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

UEYES_URL = "https://zenodo.org/api/records/8010312/files/UEyes_dataset.zip/content"
ROOT = "UEyes_dataset/"
CATEGORIES = ("web", "desktop", "mobile", "poster")
RETRIES = 6
# Zenodo publishes X-RateLimit-Limit: 133 per minute; stay comfortably under it across all threads.
MIN_INTERVAL = 0.5
_throttle_lock = threading.Lock()
_last_request = [0.0]


def _throttle() -> None:
    """Space requests at least MIN_INTERVAL apart, process-wide."""
    with _throttle_lock:
        wait = _last_request[0] + MIN_INTERVAL - time.monotonic()
        if wait > 0 and _last_request[0] > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()
RETRY_DELAY = 2.0  # seconds, doubled after each failed attempt


@dataclass
class Sample:
    name: str
    category: str
    image: Path
    fixmap: Path
    heatmap: Path


class HTTPRangeFile(io.RawIOBase):
    """Read-only, seekable view of a remote file over HTTP range requests."""

    def __init__(self, url: str):
        self.url, self.pos = url, 0
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as resp:
            self.size = int(resp.headers["Content-Length"])

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def readinto(self, buffer):
        n = min(len(buffer), self.size - self.pos)
        if n <= 0:
            return 0
        data = fetch_range(self.url, self.pos, self.pos + n - 1)
        buffer[: len(data)] = data
        self.pos += len(data)
        return len(data)


UNSCORED = "unscored.txt"  # images the archive has no human maps for


def fetch_range(url: str, start: int, end: int) -> bytes:
    """Bytes ``start``..``end`` inclusive, retried with backoff on dropped responses."""
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
    for attempt in range(RETRIES):
        _throttle()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            # rate limits and overload are worth waiting for; anything else is a real error
            if exc.code not in (429, 503) or attempt == RETRIES - 1:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            delay = float(retry_after) if retry_after and retry_after.isdigit() else RETRY_DELAY * 4 * 2**attempt
            time.sleep(delay)
        except (http.client.IncompleteRead, urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt == RETRIES - 1:
                raise
            time.sleep(RETRY_DELAY * 2**attempt)
    raise AssertionError("unreachable")


LOCAL_HEADER = struct.Struct("<4sHHHHHIIIHH")
HEADER_SLACK = 1024  # the local extra field may be longer than the central one


def fetch_member(url: str, info: zipfile.ZipInfo) -> bytes:
    """One member's decompressed bytes, from a single range request for header and data."""
    start = info.header_offset
    end = start + LOCAL_HEADER.size + len(info.filename.encode()) + HEADER_SLACK + info.compress_size
    blob = fetch_range(url, start, end)
    fields = LOCAL_HEADER.unpack_from(blob)
    if fields[0] != b"PK\x03\x04":
        raise ValueError(f"bad local header for {info.filename}")
    data_start = LOCAL_HEADER.size + fields[9] + fields[10]
    if data_start + info.compress_size > len(blob):
        blob += fetch_range(url, start + len(blob), start + data_start + info.compress_size - 1)
    raw = blob[data_start : data_start + info.compress_size]
    if info.compress_type == zipfile.ZIP_STORED:
        data = raw
    elif info.compress_type == zipfile.ZIP_DEFLATED:
        data = zlib.decompress(raw, -15)
    else:
        raise ValueError(f"unsupported compression {info.compress_type} for {info.filename}")
    if zlib.crc32(data) != info.CRC:
        raise ValueError(f"checksum mismatch for {info.filename}")
    return data


def _map_name(image_name: str) -> str:
    """UEyes names each map after its image, extension included."""
    return image_name


def _read_index(text: str) -> list[tuple[str, str, str]]:
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))[1:]
    return [(r[0], r[1], r[3].strip().lower()) for r in rows if len(r) >= 4]


def download_ueyes(
    dest: str | Path,
    split: str = "test",
    duration: int = 3,
    url: str = UEYES_URL,
    kinds: tuple[str, ...] = ("images", "fixmaps", "heatmaps"),
    workers: int = 4,
) -> int:
    """Fetch the index and the requested file kinds for one split and duration. Returns files fetched."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    # probe first: zipfile would turn an HTTP error on its first read into "not a zip file"
    if fetch_range(url, 0, 3) != b"PK\x03\x04":
        raise ValueError(f"{url} is not a zip archive")
    remote = zipfile.ZipFile(io.BufferedReader(HTTPRangeFile(url), buffer_size=1 << 20))
    fetched = 0

    index_path = dest / "image_types.csv"
    if not index_path.exists():
        index_path.write_bytes(remote.read(ROOT + "image_types.csv"))
        fetched += 1
    rows = [r for r in _read_index(index_path.read_text()) if split == "all" or r[2] == split]

    available = set(remote.namelist())
    wanted, unscored = [], []
    for name, _, _ in rows:
        maps = [
            (f"{ROOT}saliency_maps/{kind}_{duration}s/{_map_name(name)}", dest / f"{kind}_{duration}s" / _map_name(name))
            for kind in ("fixmaps", "heatmaps")
        ]
        if not all(member in available for member, _ in maps):
            unscored.append(name)
            continue
        candidates = [(f"{ROOT}images/{name}", dest / "images" / name), *maps]
        wanted += [(m, p) for m, p in candidates if p.parent.name.split("_")[0] in kinds]
    unscored_path = dest / UNSCORED
    known = set(unscored_path.read_text().split()) if unscored_path.exists() else set()
    unscored_path.write_text("\n".join(sorted(known | set(unscored))) + "\n")
    missing = [(m, p) for m, p in wanted if not p.exists()]

    def save(member: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(path.suffix + ".part")
        partial.write_bytes(fetch_member(url, remote.getinfo(member)))
        partial.replace(path)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(save, member, path) for member, path in missing]
        for i, future in enumerate(as_completed(futures), start=1):
            future.result()
            fetched += 1
            if i % 50 == 0 or i == len(missing):
                print(f"\r  UEyes: {i}/{len(missing)} files", end="", file=sys.stderr)
    if missing:
        print(file=sys.stderr)
    return fetched


def load_ueyes(root: str | Path, split: str = "test", duration: int = 3) -> list[Sample]:
    root = Path(root)
    index_path = root / "image_types.csv"
    if not index_path.exists():
        raise FileNotFoundError(f"no UEyes data in {root}; run `gazemap benchmark --download` first")
    unscored_path = root / UNSCORED
    unscored = set(unscored_path.read_text().split()) if unscored_path.exists() else set()
    samples = []
    for name, category, row_split in _read_index(index_path.read_text()):
        if (split != "all" and row_split != split) or name in unscored:
            continue
        sample = Sample(
            name=name,
            category=category,
            image=root / "images" / name,
            fixmap=root / f"fixmaps_{duration}s" / _map_name(name),
            heatmap=root / f"heatmaps_{duration}s" / _map_name(name),
        )
        if not (sample.image.exists() and sample.fixmap.exists() and sample.heatmap.exists()):
            raise FileNotFoundError(f"{name} is incomplete in {root}; run `gazemap benchmark --download` for this split")
        samples.append(sample)
    return samples
