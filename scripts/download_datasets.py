"""Download the real public bug datasets into data/raw/.

Uses the Kaggle CLI (`pip install kaggle`, then put kaggle.json in ~/.kaggle/).
This is optional — the repo ships a bundled sample so nothing here is required
to run the prototype. Run this when you want to scale the KB to the full
public datasets.

    python scripts/download_datasets.py            # show instructions
    python scripts/download_datasets.py --run      # actually download (needs kaggle CLI)

After downloading, point the KB builder at the folder:
    python -m src.ingestion.build_kb --data-dir data/raw --reset
(the builder expects files named eclipse_bugs.csv / mozilla_bugs.csv /
apache_issues.csv; rename/convert the downloaded CSVs accordingly).
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"

# Kaggle dataset slugs (Eclipse/Mozilla defect tracking + Apache JIRA issues).
DATASETS = {
    "eclipse_mozilla": "ansymo/msr2013-bug-dataset",     # MSR 2013 Eclipse & Mozilla defect tracking
    "apache_jira": "tedlozzo/apaches-jira-issues",        # Apache issues exported from JIRA
}

# Non-Kaggle canonical mirrors, for reference / manual download.
MIRRORS = {
    "eclipse_mozilla_github": "https://github.com/ansymo/msr2013-bug_dataset",
    "eclipse_mozilla_paper": "https://doi.org/10.1109/MSR.2013.6624028",
    "apache_jira_zenodo": "https://zenodo.org/records/5665896",
}


def instructions() -> None:
    print(__doc__)
    print("Kaggle slugs:")
    for name, slug in DATASETS.items():
        print(f"  {name:20s} kaggle datasets download -d {slug} -p {RAW} --unzip")
    print("\nCanonical mirrors (manual):")
    for name, url in MIRRORS.items():
        print(f"  {name:26s} {url}")


def run() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, slug in DATASETS.items():
        print(f"\n>>> downloading {name} ({slug}) ...")
        try:
            subprocess.run(
                ["kaggle", "datasets", "download", "-d", slug, "-p", str(RAW), "--unzip"],
                check=True,
            )
        except FileNotFoundError:
            print("  kaggle CLI not found. Install with `pip install kaggle` and add ~/.kaggle/kaggle.json.")
            return
        except subprocess.CalledProcessError as e:
            print(f"  download failed ({e}). You may need to accept the dataset's terms on kaggle.com first.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="Actually download via the Kaggle CLI.")
    args = ap.parse_args()
    run() if args.run else instructions()
