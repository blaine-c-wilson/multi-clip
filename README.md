# multi-clip
multi clipboard app

This application is an on-screen hidable multi clipboard that accepts images, text, and video.

The current version is a web app that saves text clips. Clips are kept in memory, so they are lost when the app restarts.

## Running locally

Requires Python 3.12 or newer.

```bash
python3 -m venv .venv                     # create an isolated environment (once)
source .venv/bin/activate                 # activate it (each new terminal)
pip install -r requirements-dev.txt       # install dependencies
uvicorn app.main:app --reload             # start the app
```

Then open http://127.0.0.1:8000. Interactive API docs are at http://127.0.0.1:8000/docs.

## Running the tests

```bash
pytest
```

## Dependencies

Direct dependencies are listed in `requirements.in` (app) and `requirements-dev.in` (testing tools).
The `.txt` files are generated lock files that pin every package, including indirect ones, to an exact version and hash.
Don't edit the `.txt` files by hand; edit the `.in` files and regenerate.

Only releases at least 14 days old are locked (a "cooldown"), because malicious package
releases are usually caught and pulled within days. The exception is a release that fixes a
known vulnerability; those are listed in `scripts/lock.sh`. Pass the date 14 days ago:

```bash
pip install uv
scripts/lock.sh 2026-10-16
```

To check the locked packages for known vulnerabilities (CI also runs this):

```bash
pip-audit --strict --disable-pip -r requirements-dev.txt
```