"""Download and verify the offline Baige card database."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image


API_BASE = "https://ygocdb.com/api/v0"
IMAGE_SOURCES = (
    ("webp", "https://cdn.233.momobako.com/ygopro/pics/{card_id}.jpg!art", False),
    (
        "jpg",
        "https://images.ygoprodeck.com/images/cards_cropped/{card_id}.jpg",
        False,
    ),
    (
        "jpg",
        "https://cdntx.moecube.com/ygopro-super-pre/data/pics/{card_id}.jpg",
        True,
    ),
)
IMAGE_SUFFIXES = tuple(dict.fromkeys(suffix for suffix, _, _ in IMAGE_SOURCES))
USER_AGENT = "YuGiOhCardMaker-OfflineLibrary/1.0"


def request(url: str, timeout: int = 60):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": USER_AGENT}),
        timeout=timeout,
    )


def download(url: str, target: Path, timeout: int = 180) -> None:
    temp_target = target.with_suffix(target.suffix + ".tmp")
    with request(url, timeout=timeout) as response, temp_target.open("wb") as output:
        shutil.copyfileobj(response, output)
    os.replace(temp_target, target)


def valid_image(path: Path, verify: bool = False) -> bool:
    try:
        with path.open("rb") as image_file:
            header = image_file.read(16)
    except OSError:
        return False
    valid_header = (
        header.startswith(b"\xff\xd8\xff")
        or header.startswith(b"\x89PNG\r\n\x1a\n")
        or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
    )
    if not valid_header or not verify:
        return valid_header
    try:
        with Image.open(path) as image:
            image.verify()
        return True
    except (OSError, ValueError):
        return False


def load_json_object(path: Path, default: dict | None = None) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else dict(default)
    return data if isinstance(data, dict) else ({} if default is None else dict(default))


def crop_full_card_art(path: Path) -> None:
    with Image.open(path) as source:
        width, height = source.size
        art = source.crop(
            (
                round(width * 0.105),
                round(height * 0.176),
                round(width * 0.895),
                round(height * 0.710),
            )
        )
        art.convert("RGB").save(path, format="JPEG", quality=95)


def file_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_card_ids(cards: dict) -> set[int]:
    return {
        card_id
        for card in cards.values()
        if isinstance(card_id := card.get("id"), int) and card_id > 0
    }


def update_database(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / "cards.zip"
    cards_path = output_dir / "cards.json"

    with request(f"{API_BASE}/cards.zip.md5") as response:
        expected_md5 = json.loads(response.read().decode("utf-8"))

    if cards_path.exists() and file_md5(cards_path) == expected_md5:
        print(f"本地卡库已经是最新版：{cards_path}")
    else:
        print("正在从百鸽 API 下载全部卡片资料……")
        download(f"{API_BASE}/cards.zip", zip_path)
        with zipfile.ZipFile(zip_path) as archive:
            cards_data = archive.read("cards.json")
        actual_md5 = hashlib.md5(cards_data).hexdigest()
        if actual_md5 != expected_md5:
            raise RuntimeError(
                f"卡库校验失败：期望 {expected_md5}，实际 {actual_md5}"
            )
        temp_cards = cards_path.with_suffix(".json.tmp")
        temp_cards.write_bytes(cards_data)
        os.replace(temp_cards, cards_path)

    with cards_path.open("r", encoding="utf-8") as source:
        cards = json.load(source)
    print(f"卡片资料数量：{len(cards)}")
    return cards


def write_json_atomic(path: Path, data: dict) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def load_pack_index(path: Path) -> dict:
    packs = load_json_object(path)
    return {
        str(card_id): pack
        for card_id, pack in packs.items()
        if pack is None or (isinstance(pack, str) and pack)
    }


def scan_cached_image_ids(
    image_dir: Path,
    expected_ids: set[int],
    verify: bool = False,
) -> set[int]:
    cached_ids = set()
    if not image_dir.exists():
        return cached_ids
    for image_path in image_dir.iterdir():
        if image_path.suffix.lower().lstrip(".") not in IMAGE_SUFFIXES:
            continue
        try:
            card_id = int(image_path.stem)
        except ValueError:
            continue
        if card_id in expected_ids and valid_image(image_path, verify=verify):
            cached_ids.add(card_id)
    return cached_ids


def update_card_packs(cards: dict, output_dir: Path, workers: int, retries: int) -> dict:
    packs_path = output_dir / "card_packs.json"
    failed_path = output_dir / "卡包信息下载失败.txt"
    packs = load_pack_index(packs_path)

    card_ids = sorted(valid_card_ids(cards))
    pending_ids = [card_id for card_id in card_ids if str(card_id) not in packs]
    print(
        f"日文卡包索引：应检查 {len(card_ids)} 张，"
        f"已有 {len(card_ids) - len(pending_ids)} 张，待下载 {len(pending_ids)} 张。",
        flush=True,
    )

    def download_one(card_id: int) -> tuple[str, int, str | None]:
        for attempt in range(retries):
            try:
                with request(f"{API_BASE}/card/{card_id}?show=all", timeout=90) as response:
                    card = json.loads(response.read().decode("utf-8"))
                japanese_packs = card.get("jppacks") or []
                pack = next(
                    (
                        item.get("setid")
                        for item in japanese_packs
                        if isinstance(item, dict)
                        and isinstance(item.get("setid"), str)
                        and item["setid"]
                    ),
                    None,
                )
                return "downloaded", card_id, pack
            except (
                OSError,
                ValueError,
                urllib.error.URLError,
                urllib.error.HTTPError,
            ):
                time.sleep(min(5, attempt + 1))
        return "failed", card_id, None

    failed_ids = []
    japanese_count = sum(bool(value) for value in packs.values())
    if pending_ids:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(download_one, card_id) for card_id in pending_ids]
            for index, future in enumerate(
                concurrent.futures.as_completed(futures), start=1
            ):
                result, card_id, pack = future.result()
                if result == "failed":
                    failed_ids.append(card_id)
                else:
                    packs[str(card_id)] = pack
                    japanese_count += bool(pack)
                if index % 50 == 0 or index == len(pending_ids):
                    write_json_atomic(packs_path, packs)
                    print(
                        f"卡包进度 {index}/{len(pending_ids)}，"
                        f"已记录日文编号 {japanese_count}，失败 {len(failed_ids)}",
                        flush=True,
                    )
    elif not packs_path.exists():
        write_json_atomic(packs_path, packs)

    if failed_ids:
        failed_path.write_text(
            "\n".join(str(card_id).zfill(8) for card_id in failed_ids) + "\n",
            encoding="utf-8",
        )
    else:
        failed_path.unlink(missing_ok=True)

    return audit_card_packs(cards, output_dir)


def audit_card_packs(cards: dict, output_dir: Path) -> dict:
    expected_ids = {str(card_id) for card_id in valid_card_ids(cards)}
    packs_path = output_dir / "card_packs.json"
    packs = load_json_object(packs_path)

    actual_ids = set(packs)
    missing_ids = expected_ids - actual_ids
    invalid_ids = {
        card_id
        for card_id in expected_ids & actual_ids
        if packs.get(card_id) is not None
        and (not isinstance(packs[card_id], str) or not packs[card_id])
    }
    japanese_count = sum(
        isinstance(packs.get(card_id), str)
        and bool(packs.get(card_id))
        and card_id not in invalid_ids
        for card_id in expected_ids
    )
    empty_count = sum(
        card_id in actual_ids and packs.get(card_id) is None
        for card_id in expected_ids
    )
    print(
        f"日文卡包索引检查：应有 {len(expected_ids)}，有日文编号 {japanese_count}，"
        f"确认无日文编号 {empty_count}，缺失 {len(missing_ids)}，"
        f"无效记录 {len(invalid_ids)}",
        flush=True,
    )
    return {
        "expected": len(expected_ids),
        "japanese": japanese_count,
        "empty": empty_count,
        "missing": len(missing_ids),
        "invalid": len(invalid_ids),
    }


def download_images(cards: dict, output_dir: Path, workers: int, retries: int) -> dict:
    image_dir = output_dir / "卡图"
    image_dir.mkdir(parents=True, exist_ok=True)
    card_ids = sorted(valid_card_ids(cards))
    expected_ids = set(card_ids)
    cached_ids = scan_cached_image_ids(image_dir, expected_ids, verify=True)
    pending_ids = [card_id for card_id in card_ids if card_id not in cached_ids]

    def download_one(card_id: int) -> tuple[str, int]:
        for suffix in IMAGE_SUFFIXES:
            target = image_dir / f"{card_id:08d}.{suffix}"
            target.unlink(missing_ok=True)

        for suffix, url_template, needs_crop in IMAGE_SOURCES:
            target = image_dir / f"{card_id:08d}.{suffix}"
            for attempt in range(retries):
                try:
                    download(url_template.format(card_id=card_id), target, timeout=60)
                    if needs_crop:
                        crop_full_card_art(target)
                    if valid_image(target, verify=True):
                        return "downloaded", card_id
                except (OSError, urllib.error.URLError, urllib.error.HTTPError):
                    pass
                target.unlink(missing_ok=True)
                target.with_suffix(target.suffix + ".tmp").unlink(missing_ok=True)
                time.sleep(min(3, attempt + 1))
        return "failed", card_id

    counts = {"downloaded": 0, "cached": len(cached_ids), "failed": 0}
    failed_ids = []
    print(
        f"卡图总数 {len(card_ids)}，已有 {len(cached_ids)}，"
        f"待下载 {len(pending_ids)}。",
        flush=True,
    )
    if pending_ids:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            for index, (result, card_id) in enumerate(
                executor.map(download_one, pending_ids), start=1
            ):
                counts[result] += 1
                if result == "failed":
                    failed_ids.append(card_id)
                if index % 100 == 0 or index == len(pending_ids):
                    print(
                        f"下载进度 {index}/{len(pending_ids)}，"
                        f"新增 {counts['downloaded']}，"
                        f"已有 {counts['cached']}，失败 {counts['failed']}",
                        flush=True,
                    )
    failed_path = output_dir / "卡图下载失败.txt"
    if failed_ids:
        failed_path.write_text(
            "\n".join(str(card_id).zfill(8) for card_id in failed_ids) + "\n",
            encoding="utf-8",
        )
    else:
        failed_path.unlink(missing_ok=True)
    print(
        f"卡图下载完成：新增 {counts['downloaded']}，"
        f"已有 {counts['cached']}，失败 {counts['failed']}",
        flush=True,
    )
    return audit_images(cards, output_dir)


def audit_images(cards: dict, output_dir: Path) -> dict:
    image_dir = output_dir / "卡图"
    expected_ids = valid_card_ids(cards)
    valid_ids = set()
    invalid_files = []
    for image_path in image_dir.iterdir():
        if not image_path.is_file():
            continue
        try:
            card_id = int(image_path.stem)
        except ValueError:
            continue
        try:
            if not valid_image(image_path, verify=True):
                raise ValueError("invalid image")
            valid_ids.add(card_id)
        except (OSError, ValueError):
            invalid_files.append(image_path.name)

    missing_ids = sorted(expected_ids - valid_ids)
    print(
        f"完整性检查：应有 {len(expected_ids)}，有效 {len(valid_ids)}，"
        f"缺失 {len(missing_ids)}，损坏 {len(invalid_files)}",
        flush=True,
    )
    if missing_ids:
        print(
            "仍缺少的卡号：" + "、".join(str(card_id) for card_id in missing_ids),
            flush=True,
        )
    if invalid_files:
        print("损坏的卡图：" + "、".join(invalid_files), flush=True)
    return {
        "expected": len(expected_ids),
        "valid": len(valid_ids),
        "missing": len(missing_ids),
        "invalid": len(invalid_files),
    }


def parse_args() -> argparse.Namespace:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from runtime_paths import app_dir

    default_output = Path(app_dir()) / "离线卡库"
    parser = argparse.ArgumentParser(description="更新游戏王制卡器的百鸽离线卡库")
    parser.add_argument("--output", type=Path, default=default_output)
    parser.add_argument(
        "--images",
        action="store_true",
        help="同时下载全部卡图，耗时较长且会产生较大网络流量",
    )
    parser.add_argument(
        "--packs",
        action="store_true",
        help="下载全部卡片的最新日文卡包编号，支持断点续传",
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--retries", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cards = update_database(args.output.resolve())
    if args.packs:
        update_card_packs(
            cards,
            args.output.resolve(),
            max(1, args.workers),
            max(1, args.retries),
        )
    if args.images:
        download_images(
            cards,
            args.output.resolve(),
            max(1, args.workers),
            max(1, args.retries),
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"更新失败：{error}", file=sys.stderr)
        raise
