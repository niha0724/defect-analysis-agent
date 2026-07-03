"""Download the real public bug datasets into data/raw/.

Sources
-------
* **Apache** — Kaggle ``tedlozzo/apaches-jira-issues`` (``issues.csv``, ~1.9 GB).
  Needs a free Kaggle token: ``pip install kaggle`` and put ``kaggle.json`` in
  ``~/.kaggle/`` (or set ``KAGGLE_USERNAME`` / ``KAGGLE_KEY``).
* **Eclipse + Mozilla** — the Eclipse & Mozilla Defect Tracking Dataset
  (Lamkanfi et al., MSR 2013) from the public GitHub mirror — no auth needed.
  ``eclipse.tar.gz`` + ``mozilla.tar.gz`` are extracted to ``data/raw/msr2013/``.

Usage
-----
    python scripts/download_datasets.py            # show instructions
    python scripts/download_datasets.py --run      # download + extract everything

Then build the KB from the real data:
    python scripts/build_real_kb.py --reset --limit 3000
"""
from __future__ import annotations

import argparse
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
MSR = RAW / "msr2013"
APACHE_SLUG = "tedlozzo/apaches-jira-issues"
MSR_BASE = "https://raw.githubusercontent.com/ansymo/msr2013-bug_dataset/master/data"


def download_apache() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    if (RAW / "issues.csv").exists():
        print(">>> Apache issues.csv already present, skipping.")
        return
    print(f">>> Apache issues.csv via Kaggle ({APACHE_SLUG}) — this is ~1.9 GB ...")
    try:
        subprocess.run(
            ["kaggle", "datasets", "download", "-d", APACHE_SLUG, "-f", "issues.csv", "-p", str(RAW)],
            check=True,
        )
    except FileNotFoundError:
        print("  kaggle CLI not found. Run: pip install kaggle  (and add ~/.kaggle/kaggle.json)")
        return
    except subprocess.CalledProcessError as e:
        print(f"  download failed ({e}). Accept the dataset terms on kaggle.com first if needed.")
        return
    zip_path = RAW / "issues.csv.zip"
    if zip_path.exists():
        print("  unzipping ...")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(RAW)
        zip_path.unlink()


def download_msr2013() -> None:
    MSR.mkdir(parents=True, exist_ok=True)
    for name in ("eclipse.tar.gz", "mozilla.tar.gz"):
        product_dir = MSR / name.split(".")[0]
        if product_dir.exists():
            print(f">>> MSR2013 {name} already extracted, skipping.")
            continue
        dest = MSR / name
        print(f">>> MSR2013 {name} from GitHub mirror ...")
        urllib.request.urlretrieve(f"{MSR_BASE}/{name}", dest)
        with tarfile.open(dest) as tf:
            try:
                tf.extractall(MSR, filter="data")   # py>=3.12 safe extraction
            except TypeError:
                tf.extractall(MSR)
        print(f"  extracted -> {product_dir}/")


def instructions() -> None:
    print(__doc__)


def run() -> None:
    download_apache()
    download_msr2013()
    print("\nDone. Next:  python scripts/build_real_kb.py --reset --limit 3000")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="Actually download + extract.")
    args = ap.parse_args()
    run() if args.run else instructions()
