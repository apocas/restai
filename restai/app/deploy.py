"""Bundle + ship helpers for App Builder projects.

Two outputs:
- :func:`stream_zip` produces a streaming ZIP of the project's source tree
  (used by the download endpoint).
- :func:`deploy_sftp` / :func:`deploy_ftp` push the same file set to a
  remote host via SFTP (paramiko) or plain FTP (stdlib ftplib). Both are
  generators of progress events suitable for a Server-Sent Events stream.

Generated apps are deliberately small (target 10-50 files), so the
"in-memory zip + sync upload" approach is fine — we don't need parallel
transfers or resumable uploads at this scale.

SSRF guard: ``restai.helper._is_private_ip`` is applied to the deploy
host before any socket is opened. We DO NOT want a project owner to be
able to talk to the AWS metadata service or internal infra by typing
"169.254.169.254" into the host field.
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
    """Knobs the user toggles in the Download dialog."""
    include_source: bool = False  # `src/*.ts` etc.; the deployed app only needs `dist/`
    include_db: bool = False      # `database.sqlite` — usually don't ship the dev DB to prod


def _iter_project_files(root: Path, filters: ZipFilters) -> Iterable[tuple[Path, str]]:
    """Yield ``(absolute_path, archive_name)`` for every file we want to
    ship. Walks the project root, skipping never-ship directories outright
    so we don't walk into `node_modules`."""
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        # In-place mutate dirnames so os.walk doesn't descend.
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
    """Generator of ZIP bytes for FastAPI's ``StreamingResponse``.

    Builds the archive in memory before yielding (a 50-file project with
    text files is at most a few hundred KB). Could be promoted to a true
    streaming writer later — premature optimization for now.
    """
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


# ────────────────────────────────────────────────────────────────────
# Deploy targets
# ────────────────────────────────────────────────────────────────────


def _resolve_host_safe(host: str) -> str:
    """Resolve `host` and refuse private/loopback/link-local addresses.

    Same SSRF guard pattern that `restai/helper.py:_is_private_ip` uses
    for inbound URL fetchers. Local dev against `localhost` is genuinely
    useful for testing; the caller can opt in with the `allow_private`
    flag at the deploy_* level if they really mean it.
    """
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
    """Normalize the remote target to an absolute POSIX path. The deploy
    endpoints pass `ftp_path` straight through; default to '/' if blank."""
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
    """Yield progress events while uploading to an SFTP server.

    Events: ``{"event": "connect" | "mkdir" | "upload" | "done" | "error", ...}``.

    Uses paramiko's high-level :class:`SSHClient` + :meth:`open_sftp` so we
    get the auth handshake for free. Host keys are NOT verified — first
    deploys to brand-new hosts would otherwise need a manual fingerprint
    dance. SSRF guard fires before any socket opens.
    """
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
    """`mkdir -p` over SFTP. paramiko has no built-in equivalent."""
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
    """Same shape as :func:`deploy_sftp` but for plain FTP. Many shared
    hosts only offer FTP, not SFTP.

    Note: FTP transmits credentials in cleartext. The UI warns about this
    explicitly; if the host supports SFTP, the user should pick SFTP.
    """
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
    """`mkdir -p` over FTP. ftplib's MKD only makes one level."""
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


# Connection test -----------------------------------------------------


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
    """Open a connection, list the remote dir, close. No transfers.

    Returns ``{"ok": True, "message": "..."}`` on success, or
    ``{"ok": False, "error": "..."}``."""
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
