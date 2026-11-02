# multi-clip
multi clipboard app

This application is an on-screen hidable multi clipboard that accepts images, text, and video.

The current version is a web app that saves text and image clips. On AWS, clips are kept in DynamoDB and images in S3; running locally, text clips are kept in memory and image clips are switched off.

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

## Lambda adapter mirror

The Dockerfile pulls the AWS Lambda Web Adapter from a public copy at
`ghcr.io/blaine-c-wilson/aws-lambda-adapter`, because `public.ecr.aws` often rate-limits CI
(issue #15). Dependabot doesn't watch the copy, so to upgrade the adapter, mirror the new
version from a Mac with Docker running:

1. Create a classic personal access token with `write:packages` and a short expiry.
2. Sign in, copy the image, and check that its digest matches the original:
   ```bash
   docker login ghcr.io -u blaine-c-wilson
   docker buildx imagetools create --tag ghcr.io/blaine-c-wilson/aws-lambda-adapter:<version> \
     public.ecr.aws/awsguru/aws-lambda-adapter:<version>@sha256:<digest>
   docker buildx imagetools inspect ghcr.io/blaine-c-wilson/aws-lambda-adapter:<version>
   docker logout ghcr.io
   ```
3. Delete the token, then update the `FROM` line in the Dockerfile to the new tag and digest.

## Deployment

The app runs on AWS Lambda (`us-east-2`) at
https://st5ymlzzn3ahurkxqqepfuv5pm0blzqs.lambda-url.us-east-2.on.aws/

Every merge to `main` runs CI. Once all checks pass, the `deploy` job pushes the tested image
to Amazon ECR, tagged with the commit SHA, updates the `multi-clip` Lambda function to that
image, and checks that `/health` answers on the live site.

To roll back, choose **Deploy new image** on the function's page in the Lambda console and
pick the previous image tag, or revert the commit on `main` so the pipeline redeploys it.

Clips are stored in the DynamoDB table `multi-clip-clips` (partition key `owner`, sort key
`id`, both strings; provisioned 5/5 capacity; deletion protection on). The Lambda function
finds it through its `CLIPS_TABLE` environment variable. Without that variable, as when
running locally, clips are kept in memory instead. The function runs as the IAM role
`multi-clip-lambda`: `AWSLambdaBasicExecutionRole` for logs, plus the inline policy in
`aws/lambda-dynamodb-policy.json` for the table only.

Image files are in the S3 bucket `multi-clip-images-433490647961`, under `images/`, found
through the function's `IMAGES_BUCKET` environment variable. Browsers upload to it directly
with a signed form (PNG, JPEG, GIF or WebP, up to 5 MB) and view images through short-lived
signed links, so the bucket stays private (Block Public Access on). Its CORS rules, which let
the live site's pages talk to it, are in `aws/images-bucket-cors.json`. The app has no login, so
images don't stay forever: image clips get an `expires_at` time 7 days ahead, which the table's
time-to-live setting uses to delete them, and a bucket lifecycle rule deletes files under
`images/` after 8 days. The role's inline policy `multi-clip-images`
(`aws/lambda-images-policy.json`) allows only that bucket. Without `IMAGES_BUCKET`, as when
running locally, image clips are switched off.

- CI signs in to AWS as the IAM user `github-actions-multi-clip`. Its permissions are in
  `aws/github-deploy-policy.json`; keep that file in sync with the user's inline policy.
- The user's access key is stored only as secrets in the GitHub environment `production`,
  which only `main` can use.
- **Rotate the key every few months:** create a new access key in IAM, update the
  `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment secrets, then delete the old key.
  If you suspect a leak, deactivate the key in IAM immediately.
