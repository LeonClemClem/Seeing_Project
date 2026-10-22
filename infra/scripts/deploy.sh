#!/usr/bin/env bash
# Build (Cloud Build) and roll out images to one environment.
#
#   infra/scripts/deploy.sh <dev|prod> <web|batch|all> [tag]
#
# - Without a tag: tag = git short SHA of HEAD (plus -dirty-<timestamp> if the tree is dirty);
#   the image is built only if that tag is not already in Artifact Registry, so deploying the
#   same commit to prod after dev reuses the dev image.
# - With a tag: deploys that existing image (rollback / promotion); never builds.
# - web: build web image -> update + execute seeing-migrate-<env> -> deploy seeing-web-<env>
#   -> update seeing-create-user-<env>.
# - batch: build batch image -> update seeing-batch-<env> (next scheduled run uses it).
set -euo pipefail

PROJECT="${PROJECT:-project-astrarome}"
REGION="${REGION:-us-central1}"
REPO="${REGION}-docker.pkg.dev/${PROJECT}/seeing"
BUILD_SA="projects/${PROJECT}/serviceAccounts/seeing-build@${PROJECT}.iam.gserviceaccount.com"
STAGING="gs://${PROJECT}-cloudbuild-src/source"

usage() {
  echo "usage: $0 <dev|prod> <web|batch|all> [tag]" >&2
  exit 2
}

[[ $# -ge 2 && $# -le 3 ]] || usage
ENV="$1"
TARGET="$2"
TAG="${3:-}"
[[ "$ENV" == dev || "$ENV" == prod ]] || usage
[[ "$TARGET" == web || "$TARGET" == batch || "$TARGET" == all ]] || usage

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

EXPLICIT_TAG=false
if [[ -n "$TAG" ]]; then
  EXPLICIT_TAG=true
else
  TAG="$(git rev-parse --short=7 HEAD)"
  if [[ -n "$(git status --porcelain)" ]]; then
    TAG="${TAG}-dirty-$(date -u +%Y%m%d%H%M%S)"
    echo "warning: working tree is dirty, building ${TAG}" >&2
  fi
fi

gc() { gcloud --project="$PROJECT" --quiet "$@"; }

image_exists() {
  gc artifacts docker images describe "$1" >/dev/null 2>&1
}

# ensure_image <name> <dockerfile>: make sure $REPO/<name>:$TAG exists, building it if allowed.
ensure_image() {
  local image="${REPO}/$1"
  if image_exists "${image}:${TAG}"; then
    echo "==> ${image}:${TAG} already exists, not rebuilding"
    return
  fi
  if [[ "$EXPLICIT_TAG" == true ]]; then
    echo "error: ${image}:${TAG} not found in Artifact Registry" >&2
    exit 1
  fi
  echo "==> building ${image}:${TAG} from $2"
  gc builds submit . \
    --region="$REGION" \
    --config=cloudbuild.yaml \
    --ignore-file=infra/scripts/build.gcloudignore \
    --service-account="$BUILD_SA" \
    --gcs-source-staging-dir="$STAGING" \
    --substitutions="_IMAGE=${image},_TAG=${TAG},_DOCKERFILE=$2"
}

deploy_web() {
  local image="${REPO}/web:${TAG}"
  ensure_image web apps/api/Dockerfile

  echo "==> migrating seeing_${ENV} with ${image}"
  gc run jobs update "seeing-migrate-${ENV}" --region="$REGION" --image="$image"
  gc run jobs execute "seeing-migrate-${ENV}" --region="$REGION" --wait

  echo "==> deploying seeing-web-${ENV}"
  gc run deploy "seeing-web-${ENV}" --region="$REGION" --image="$image"

  # Same image: the account-administration job must run the same code and migrations.
  echo "==> updating seeing-create-user-${ENV}"
  gc run jobs update "seeing-create-user-${ENV}" --region="$REGION" --image="$image"
}

deploy_batch() {
  local image="${REPO}/batch:${TAG}"
  ensure_image batch apps/batch/Dockerfile

  echo "==> updating seeing-batch-${ENV}"
  gc run jobs update "seeing-batch-${ENV}" --region="$REGION" --image="$image"
}

case "$TARGET" in
  web) deploy_web ;;
  batch) deploy_batch ;;
  all)
    deploy_web
    deploy_batch
    ;;
esac

echo "==> done: ${ENV} ${TARGET} @ ${TAG}"
if [[ "$TARGET" != web ]]; then
  echo "    run the batch now with: gcloud run jobs execute seeing-batch-${ENV} --region=${REGION} --project=${PROJECT} --wait"
fi
