# Brightify — AWS infrastructure (Terraform)

Provisions a single-EC2 Brightify deployment with audio offloaded to S3 + CloudFront.

## What it creates
- **VPC** + public subnet + IGW + security group (80/443 public, 22 restricted/off).
- **EC2** `t3.medium` (Ubuntu 22.04, amd64) with an Elastic IP and a 50GB gp3 root volume. Cloud-init installs Docker + AWS CLI.
- **S3** bucket (private) for the 17GB MP3s + **CloudFront** (OAC, Range, CORS) in front of it.
- **ECR** repository for the app image.
- **IAM**: EC2 instance role (ECR pull, S3 r/w, SSM) + GitHub Actions OIDC deploy role.

## Usage
```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # edit github_repo, ssh_allowed_cidr, etc.
terraform init
terraform plan
terraform apply
terraform output           # app_public_ip, cloudfront_domain, ecr_repository_url, github_deploy_role_arn
```

## After apply (Phase 2 — data load)
1. Upload MP3s: `make audio-manifest && aws s3 sync music_files/ s3://$(terraform output -raw audio_bucket)/ --content-type audio/mpeg`
2. SSH/SSM into the box, clone the repo to `/opt/brightify`, build a **data-only** serving release: `PYTHONPATH=. python tools/build_serving_release.py --no-music --copy` and point `SERVING_RELEASES_PATH` at it.
3. Fill `.env` (`APP_IMAGE`, `AUDIO_CDN_BASE=https://$(terraform output -raw cloudfront_domain)`, `POSTGRES_*`, `ALLOWED_ORIGINS`).
4. `make aws` → migrate + `make seed` → `make verify`.

## GitHub Actions secrets to set (repo settings)
- `AWS_DEPLOY_ROLE_ARN` = `terraform output -raw github_deploy_role_arn`
- `AWS_REGION`, `ECR_REPOSITORY_URL`, `EC2_INSTANCE_ID` (from outputs)

## Notes
- The `$100` credit lasts ~3 months at `t3.medium`. Drop to `t3.small` to stretch it.
- CloudFront free tier covers 1TB egress for 12 months; watch egress after that.
- State is local (`*.tfstate` gitignored). For a team, move it to an S3 backend.
