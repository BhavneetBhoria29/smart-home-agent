# Smart Home Agent on GKE (Terraform)

Google ADK + Gemini agent, containerised and deployed to GKE Autopilot.
Infra is Terraform; Gemini is called through Vertex AI using Workload Identity,
so there is no API key anywhere in the cluster.

```
terraform/   Artifact Registry, GKE Autopilot cluster, runtime service account, IAM
k8s/         Namespace, K8s service account, Deployment, LoadBalancer Service
deploy.sh    Cloud Build -> push -> kubectl apply -> prints the public URL
```

## Put these files in your repo root

```
your-repo/
  smart_home_agent/      # __init__.py imports agent; agent.py defines root_agent
  requirements.txt       # must include google-adk
  Dockerfile  .dockerignore  deploy.sh  terraform/  k8s/
```

## One-time setup

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

Billing must be enabled on the project. Tools needed: gcloud, terraform, kubectl
(`gcloud components install kubectl gke-gcloud-auth-plugin`), envsubst
(Mac: `brew install gettext`).

## Deploy

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # set project_id
terraform init
terraform apply                                # ~8-10 min, mostly the cluster
cd ..
./deploy.sh                                    # prints http://<EXTERNAL_IP>
```

Open the IP and pick `smart_home_agent` in the ADK dev UI.

## Test locally first (saves debugging time on the cluster)

```bash
docker build -t sha . && docker run -p 8080:8080 \
  -e GOOGLE_API_KEY=your_key sha
```

## Tear down when you're done demoing

```bash
kubectl delete ns smart-home        # removes the load balancer first
cd terraform && terraform destroy
```

## Troubleshooting

- `ImagePullBackOff`: check `terraform apply` finished (it grants the node pull role).
- `403 aiplatform` / permission errors in logs: `kubectl -n smart-home logs deploy/smart-home-agent`,
  then confirm the Vertex AI API is enabled and the KSA annotation matches `gcp_service_account`.
- Catalogue file not found: the JSONs must be inside the image (see the COPY comment in the Dockerfile)
  and the tools must build paths relative to the package, not your laptop.
- Model not found: set `GOOGLE_CLOUD_LOCATION` in k8s/deployment.yaml to a region that serves your
  Gemini model (europe-west1/west4 or us-central1 are safe bets).
