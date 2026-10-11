from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile
import hashlib
import tempfile
import shutil

# Relative to this Python file, not the working directory.
PROJECT_DIR = Path(__file__).resolve().parent
FFMPEG_DIR = PROJECT_DIR / ".bin" / "ffmpeg"

# Latest stable Windows essentials build.
URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def ensure_ffmpeg() -> Path:
    """Ensure FFmpeg and FFprobe exist; return their directory."""

    ffmpeg = FFMPEG_DIR / "ffmpeg.exe"
    ffprobe = FFMPEG_DIR / "ffprobe.exe"

    if ffmpeg.is_file() and ffprobe.is_file():
        return FFMPEG_DIR

    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        archive = temp / "ffmpeg.zip"

        # Download the archive.
        with urlopen(URL, timeout=60) as response:
            with archive.open("wb") as file:
                shutil.copyfileobj(response, file)

        # Verify against the publisher's SHA-256 checksum.
        with urlopen(URL + ".sha256", timeout=30) as response:
            checksum_text = response.read().decode("utf-8")

        expected_hash = checksum_text.split()[0].lower()

        digest = hashlib.sha256()
        with archive.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)

        if digest.hexdigest() != expected_hash:
            raise RuntimeError("FFmpeg archive checksum verification failed")

        # Extract only the two executables we need.
        with ZipFile(archive) as zip_file:
            for executable in ("ffmpeg.exe", "ffprobe.exe"):
                matches = [
                    name for name in zip_file.namelist()
                    if name.replace("\\", "/").endswith(
                        "/bin/" + executable
                    )
                ]

                if not matches:
                    raise RuntimeError(
                        f"{executable} was not found in the FFmpeg archive"
                    )

                destination = FFMPEG_DIR / executable
                with zip_file.open(matches[0]) as source:
                    with destination.open("wb") as target:
                        shutil.copyfileobj(source, target)

    return FFMPEG_DIR