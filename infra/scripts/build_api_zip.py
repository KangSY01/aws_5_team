"""HTTPS API Lambda 코드 zip 빌드.

Lambda 는 arm64(Python 3.13)로 돌리므로 의존성을 arm64 wheel 로 받아 zip 에 담는다.
zip 루트 구성: 의존성 패키지 + app/ (backend/app 전체. 도구·Guardian 이 읽는 데이터 파일 app/data/ 포함)
Lambda 핸들러는 app.handler.handler 다.
크기 제한은 압축 250MB(S3 로 올릴 때) / 해제 250MB.

다른 빌드와 build/ 폴더를 나눠 쓴다 (AgentCore 용 build_zip.py 는 infra/build 를 통째로 지운다).

실행 (infra/ 에서): uv run --no-project python scripts/build_api_zip.py
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
BUILD = INFRA / "build" / "api"
PACKAGE = BUILD / "package"
ZIP_PATH = BUILD / "api_package.zip"

PYTHON_VERSION = "3.13"
MAX_UNZIPPED_BYTES = 250 * 1024 * 1024  # Lambda 는 압축을 푼 크기가 250MB 이하여야 한다
# zip 에 넣지 않는 것: 캐시, 로컬 원본 데이터(git 에도 올리지 않는 raw/)
IGNORED = ("__pycache__", "*.pyc", "raw")


def install_dependencies() -> None:
    subprocess.run(
        [
            "uv", "pip", "install",
            "--python-platform", "aarch64-manylinux2014",
            "--python-version", PYTHON_VERSION,
            "--target", str(PACKAGE),
            "--only-binary=:all:",
            "-r", str(INFRA / "api" / "requirements.txt"),
        ],
        check=True,
    )


def copy_sources() -> None:
    shutil.copytree(BACKEND_APP, PACKAGE / "app", ignore=shutil.ignore_patterns(*IGNORED))


def write_zip() -> int:
    """Windows 에서 만들어도 파일 644, 디렉터리 755 권한이 되도록 직접 기록한다. 압축을 푼 크기(바이트)를 돌려준다."""
    unzipped = 0
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
                data = path.read_bytes()
                unzipped += len(data)
                zf.writestr(info, data)
    return unzipped


def main() -> int:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    PACKAGE.mkdir(parents=True)

    install_dependencies()
    copy_sources()
    unzipped = write_zip()

    if unzipped > MAX_UNZIPPED_BYTES:
        print(f"압축을 푼 크기가 250MB 를 넘습니다: {unzipped / 1024 / 1024:.1f}MB", file=sys.stderr)
        return 1
    size = ZIP_PATH.stat().st_size
    sha = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()[:12]
    print(f"zip 크기 {size / 1024 / 1024:.1f}MB (압축 해제 {unzipped / 1024 / 1024:.1f}MB)")
    print(f"ZIP={ZIP_PATH} SHA={sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
