"""Build a deterministic, content-addressed application Lambda ZIP."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build_application(root=ROOT, dependency_dir=None, *, artifact_kind="application"):
    """Return (S3 key, bytes), using pinned Linux CPython 3.12 wheels."""
    if artifact_kind not in {"application", "worker"}:
        raise ValueError("Unknown runtime artifact kind")
    package = root / "career_coach"
    files = sorted(p for p in package.rglob("*") if p.is_file()
                   and p.suffix in {".py", ".json"} and "__pycache__" not in p.parts)
    if not (package / "__init__.py").is_file():
        raise ValueError("career_coach package is missing")
    requirements = root / "requirements-application.txt"
    pins = [line.strip() for line in requirements.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")]
    if not pins or any("==" not in pin or any(c in pin for c in " <>;[]") for pin in pins):
        raise ValueError("Application dependencies must be exactly pinned")
    wheels = Path(dependency_dir) if dependency_dir else root / ".lab" / "application-wheels"
    wheels.mkdir(parents=True, exist_ok=True)
    if dependency_dir is None:
        subprocess.run([sys.executable, "-m", "pip", "download", "--disable-pip-version-check",
            "--only-binary=:all:", "--no-deps", "--platform", "manylinux2014_x86_64",
            "--implementation", "cp", "--python-version", "312", "--abi", "cp312",
            "--dest", str(wheels), "-r", str(requirements)], check=True)
    lock = json.loads((root / "requirements-application.lock.json").read_text())
    entries = lock["wheels"]
    if [entry["name"] + "==" + entry["version"] for entry in entries] != pins:
        raise ValueError("Wheel lock does not match pinned application requirements")
    names = [entry["filename"] for entry in entries]
    if len(set(names)) != len(names) or set(names) != {p.name for p in wheels.glob("*.whl")}:
        raise ValueError("Wheelhouse contains missing or unexpected wheels")
    selected = []
    for entry in entries:
        name, version, filename = entry["name"], entry["version"], entry["filename"]
        prefix = name.lower().replace("-", "_") + "-" + version.lower() + "-"
        if (Path(filename).name != filename or not filename.lower().startswith(prefix) or
            not (filename.endswith("-none-any.whl") or
                 ("manylinux2014_x86_64" in filename and ("cp312" in filename or "abi3" in filename)))):
            raise ValueError(f"Invalid locked Linux wheel: {filename}")
        body = (wheels / filename).read_bytes()
        if hashlib.sha256(body).hexdigest() != entry["sha256"]:
            raise ValueError(f"Wheel SHA-256 mismatch: {filename}")
        selected.append((filename, body))
    contents = {path.relative_to(root).as_posix(): path.read_bytes() for path in files}
    manifest = {"artifact_kind": artifact_kind, "dependencies": pins,
                "wheels": {name: hashlib.sha256(body).hexdigest() for name, body in selected}}
    for _, body in selected:
        with zipfile.ZipFile(io.BytesIO(body)) as source:
            for info in source.infolist():
                name = info.filename
                if info.is_dir():
                    continue
                if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
                    raise ValueError(f"Unsafe wheel path: {name}")
                if ".data/" in name:
                    raise ValueError(f"Unsupported wheel data path: {name}")
                if name in contents:
                    raise ValueError(f"Duplicate artifact path: {name}")
                contents[name] = source.read(info)
    manifest["files"] = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(contents.items())}
    contents["application-manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    body = buffer.getvalue()
    return "lambda-artifacts/" + artifact_kind + "/" + hashlib.sha256(body).hexdigest() + ".zip", body


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dependency-dir", type=Path, help="Use an existing pinned Linux wheelhouse offline")
    parser.add_argument("--kind", choices=["application", "worker"], default="application")
    args = parser.parse_args()
    key, body = build_application(dependency_dir=args.dependency_dir, artifact_kind=args.kind)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(body)
    print(key)


if __name__ == "__main__":
    main()
