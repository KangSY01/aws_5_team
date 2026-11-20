"""AgentCore Runtime 코드 zip 빌드.

AgentCore Runtime은 linux/arm64 만 지원하므로 의존성을 arm64 wheel 로 받아 zip 에 담는다.
zip 루트 구성: 의존성 패키지 + main.py + app/(backend/app 의 허용 목록만)
크기 제한은 압축 250MB / 해제 750MB.

실행 (infra/ 에서): uv run --no-project python scripts/build_zip.py
마지막 줄에 zip 경로와 sha256 앞 12자리를 `ZIP=<경로> SHA=<해시>` 형식으로 출력한다.
"""

import hashlib
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

INFRA = Path(__file__).resolve().parent.parent
BACKEND_APP = INFRA.parent / "backend" / "app"
BUILD = INFRA / "build"
PACKAGE = BUILD / "package"
ZIP_PATH = BUILD / "deployment_package.zip"

# backend/app 에서 zip 에 넣을 항목. 단계가 진행되면 여기에 추가한다.
APP_ALLOWLIST = ["__init__.py", "config.py", "models"]
PYTHON_VERSION = "3.13"
MAX_ZIP_BYTES = 250 * 1024 * 1024


def install_dependencies() -> None:
    subprocess.run(
        [
            "uv", "pip", "install",
            "--python-platform", "aarch64-manylinux2014",
            "--python-version", PYTHON_VERSION,
            "--target", str(PACKAGE),
            "--only-binary=:all:",
            "-r", str(INFRA / "agentcore" / "requirements.txt"),
        ],
        check=True,
    )


def copy_sources() -> None:
    shutil.copy2(INFRA / "agentcore" / "main.py", PACKAGE / "main.py")
    (PACKAGE / "app").mkdir()
    for name in APP_ALLOWLIST:
        src = BACKEND_APP / name
        dst = PACKAGE / "app" / name
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, dst)


def write_zip() -> None:
    """Windows 에서 만들어도 파일 644, 디렉터리 755 권한이 되도록 직접 기록한다."""
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PACKAGE.rglob("*")):
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            rel = path.relative_to(PACKAGE).as_posix()
            if path.is_dir():
                info = zipfile.ZipInfo(rel + "/")
                info.external_attr = (stat.S_IFDIR | 0o755) << 16
                zf.writestr(info, b"")
            else:
                info = zipfile.ZipInfo(rel)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                zf.writestr(info, path.read_bytes())


def main() -> int:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    PACKAGE.mkdir(parents=True)

    install_dependencies()
    copy_sources()
    write_zip()

    size = ZIP_PATH.stat().st_size
    if size > MAX_ZIP_BYTES:
        print(f"zip 이 250MB 를 넘습니다: {size / 1024 / 1024:.1f}MB", file=sys.stderr)
        return 1
    sha = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()[:12]
    print(f"zip 크기 {size / 1024 / 1024:.1f}MB")
    print(f"ZIP={ZIP_PATH} SHA={sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
