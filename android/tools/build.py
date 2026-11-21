"""使用标准 Android SDK 构建 APK，无 Gradle/Maven 或网络运行依赖。"""
import argparse
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ANDROID = Path(__file__).resolve().parents[1]
PACKAGE = "YGODIY-Android-1.0.0"
API = "35"
TOOLS = "35.0.0"


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk", type=Path, default=os.getenv("ANDROID_HOME") or os.getenv("ANDROID_SDK_ROOT"))
    parser.add_argument("--jdk", type=Path, default=os.getenv("JAVA_HOME"))
    parser.add_argument("--keystore", type=Path, required=True)
    parser.add_argument("--alias", required=True)
    parser.add_argument("--debug", action="store_true", help="仅开发测试时允许 WebView 调试")
    args = parser.parse_args()
    if not args.sdk or not args.jdk:
        parser.error("请设置 ANDROID_HOME、JAVA_HOME 或传入 --sdk、--jdk。")
    if not os.getenv("YGODIY_STORE_PASS"):
        parser.error("请通过环境变量 YGODIY_STORE_PASS 提供签名库密码。")
    sdk = args.sdk / "build-tools" / TOOLS
    platform = args.sdk / "platforms" / ("android-" + API) / "android.jar"
    exe = ".exe" if os.name == "nt" else ""
    jdk = args.jdk / "bin"
    java = jdk / ("java" + exe)
    build = ANDROID / "build"
    build.mkdir(exist_ok=True)
    prepared = build / "assets"
    output = build / (PACKAGE + ("-debug" if args.debug else "") + ".apk")
    with tempfile.TemporaryDirectory(prefix="ygodiy-android-") as tmp:
        stage = Path(tmp)
        shutil.copytree(ANDROID / "res", stage / "res")
        shutil.copyfile(ANDROID / "AndroidManifest.xml", stage / "AndroidManifest.xml")
        assets = stage / "assets"
        shutil.copytree(ANDROID / "web", assets)
        for name in ("runtime", "fig", "frames", "notices"):
            shutil.copytree(prepared / name, assets / name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("*.zip") if name == "runtime" else None)
        for name in ("art.json", "library.json", "reader.py"):
            shutil.copy2(prepared / name, assets / name)
        aapt = sdk / ("aapt2" + exe)
        run(aapt, "compile", "--dir", stage / "res", "-o", stage / "res.zip")
        run(aapt, "link", "-I", platform, "--manifest", stage / "AndroidManifest.xml",
            *(["--debug-mode"] if args.debug else []),
            "-o", stage / "base.apk", stage / "res.zip")
        classes = stage / "classes"
        classes.mkdir()
        run(jdk / ("javac" + exe), "-encoding", "UTF-8", "--release", "8", "-cp", platform,
            "-d", classes, *sorted((ANDROID / "src").rglob("*.java")))
        with zipfile.ZipFile(stage / "classes.jar", "w") as jar:
            for path in classes.rglob("*.class"):
                jar.write(path, path.relative_to(classes))
        run(java, "-cp", sdk / "lib/d8.jar", "com.android.tools.r8.D8", "--release",
            "--min-api", "29", "--lib", platform, "--output", stage, stage / "classes.jar")
        with zipfile.ZipFile(stage / "base.apk", "a") as apk:
            for source in sorted(assets.rglob("*")):
                if source.is_file():
                    apk.write(source, source.relative_to(stage).as_posix(), compress_type=zipfile.ZIP_DEFLATED)
            apk.write(stage / "classes.dex", "classes.dex", compress_type=zipfile.ZIP_DEFLATED)
        run(sdk / ("zipalign" + exe), "-f", "4", stage / "base.apk", stage / "aligned.apk")
        signer = (java, "-jar", sdk / "lib/apksigner.jar")
        run(*signer, "sign", "--ks", args.keystore, "--ks-key-alias", args.alias,
            "--ks-pass", "env:YGODIY_STORE_PASS", "--key-pass",
            "env:" + ("YGODIY_KEY_PASS" if os.getenv("YGODIY_KEY_PASS") else "YGODIY_STORE_PASS"),
            "--v4-signing-enabled", "false", "--out", stage / "signed.apk", stage / "aligned.apk")
        run(*signer, "verify", "--verbose", "--print-certs", stage / "signed.apk")
        shutil.copyfile(stage / "signed.apk", output.with_suffix(".tmp"))
        output.with_suffix(".tmp").replace(output)
    print(output)


if __name__ == "__main__":
    main()
