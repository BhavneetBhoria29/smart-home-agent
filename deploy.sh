#!/usr/bin/env bash
# Build, push and deploy the Smart Home Agent to GKE Autopilot.
# Run from the repo root after `terraform apply` in ./terraform.
set -euo pipefail

cd "$(dirname "$0")"
TF="terraform -chdir=terraform"

export PROJECT_ID=$(gcloud config get-value project)
export REGION=${REGION:-europe-west3}
REPO=$($TF output -raw image_repo)
CLUSTER=$($TF output -raw cluster_name)
export GSA_EMAIL=$($TF output -raw gcp_service_account)
TAG=$(git rev-parse --short HEAD 2>/dev/null || date +%s)
export IMAGE="$REPO/smart-home-agent:$TAG"

echo ">> Building $IMAGE with Cloud Build (amd64, no local Docker needed)"
gcloud builds submit --tag "$IMAGE" .

echo ">> Fetching cluster credentials"
gcloud container clusters get-credentials "$CLUSTER" --region "$REGION"

echo ">> Applying manifests"
envsubst < k8s/deployment.yaml | kubectl apply -f -
kubectl -n smart-home rollout status deploy/smart-home-agent --timeout=600s

echo ">> Waiting for external IP (1-3 min)"
for i in {1..40}; do
  IP=$(kubectl -n smart-home get svc smart-home-agent -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
  [ -n "$IP" ] && break
  sleep 6
done
echo ">> Live at: http://${IP:-<pending, run: kubectl -n smart-home get svc>}"
