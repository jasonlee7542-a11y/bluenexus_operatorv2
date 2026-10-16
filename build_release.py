"""Build the GitHub upload ZIP without confidential data, caches or operator logs."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
DESTINATION=ROOT.parent/"BlueNexus_Unified_GitHub.zip"
SKIP={"__pycache__",".pytest_cache",".venv",".git",".review","outputs"}

def build():
    with ZipFile(DESTINATION,"w",ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            relative=path.relative_to(ROOT)
            if not path.is_file() or any(part in SKIP for part in relative.parts):
                continue
            if path.suffix in {".csv",".parquet",".zip",".pyc"} or path.name in {".env","secrets.toml"}:
                continue
            if path.name.endswith(("_work_log.json","_handoff.md")):
                continue
            archive.write(path,relative.as_posix())
    with ZipFile(DESTINATION) as archive:
        names=set(archive.namelist())
        assert {"app.py","requirements.txt",".streamlit/config.toml","static/fonts/Montserrat-Variable.ttf"} <= names
        assert not any(name.endswith(".csv") for name in names)
        assert archive.testzip() is None
    print(DESTINATION)
    print(f"{len(names)} files; {DESTINATION.stat().st_size:,} bytes; no plant CSVs")

if __name__=="__main__":
    build()
