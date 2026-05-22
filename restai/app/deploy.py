"""Bundle + ship helpers for App Builder projects.

stream_zip produces a streaming ZIP of the project tree; deploy_sftp /
deploy_ftp push the same file set as generators of progress events.

SSRF guard: restai.helper._is_private_ip is applied to the deploy host
before any socket opens — refuses AWS metadata / internal LAN targets.
"""

from __future__ import annotations

import io
import logging
import os
import socket
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Iterable, Optional

logger = logging.getLogger(__name__)


# Patterns that NEVER ship to a deployed host. `node_modules` is huge and
# pure dev. `.git` is wrong on a production host (info leak + exec risk).
# Hidden dotfiles are excluded by default but can be re-included by an
# explicit override (`.htaccess` is forbidden by the LLM prompt anyway).
_NEVER_SHIP_DIRS = {"node_modules", ".git", "__pycache__", ".cache", ".vscode", ".idea"}
_NEVER_SHIP_FILE_NAMES = {".DS_Store", "Thumbs.db"}


@dataclass(frozen=True)
class ZipFilters:
    include_source: bool = False  # `src/*.ts` etc.; the deployed app only needs `dist/`
    include_db: bool = False      # `database.sqlite` — usually don't ship the dev DB to prod


def _iter_project_files(root: Path, filters: ZipFilters) -> Iterable[tuple[Path, str]]:
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        # Mutate dirnames in place so os.walk skips never-ship dirs entirely.
        dirnames[:] = [d for d in dirnames if d not in _NEVER_SHIP_DIRS]
        rel_dir = Path(dirpath).relative_to(root)
        for fn in filenames:
            if fn in _NEVER_SHIP_FILE_NAMES:
                continue
            rel = (rel_dir / fn).as_posix()
            # Apply per-flag filters.
            if not filters.include_source:
                # The compiled `dist/app.js` is what runs in the browser
                # on the deployed host; the `src/` source is dev-only.
                if rel.startswith("src/"):
                    continue
            if not filters.include_db:
                if rel == "database.sqlite" or rel.endswith("/database.sqlite"):
                    continue
            yield Path(dirpath) / fn, rel


def stream_zip(root: Path, filters: ZipFilters) -> Generator[bytes, None, None]:
    """Generator of ZIP bytes for FastAPI's StreamingResponse. Builds in-memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for abs_path, name in _iter_project_files(root, filters):
            try:
                zf.write(abs_path, name)
            except OSError as e:
                logger.warning("zip: skipping %s — %s", abs_path, e)
    buf.seek(0)
    # 64K chunks — big enough to amortize overhead, small enough that the
    # client sees the download progress.
    while True:
        chunk = buf.read(64 * 1024)
        if not chunk:
            return
        yield chunk


def _resolve_host_safe(host: str) -> str:
    """Same SSRF guard pattern as restai/helper.py:_is_private_ip. Local dev
    is opt-in via allow_private on the deploy_* call sites."""
    from restai.helper import _is_private_ip
    try:
        if _is_private_ip(host):
            raise ValueError(f"refusing to deploy to private/loopback host {host!r}")
    except ValueError:
        raise
    except Exception as e:
        # `_is_private_ip` raises ValueError("Cannot resolve hostname...")
        # when DNS fails. Surface that as a deploy error rather than letting
        # it become a generic "deploy failed".
        raise ValueError(f"could not resolve host {host!r}: {e}")
    return host


def _norm_remote_dir(p: Optional[str]) -> str:
    if not p:
        return "/"
    p = p.strip()
    if not p.startswith("/"):
        p = "/" + p
    return p.rstrip("/") or "/"


# SFTP via paramiko ----------------------------------------------------


def deploy_sftp(
    root: Path,
    filters: ZipFilters,
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    remote_dir: str,
    allow_private: bool = False,
) -> Generator[dict, None, None]:
    """Yields {"event": ...} progress dicts. Host keys NOT verified (first-deploy UX)."""
    if not allow_private:
        _resolve_host_safe(host)

    import paramiko
    yield {"event": "connect", "message": f"Connecting to sftp://{user}@{host}:{port}"}
    transport = None
    sftp = None
    try:
        transport = paramiko.Transport((host, port or 22))
        transport.banner_timeout = 15
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
        if sftp is None:
            raise RuntimeError("SFTP subsystem unavailable on the remote host")
        remote_root = _norm_remote_dir(remote_dir)
        yield {"event": "mkdir", "message": f"cd {remote_root}"}
        _sftp_makedirs(sftp, remote_root)

        files = list(_iter_project_files(root, filters))
        for idx, (abs_path, name) in enumerate(files, 1):
            target = remote_root.rstrip("/") + "/" + name
            _sftp_makedirs(sftp, os.path.dirname(target) or remote_root)
            sftp.put(str(abs_path), target)
            yield {"event": "upload", "path": name, "index": idx, "total": len(files)}
        yield {"event": "done", "uploaded": len(files), "remote_dir": remote_root}
    except Exception as e:
        logger.exception("SFTP deploy failed for host=%s", host)
        yield {"event": "error", "message": str(e)}
    finally:
        try:
            if sftp is not None:
                sftp.close()
        except Exception:
            pass
        try:
            if transport is not None:
                transport.close()
        except Exception:
            pass


def _sftp_makedirs(sftp, path: str) -> None:
    # mkdir -p over SFTP; paramiko has no built-in equivalent.
    if not path or path == "/":
        return
    parts = path.strip("/").split("/")
    cursor = ""
    for part in parts:
        cursor = cursor + "/" + part if cursor else "/" + part
        try:
            sftp.stat(cursor)
        except IOError:
            try:
                sftp.mkdir(cursor)
            except IOError:
                # Race with another deploy or directory was created
                # between stat and mkdir — re-stat to confirm it exists.
                sftp.stat(cursor)


# Plain FTP via stdlib -------------------------------------------------


def deploy_ftp(
    root: Path,
    filters: ZipFilters,
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    remote_dir: str,
    use_passive: bool = True,
    allow_private: bool = False,
) -> Generator[dict, None, None]:
    """Plain-FTP variant of deploy_sftp. Credentials are cleartext (UI warns)."""
    if not allow_private:
        _resolve_host_safe(host)

    from ftplib import FTP, error_perm
    yield {"event": "connect", "message": f"Connecting to ftp://{user}@{host}:{port}"}
    ftp = None
    try:
        ftp = FTP()
        ftp.connect(host, port or 21, timeout=20)
        ftp.login(user, password)
        ftp.set_pasv(bool(use_passive))
        remote_root = _norm_remote_dir(remote_dir)
        yield {"event": "mkdir", "message": f"cwd {remote_root}"}
        _ftp_makedirs(ftp, remote_root)
        ftp.cwd(remote_root)

        files = list(_iter_project_files(root, filters))
        for idx, (abs_path, name) in enumerate(files, 1):
            target_dir, target_name = os.path.split(name)
            if target_dir:
                _ftp_makedirs(ftp, remote_root.rstrip("/") + "/" + target_dir)
                ftp.cwd(remote_root.rstrip("/") + "/" + target_dir)
            else:
                ftp.cwd(remote_root)
            with open(abs_path, "rb") as fh:
                # FTP `STOR` is binary by default; we never want ASCII mode
                # for our generated files (esbuild output, PHP, CSS — all
                # safe as binary, and ASCII mode would corrupt UTF-8 BOMs).
                ftp.storbinary(f"STOR {target_name}", fh)
            yield {"event": "upload", "path": name, "index": idx, "total": len(files)}
        yield {"event": "done", "uploaded": len(files), "remote_dir": remote_root}
    except error_perm as e:
        yield {"event": "error", "message": f"FTP permission denied: {e}"}
    except Exception as e:
        logger.exception("FTP deploy failed for host=%s", host)
        yield {"event": "error", "message": str(e)}
    finally:
        try:
            if ftp is not None:
                ftp.quit()
        except Exception:
            try:
                if ftp is not None:
                    ftp.close()
            except Exception:
                pass


def _ftp_makedirs(ftp, path: str) -> None:
    # mkdir -p over FTP; ftplib's MKD only makes one level.
    from ftplib import error_perm
    if not path or path == "/":
        return
    parts = path.strip("/").split("/")
    cursor = ""
    for part in parts:
        cursor = cursor + "/" + part if cursor else "/" + part
        try:
            ftp.mkd(cursor)
        except error_perm:
            # Likely "directory already exists" — fine.
            pass


def test_connection(
    *,
    protocol: str,
    host: str,
    port: int,
    user: str,
    password: str,
    remote_dir: str,
    use_passive: bool = True,
    allow_private: bool = False,
) -> dict:
    """Open + list + close. Returns {"ok": True, "message": ...} or {"ok": False, "error": ...}."""
    if not host:
        return {"ok": False, "error": "host is required"}
    try:
        if not allow_private:
            _resolve_host_safe(host)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    proto = (protocol or "sftp").lower()
    remote = _norm_remote_dir(remote_dir)
    try:
        if proto == "sftp":
            import paramiko
            transport = paramiko.Transport((host, port or 22))
            transport.banner_timeout = 15
            try:
                transport.connect(username=user, password=password)
                sftp = paramiko.SFTPClient.from_transport(transport)
                if sftp is None:
                    return {"ok": False, "error": "SFTP subsystem unavailable"}
                try:
                    listing = sftp.listdir(remote)
                finally:
                    sftp.close()
            finally:
                transport.close()
            return {"ok": True, "message": f"Connected. {len(listing)} entries in {remote}."}
        elif proto == "ftp":
            from ftplib import FTP
            ftp = FTP()
            try:
                ftp.connect(host, port or 21, timeout=15)
                ftp.login(user, password)
                ftp.set_pasv(bool(use_passive))
                ftp.cwd(remote)
                listing = ftp.nlst()
            finally:
                try:
                    ftp.quit()
                except Exception:
                    try:
                        ftp.close()
                    except Exception:
                        pass
            return {"ok": True, "message": f"Connected. {len(listing)} entries in {remote}."}
        else:
            return {"ok": False, "error": f"unknown protocol: {protocol!r}"}
    except socket.gaierror as e:
        return {"ok": False, "error": f"DNS resolution failed: {e}"}
    except socket.timeout:
        return {"ok": False, "error": "connection timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
