# Brightify — AWS Deployment Runbook

Single EC2 (Docker Compose) + S3/CloudFront for audio + ECR + GitHub Actions CI/CD.
All app/infra/CI code is in the repo and verified. The steps below need **your AWS
credentials** and run on **your** machine / AWS account.

Tools are installed: `aws` (v2) and `tofu` (OpenTofu, drop-in for Terraform —
use `tofu` wherever you'd type `terraform`).

---

## 0. One-time prerequisites
```bash
aws configure        # paste your AWS Access Key + Secret (region: ap-southeast-1)
# tofu + aws are already installed.
```

## 1. Provision infrastructure
```bash
cd infra/terraform
# terraform.tfvars is prefilled (github_repo + your IP). Review it.
tofu init
tofu plan        # review what will be created
tofu apply       # type yes — creates VPC, EC2, S3, CloudFront, ECR, IAM (~few min; CloudFront ~15min)
tofu output      # note: app_public_ip, cloudfront_domain, ecr_repository_url, instance_id, github_deploy_role_arn, audio_bucket
```

## 2. Set GitHub Actions secrets
Repo → Settings → Secrets and variables → Actions → New repository secret (4):

| Secret | Value (from `tofu output`) |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `github_deploy_role_arn` |
| `AWS_REGION` | `ap-southeast-1` |
| `ECR_REPOSITORY_URL` | `ecr_repository_url` |
| `EC2_INSTANCE_ID` | `instance_id` |

(Or with the GitHub CLI: `gh auth login` then
`gh secret set AWS_DEPLOY_ROLE_ARN -b "$(cd infra/terraform && tofu output -raw github_deploy_role_arn)"`, etc.)

## 3. Upload data (one-time) — from your laptop
`data/` (embeddings/CSV) and `music_files/` are gitignored, so they are NOT in git.
This script builds the data-only serving release, uploads the 17GB MP3s to S3, and
rsyncs the release to EC2:
```bash
BUCKET=$(cd infra/terraform && tofu output -raw audio_bucket)
IP=$(cd infra/terraform && tofu output -raw app_public_ip)
scripts/aws-sync-data.sh "$BUCKET" "$IP"      # ssh_user defaults to ubuntu
```

## 4. First deploy
On the EC2 host (`ssh ubuntu@$IP`), get the repo + .env ready:
```bash
sudo mkdir -p /opt/brightify && sudo chown ubuntu:ubuntu /opt/brightify
git clone https://github.com/giaduocquach/Brightify.git /opt/brightify
cd /opt/brightify && git checkout main          # or your deploy branch
cp .env.example .env
# Edit .env: POSTGRES_USER/PASSWORD/DB, ALLOWED_ORIGINS (your domain/IP),
#   AUDIO_CDN_BASE=https://<cloudfront_domain>, APP_IMAGE=<ecr_url>:latest, SKIP_PHOBERT_LOAD=True
```

The app image must exist in ECR. Two ways:
- **Via CI (recommended):** merge your branch to `main` and push → `deploy.yml` builds + pushes the image and runs the deploy over SSM automatically.
- **Manual one-time build/push** (if you want to bring it up before wiring CI):
  ```bash
  aws ecr get-login-password --region ap-southeast-1 | docker login --username AWS --password-stdin <ecr_url%/*>
  docker build -t <ecr_url>:latest .          # build on a machine with Docker
  docker push <ecr_url>:latest
  ```

Then on EC2:
```bash
cd /opt/brightify && scripts/aws-bootstrap.sh   # init + pull + up + migrate + seed + verify
```

## 5. Domain + HTTPS (optional, recommended for public)
- No domain yet? Use a free **DuckDNS** subdomain, or buy one (~$10/yr).
- Point an **A record** → `app_public_ip`.
- Enable the HTTPS block in `nginx/conf.d.aws/brightify.conf`, then on EC2:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.aws.yml run --rm \
    --entrypoint "certbot certonly --webroot -w /var/www/certbot -d <domain>" nginx
  ```
  (CloudFront audio already has HTTPS via its `*.cloudfront.net` domain.)

---

## What needs YOU (cannot be automated for you)
1. **AWS credentials** (`aws configure`) — billable account, $100 credit.
2. **`tofu apply`** — creates real (billable ~$35/mo) resources.
3. **4 GitHub secrets** (step 2).
4. **Merge to `main`** to trigger the CI deploy (or set `github_branch` in tfvars + use “Run workflow”).

## Notes / risks
- $100 credit ≈ 2.8 months at t3.medium. Compose is portable → migrate to Oracle Always Free ($0) later if needed.
- CloudFront free tier covers 1TB egress for 12 months; watch egress after.
- Serving 17GB of Vietnamese music publicly carries copyright risk — your call.
- Tear down everything: `cd infra/terraform && tofu destroy`.
