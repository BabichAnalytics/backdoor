# BACKDOOR — Backup & Verification

A local desktop utility inspired by Root's fictional diagnostic case. Copy a folder into a **new backup directory**, verify every copied file with SHA-256, and save a JSON report. Built for learning practical IT, reliable file handling, and troubleshooting.

**This is a backup prototype, not a hacking tool, deleted-file recovery system, or production disaster-recovery product.** It never bypasses access controls or sends your data to a remote service.

## Start on Windows

Install Python **3.12 or newer** from python.org with Tcl/Tk support (included in the standard Windows installer). Download this repository and extract it, then open a terminal in its folder:

```powershell
py app.py
```

If you use `python` instead of `py`, run `python app.py`. No third-party Python packages are required. macOS needs a Python installation with Tk; Linux distributions may require their `python3-tk` package. Test the command-line mode if a graphical display is unavailable.

1. Choose an existing source folder of **disposable test documents** first.
2. Choose an existing destination folder on your SSD or another separate location.
3. Select **Start verified backup**. Each run writes `backdoor-DATE-TIME-ID/files/` plus `report.json` inside your chosen destination.
4. Check the final status and any errors or skipped items. Use **Recheck a backup** to detect later changes to verified files.
5. **Export last report** saves a copy of the latest backup or recheck report.

## Command line

```powershell
py app.py backup "C:\TestDocuments" "E:\Backups"
py app.py verify "E:\Backups\backdoor-DATE-TIME-ID\report.json"
py -m unittest -v
```

Replace example paths with your actual folders. Source and destination must not be the same or nested inside each other. A CLI backup exits 0 only for `completed`; skipped links or errors produce exit 1. Verification exits 0 only when at least one recorded verified file is checked and every checked file matches.

## What it does

- Scans regular files, records sizes, and preserves empty directories.
- Streams copies in 1 MiB chunks without loading entire files into memory.
- Writes to unique partial names; independently rereads copied bytes for SHA-256 validation before promoting a file to verified.
- Checks source identity, size and timestamps for changes during copying.
- Records errors, skipped symbolic links/junctions, cancellation, and partial-copy paths.
- Retains incomplete copies rather than deleting them. They are **not verified backups**.
- Saves progress reports after each file; a killed process may leave an unfinished status and partial files.
- Supports read-only later verification, including manifest path-containment checks.

## Boundaries and limitations

Use only on files you own or are authorized to back up. Source files are opened for reading, but this is **not forensic write blocking**; operating systems may update access metadata. Live files are not snapshotted, and multi-file applications/databases may be inconsistent even when individual file checks pass. Stop applications or use their supported backup tools for important data.

Backup copies file contents, not full disk images, ACLs, ownership, extended attributes, alternate data streams, boot information, or all filesystem metadata. Symlinks/junctions and nonregular files are skipped. The destination must be trusted and not concurrently modified. This is not hardened against an adversary racing directory changes. Very long paths, locked files, full disks, disconnections and permissions may fail and are reported.

A recheck tests only entries previously marked verified; it does not certify skipped/failed files, detect extra files, or authenticate a modified report. SHA-256 integrity is not encryption or proof of who created a file. Empty backups have no verified-file integrity claim. Keep an independent off-device backup; a local SSD alone is not a complete recovery strategy.

Reports contain local paths and filenames. **Do not commit real reports or backup contents to GitHub.** Source and destination paths stay on your computer. No telemetry or network requests are implemented.

## Project structure

| File | Purpose |
|---|---|
| `engine.py` | Streaming copy, integrity checks, JSON manifests |
| `app.py` | Tkinter desktop interface and CLI |
| `test_engine.py` | Safety and integrity regression tests |

## Learning and validation

This portfolio prototype was developed with AI assistance. Review and understand the implementation before presenting it as independent proficiency. Tests cover verified nested/empty files, repeat-run isolation, invalid roots, tampering, cancellation, source mutation, symlinks, unsafe manifest paths, and empty verification. Automated checks do not establish production readiness or Windows GUI compatibility; test on your own machine and disposable data first.

Potential next steps: improved accessible UI, per-file retry, report signing, and separately designed restore workflows. No automatic deletion, remote administration, credential collection, or network intrusion functionality is included.
