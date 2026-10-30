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

## Checking for vulnerabilities

To check the locked packages for known vulnerabilities (CI also runs this):

```bash
pip-audit --strict --disable-pip -r requirements-dev.txt
```

## Deployment

The app runs on AWS Lambda (`us-east-2`) at
https://st5ymlzzn3ahurkxqqepfuv5pm0blzqs.lambda-url.us-east-2.on.aws/

Every merge to `main` runs CI. Once all checks pass, the `deploy` job pushes the tested image
to Amazon ECR, tagged with the commit SHA, updates the `multi-clip` Lambda function to that
image, and checks that `/health` answers on the live site.

To roll back, choose **Deploy new image** on the function's page in the Lambda console and
pick the previous image tag, or revert the commit on `main` so the pipeline redeploys it.

- CI signs in to AWS as the IAM user `github-actions-multi-clip`. Its permissions are in
  `aws/github-deploy-policy.json`; keep that file in sync with the user's inline policy.
- The user's access key is stored only as secrets in the GitHub environment `production`,
  which only `main` can use.
- **Rotate the key every few months:** create a new access key in IAM, update the
  `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment secrets, then delete the old key.
  If you suspect a leak, deactivate the key in IAM immediately.
