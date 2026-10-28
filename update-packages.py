#!/usr/bin/env python3
"""Version check + update for the pinned packages of the Outpost image.

Checks the two frozen files of the production image against their sources:

  * project/requirements_pip.txt  -> PyPI (https://pypi.org)
  * project/requirements_apk.txt  -> the alpine package index of the alpine
    release used by project/Dockerfile (parsed from the FROM line), main +
    community repos

Version policy:
  * a newer release with the same leading (first) version number is applied
    automatically (e.g. 2.9.x within 2.x, all 0.x within 0);
  * a release with a different first version number is never applied - it is
    only reported (job log + MR description). Review it and bump the pin by
    hand when you adopt it.

Pre-releases and fully yanked releases are ignored. The script is safe to
run repeatedly: it always converges to "latest within series".

Usage:
  python3 update-packages.py                    dry run (print report only)
  python3 update-packages.py --yes              apply the safe updates in place
  python3 update-packages.py --report-file f    markdown report destination
                                                (default: package-update-report.md)

Requires the `packaging` module (pip install packaging).

The CI job (update-packages in .gitlab-ci.yml) runs this on a schedule,
pushes the changed files to the single, long-lived branch
ci/update-packages and keeps one accumulating merge request up to date
(create-mr.py).
"""
import argparse
import io
import json
import re
import sys
import tarfile
import time
import urllib.request
from datetime import datetime
from datetime import timezone
from pathlib import Path

try:
    from packaging.version import Version
except ImportError:
    sys.exit("error: the 'packaging' module is required (pip install packaging)")

BASE = Path(__file__).resolve().parent
PIP_REQ = BASE / "project" / "requirements_pip.txt"
APK_REQ = BASE / "project" / "requirements_apk.txt"
DOCKERFILE = BASE / "project" / "Dockerfile"
ARCH = "x86_64"
REPOS = ("main", "community")

PIP_RE = re.compile(r"^([A-Za-z0-9._\[\]-]+)==([^\s#]+)$")
APK_RE = re.compile(r"^([A-Za-z0-9._\[\]-]+)=(?!=)([^\s#]+)$")

applied = []  # (source, name, old, new)
pending_major = []  # (source, name, old, new)
warnings = []


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"WARNING: {msg}", file=sys.stderr)


def http_get(url: str, timeout: int = 30, attempts: int = 3) -> bytes:
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001 - warn & retry
            last = exc
            if i < attempts - 1:
                time.sleep(2)
    raise last


def parse_pins(path: Path, rx: re.Pattern) -> list[tuple[str, str]]:
    pins = []
    for line in path.read_text().splitlines():
        m = rx.match(line)
        if m:
            pins.append((m.group(1), m.group(2)))
    return pins


# --------------------------------------------------------------------- pypi


def pypi_candidates(name: str) -> list[Version]:
    """All installable stable releases of a package on PyPI."""
    data = json.loads(http_get(f"https://pypi.org/pypi/{name}/json"))
    out = []
    for ver, files in data.get("releases", {}).items():
        if not files or all(f.get("yanked") for f in files):
            continue  # unavailable
        try:
            v = Version(ver)
        except Exception:  # noqa: BLE001 - skip unparseable
            continue
        if v.is_prerelease:
            continue
        out.append(v)
    return out


def series_prefix(v: Version) -> tuple[int, ...]:
    """The version components that define the compatibility series."""
    rel = v.release
    if not rel:
        return ()
    return rel[:1]  # the first version number


def check_pypi(pins: list[tuple[str, str]]) -> None:
    for name, version in pins:
        try:
            candidates = pypi_candidates(name)
        except Exception as exc:  # noqa: BLE001 - warn & continue
            warn(f"pypi: could not query {name} ({exc}); skipped")
            continue
        if not candidates:
            warn(f"pypi: no stable releases found for {name}; skipped")
            continue
        try:
            current = Version(version)
        except Exception:  # noqa: BLE001
            warn(f"pypi: unparsable pinned version {name}=={version}; skipped")
            continue
        prefix = series_prefix(current)
        in_series = [
            v for v in candidates if not prefix or v.release[: len(prefix)] == prefix
        ]
        latest_series = max(in_series) if in_series else None
        latest_overall = max(candidates)
        if latest_overall <= current:
            if latest_overall < current:
                warn(
                    f"pypi: {name}=={version} is newer than the newest PyPI "
                    f"release {latest_overall}; skipped"
                )
            continue
        if latest_series is not None and latest_series > current:
            applied.append(("pypi", name, str(version), str(latest_series)))
        if latest_overall not in in_series:
            pending_major.append(("pypi", name, str(version), str(latest_overall)))


# -------------------------------------------------------------------- alpine


def alpine_release_from_dockerfile() -> str | None:
    m = re.search(r"alpine(\d+\.\d+)", DOCKERFILE.read_text())
    return m.group(1) if m else None


def apkindex_versions(release: str) -> dict[str, str]:
    """package name -> 'upstream-rRevision' for one alpine release."""
    idx: dict[str, str] = {}
    for repo in REPOS:
        url = (
            f"https://dl-cdn.alpinelinux.org/alpine/v{release}/"
            f"{repo}/{ARCH}/APKINDEX.tar.gz"
        )
        try:
            raw = http_get(url, timeout=60)
        except Exception as exc:  # noqa: BLE001 - warn & continue
            warn(f"alpine: could not fetch {repo} index ({exc}); skipped")
            continue
        try:
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
                member = next(
                    (m for m in tf.getmembers() if m.name == "APKINDEX"), None
                )
                f = tf.extractfile(member) if member else None
                if f is None:
                    continue
                current = None
                for line in f.read().decode(errors="replace").splitlines():
                    if line.startswith("P:"):
                        current = line[2:].strip()
                    elif line.startswith("V:") and current:
                        idx.setdefault(current, line[2:].strip())
        except Exception as exc:  # noqa: BLE001 - warn & continue
            warn(f"alpine: could not parse {repo} index ({exc}); skipped")
    return idx


def split_apk(v: str) -> tuple[str, str]:
    """'10.2_p1-r0' -> ('10.2_p1', '0'); keeps the last '-r<digits>'."""
    m = re.match(r"^(.*)-r(\d+)$", v)
    return (m.group(1), m.group(2)) if m else (v, "0")


def leading_numeric_tuple(v: str) -> tuple[int, ...]:
    """'10.2_p1' -> (10, 2); '20251016.3.1' -> (20251016, 3, 1)."""
    m = re.match(r"((?:\d+\.)*\d+)", v)
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def check_apk(pins: list[tuple[str, str]]) -> None:
    release = alpine_release_from_dockerfile()
    if not release:
        warn(
            "alpine: could not determine the alpine release from project/Dockerfile; apk check skipped"
        )
        return
    idx = apkindex_versions(release)
    if not idx:
        warn("alpine: no package index could be fetched; apk check skipped")
        return
    for name, version in pins:
        cur = idx.get(name)
        if cur is None:
            warn(
                f"alpine: {name} not found in the alpine v{release} index (main/community); skipped"
            )
            continue
        pin_v, _ = split_apk(version)
        idx_v, _ = split_apk(cur)
        pt = leading_numeric_tuple(pin_v)
        it = leading_numeric_tuple(idx_v)
        n = max(len(pt), len(it))
        pt = pt + (0,) * (n - len(pt))
        it = it + (0,) * (n - len(it))
        if it < pt:
            warn(
                f"alpine: {name}={version} is newer than the alpine repo version {cur}; skipped"
            )
            continue
        if it > pt:
            if pt[0] == it[0]:
                applied.append(("alpine", name, version, cur))
            else:
                pending_major.append(("alpine", name, version, cur))
        elif cur != version:
            # same upstream version core: alpine re-release (revision bump
            # or build suffix change) - safe to follow
            applied.append(("alpine", name, version, cur))


# ------------------------------------------------------------------- report


def build_report() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L = [
        f"# Package update report - {now}",
        "",
        "Automated by the scheduled `update-packages` job. This branch/MR "
        "accumulates minor/patch updates over time - merge when you need "
        "them (e.g. due to a CVE).",
        "",
        "## Applied (minor/patch within the pinned series)",
    ]
    if applied:
        L += ["", "| source | package | was | now |", "|---|---|---|---|"]
        L += [f"| {s} | {n} | {o} | {w} |" for s, n, o, w in sorted(applied)]
    else:
        L += ["", "_none - all pins are up to date within their series_"]
    L += ["", "## NOT applied: new major versions (breaking changes possible)"]
    if pending_major:
        L += ["", "| source | package | current | latest |", "|---|---|---|---|"]
        L += [f"| {s} | {n} | {o} | {w} |" for s, n, o, w in sorted(pending_major)]
        L += [
            "",
            "_Review manually; bump the pin in `project/requirements_*.txt` "
            "by hand to adopt a major version._",
        ]
    else:
        L += ["", "_none_"]
    if warnings:
        L += ["", "## Warnings", ""]
        L += [f"- {w}" for w in warnings]
    L.append("")
    return "\n".join(L)


def apply_updates(path: Path, updates: dict[str, str], rx: re.Pattern, sep: str) -> int:
    if not updates:
        return 0
    text = path.read_text()
    lines = text.splitlines()
    changed = 0
    out = []
    for line in lines:
        m = rx.match(line)
        if m and m.group(1) in updates:
            line = f"{m.group(1)}{sep}{updates[m.group(1)]}"
            changed += 1
        out.append(line)
    path.write_text("\n".join(out) + ("\n" if text.endswith("\n") else ""))
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--yes",
        action="store_true",
        help="apply the safe updates in place (default: dry run)",
    )
    ap.add_argument(
        "--report-file",
        default=str(BASE / "package-update-report.md"),
        help="markdown report destination",
    )
    args = ap.parse_args()

    pip_pins = parse_pins(PIP_REQ, PIP_RE)
    apk_pins = parse_pins(APK_REQ, APK_RE)
    check_pypi(pip_pins)
    check_apk(apk_pins)

    pip_updates = {n: w for s, n, o, w in applied if s == "pypi"}
    apk_updates = {n: w for s, n, o, w in applied if s == "alpine"}

    if args.yes and (pip_updates or apk_updates):
        n1 = apply_updates(PIP_REQ, pip_updates, PIP_RE, "==")
        n2 = apply_updates(APK_REQ, apk_updates, APK_RE, "=")
        print(
            f"updated: {n1} pip pin(s) in {PIP_REQ.name}, {n2} apk pin(s) in {APK_REQ.name}"
        )
    elif pip_updates or apk_updates:
        print("dry run - re-run with --yes to apply.")

    report = build_report()
    print(report)
    Path(args.report_file).write_text(report)

    print(
        f"summary: {len(applied)} minor/patch update(s) applied, "
        f"{len(pending_major)} major version(s) pending review, "
        f"{len(warnings)} warning(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
