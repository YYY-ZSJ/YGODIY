"""准备独立 APK 的资源目录，也可作为浏览器回归测试的静态目录。"""
import argparse
import os
import shutil
from pathlib import Path

import art_data
import blocks_data
import runtime

ANDROID = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resources", type=Path, default=os.environ.get("YGODIY_RESOURCES", ANDROID.parent / "resources"))
    parser.add_argument("--cache", type=Path, default=ANDROID / "build/cache")
    args = parser.parse_args()
    dest = ANDROID / "build/assets"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ANDROID / "notices", dest / "notices", dirs_exist_ok=True)
    runtime.prepare(dest, args.cache)
    count = blocks_data.prepare(dest)
    art_data.prepare(args.resources, dest)
    print(f"已准备 {count} 种中文积木及移动卡面资源。")


if __name__ == "__main__":
    main()
