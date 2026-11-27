#!/usr/bin/env python3
"""Download DB-IP's free IP-to-Country Lite database at image build time."""

import datetime
import gzip
import os
import shutil
import sys
import urllib.error
import urllib.request

URL = "https://download.db-ip.com/free/dbip-country-lite-{y}-{m:02d}.mmdb.gz"


def months(today: datetime.date):
    yield today.year, today.month
    prev = today.replace(day=1) - datetime.timedelta(days=1)
    yield prev.year, prev.month


def download(target: str) -> None:
    for y, m in months(datetime.datetime.now(datetime.timezone.utc).date()):
        try:
            with urllib.request.urlopen(URL.format(y=y, m=m), timeout=120) as resp, \
                    gzip.GzipFile(fileobj=resp) as gz, open(target, "wb") as out:
                shutil.copyfileobj(gz, out)
            return
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
    raise SystemExit("DB-IP database not found for current or previous month")


def main() -> None:
    target = sys.argv[1]
    os.makedirs(os.path.dirname(target), exist_ok=True)
    download(target)
    import maxminddb

    with maxminddb.open_database(target) as reader:
        record = reader.get("8.8.8.8")
        if not record or not record.get("country", {}).get("iso_code"):
            raise SystemExit("Downloaded GeoIP database does not resolve 8.8.8.8")
    os.chmod(target, 0o644)
    os.chmod(os.path.dirname(target), 0o755)


if __name__ == "__main__":
    main()
