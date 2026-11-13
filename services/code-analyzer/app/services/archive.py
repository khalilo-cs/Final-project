"""Safe extraction of an uploaded project archive."""

import stat
import zipfile
from pathlib import Path


class ArchiveError(Exception):
    pass


def extract_zip(archive: Path, destination: Path, max_bytes: int, max_files: int) -> None:
    """Extract `archive` into `destination`, refusing zip-slip paths and zip bombs."""
    root = destination.resolve()
    try:
        with zipfile.ZipFile(archive) as bundle:
            members = [info for info in bundle.infolist() if not info.is_dir()]
            if len(members) > max_files:
                raise ArchiveError(f"archive has more than {max_files} files")
            if sum(info.file_size for info in members) > max_bytes:
                raise ArchiveError("archive is too large when extracted")

            written = 0
            for info in members:
                if stat.S_ISLNK(info.external_attr >> 16):
                    continue  # never materialize symlinks from an upload
                target = (root / info.filename).resolve()
                if not target.is_relative_to(root):
                    raise ArchiveError(f"unsafe path in archive: {info.filename}")
                target.parent.mkdir(parents=True, exist_ok=True)
                # Copy in chunks and count real bytes: header sizes can lie.
                with bundle.open(info) as source, open(target, "wb") as sink:
                    while chunk := source.read(1 << 16):
                        written += len(chunk)
                        if written > max_bytes:
                            raise ArchiveError("archive is too large when extracted")
                        sink.write(chunk)
    except zipfile.BadZipFile as exc:
        raise ArchiveError("not a valid ZIP archive") from exc
