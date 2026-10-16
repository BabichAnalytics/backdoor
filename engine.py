"""Copy-only backup engine. No network access or source-file mutations."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import threading
import uuid
from datetime import datetime, timezone

CHUNK = 1024 * 1024

def now():
    return datetime.now(timezone.utc).isoformat()

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(CHUNK), b''):
            h.update(block)
    return h.hexdigest()

def roots(source, destination):
    source, destination = Path(source).expanduser().resolve(), Path(destination).expanduser().resolve()
    if not source.is_dir() or not destination.is_dir():
        raise ValueError('Select an existing source folder and destination folder.')
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError('Source and destination must be separate, non-nested folders.')
    return source, destination

def save_report(run, report):
    temporary = run / 'report.json.tmp'
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
    os.replace(temporary, run / 'report.json')

def backup(source, destination, cancel=None, notify=None):
    """Create a fresh backup folder; verified means copied bytes match at copy time.

    File changes during copy are detected by stat checks. This is not a snapshot
    and cannot guarantee consistency across multiple live application files.
    """
    source, destination = roots(source, destination)
    cancel = cancel or threading.Event()
    notify = notify or (lambda event: None)
    run = destination / ('backdoor-' + datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    run.mkdir()  # Never reuse an earlier backup.
    payload = run / 'files'
    payload.mkdir()
    report = {'format': 'backdoor-backup-v1', 'started_utc': now(), 'source': str(source),
              'run_folder': str(run), 'status': 'scanning', 'files': [], 'scan_errors': [],
              'skipped': [], 'empty_directories': [], 'bytes_copied': 0, 'total_bytes': 0}
    save_report(run, report)
    candidates = []
    def scan_error(error):
        report['scan_errors'].append(str(error))
    for base, dirs, names in os.walk(source, followlinks=False, onerror=scan_error):
        if cancel.is_set():
            break
        base = Path(base)
        safe_dirs = []
        for name in sorted(dirs):
            path = base / name
            # Reject Windows junctions too; they may point outside the source.
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                report['skipped'].append(str(path.relative_to(source)))
            else:
                safe_dirs.append(name)
        dirs[:] = safe_dirs
        if not dirs and not names:
            report['empty_directories'].append(str(base.relative_to(source)))
        for name in sorted(names):
            path = base / name
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode):
                    report['skipped'].append(str(path.relative_to(source)))
                    continue
                candidates.append((path, info.st_size))
                report['total_bytes'] += info.st_size
            except OSError as exc:
                report['scan_errors'].append(str(exc))
    report['total_files'] = len(candidates)
    report['status'] = 'copying'
    save_report(run, report)
    notify(dict(report, event='scan'))
    if shutil.disk_usage(destination).free < report['total_bytes'] + 1024 * 1024:
        report['scan_errors'].append('Insufficient destination free space (includes 1 MiB reserve).')
        candidates = []
    for path, scanned_size in candidates:
        if cancel.is_set():
            break
        relative = path.relative_to(source)
        target = payload / relative
        entry = {'path': relative.as_posix(), 'status': 'copying', 'size': scanned_size}
        report['files'].append(entry)
        partial = None
        try:
            # Recheck containment after scanning; do not follow renamed links.
            if path.resolve() != path or not path.is_relative_to(source):
                raise OSError('Source path changed or contains a symbolic link.')
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode):
                raise OSError('Source is no longer a regular file.')
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(target.name + '.partial-' + uuid.uuid4().hex)
            h = hashlib.sha256()
            flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
            fd = os.open(path, flags)
            with os.fdopen(fd, 'rb') as src, open(partial, 'xb') as dst:
                opened = os.fstat(src.fileno())
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise OSError('Source changed before opening.')
                while True:
                    if cancel.is_set():
                        raise InterruptedError('Cancelled; partial copy is not verified.')
                    block = src.read(CHUNK)
                    if not block:
                        break
                    dst.write(block)
                    h.update(block)
                    report['bytes_copied'] += len(block)
                    notify({'event': 'progress', 'path': entry['path'], 'bytes_copied': report['bytes_copied'],
                            'total_bytes': report['total_bytes'], 'total_files': len(candidates)})
                dst.flush()
                os.fsync(dst.fileno())
                after = os.fstat(src.fileno())
            current = path.lstat()
            signature = lambda v: (v.st_dev, v.st_ino, v.st_size, v.st_mtime_ns, v.st_ctime_ns)
            if signature(before) != signature(after) or signature(after) != signature(current):
                raise OSError('Source changed during copy; retry when the file is idle.')
            if digest(partial) != h.hexdigest():
                raise OSError('Destination checksum mismatch.')
            # Fresh run directory and exclusive partial file prevent accidental reuse.
            if target.exists():
                raise OSError('Unexpected destination file already exists.')
            partial.rename(target)
            entry.update(status='verified', size=after.st_size, sha256=h.hexdigest())
        except Exception as exc:
            entry.update(status='cancelled' if isinstance(exc, InterruptedError) else 'error', error=str(exc))
            if partial is not None and partial.exists():
                entry['partial_file'] = partial.relative_to(run).as_posix()
        save_report(run, report)
        notify({'event': 'file', 'path': entry['path'], 'status': entry['status']})
    if not cancel.is_set():
        for relative in report['empty_directories']:
            (payload / relative).mkdir(parents=True, exist_ok=True)
    errors = report['scan_errors'] or any(e['status'] != 'verified' for e in report['files'])
    report['status'] = 'cancelled' if cancel.is_set() else ('completed_with_issues' if errors or report['skipped'] else 'completed')
    report['finished_utc'] = now()
    report['verified_files'] = sum(e['status'] == 'verified' for e in report['files'])
    save_report(run, report)
    notify(dict(report, event='done'))
    return report

def verify_report(report_path):
    """Read-only integrity check of backup payload against the saved manifest."""
    report_path = Path(report_path).resolve()
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if report.get('format') != 'backdoor-backup-v1':
        raise ValueError('Not a Backdoor backup report.')
    payload = (report_path.parent / 'files').resolve()
    results = []
    for entry in report['files']:
        if entry['status'] != 'verified':
            continue
        candidate = payload / entry['path']
        target = candidate.resolve()
        if target == payload or payload not in target.parents or target != candidate or candidate.is_symlink():
            results.append({'path': entry['path'], 'status': 'unsafe_path'})
            continue
        try:
            match = target.is_file() and target.stat().st_size == entry['size'] and digest(target) == entry['sha256']
            results.append({'path': entry['path'], 'status': 'match' if match else 'mismatch_or_missing'})
        except OSError:
            results.append({'path': entry['path'], 'status': 'unreadable'})
    return {'checked_utc': now(), 'files_checked': len(results),
            'all_match': bool(results) and all(r['status'] == 'match' for r in results),
            'original_status': report['status'], 'results': results}
