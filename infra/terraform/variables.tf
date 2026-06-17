variable "aws_region" {
  description = "AWS region (ap-southeast-1 = Singapore, closest to Vietnam)"
  type        = string
  default     = "ap-southeast-1"
}

variable "project" {
  description = "Project/name prefix for all resources"
  type        = string
  default     = "brightify"
}

variable "instance_type" {
  description = "EC2 instance type. t3.medium (4GB) fits the stack after PhoBERT is disabled."
  type        = string
  default     = "t3.medium"
}

variable "root_volume_gb" {
  description = "Root EBS volume size (GB). Holds OS + Docker + DB + data-only serving release (no music — that is in S3)."
  type        = number
  default     = 50
}

variable "key_pair_name" {
  description = "Name of an existing EC2 key pair for SSH. Leave empty to rely solely on SSM Session Manager."
  type        = string
  default     = ""
}

variable "ssh_allowed_cidr" {
  description = "CIDR allowed to SSH (port 22). Restrict to your IP, e.g. 1.2.3.4/32. Empty disables SSH ingress (SSM only)."
  type        = string
  default     = ""
}

variable "github_repo" {
  description = "GitHub repo (owner/name) allowed to assume the CI deploy role via OIDC, e.g. giaduocquach/Brightify"
  type        = string
}

variable "github_branch" {
  description = "Branch allowed to deploy (used in the OIDC trust condition)"
  type        = string
  default     = "main"
}

variable "create_github_oidc_provider" {
  description = "Create the GitHub Actions OIDC provider. Set false if it already exists in the account."
  type        = bool
  default     = true
}

variable "domain_name" {
  description = "Optional domain for the app (TLS via Let's Encrypt on nginx). Empty = use the EC2 public IP."
  type        = string
  default     = ""
}

variable "app_origins" {
  description = "Allowed CORS origins for audio responses from the CDN (the app's public origin). '*' works for crossOrigin=anonymous media."
  type        = string
  default     = "*"
}

variable "enable_cloudfront" {
  description = "Use CloudFront in front of S3 for audio. Set false for new AWS accounts where CloudFront is not yet verified — audio is then served directly from S3 (public-read, HTTPS, Range, CORS). Flip to true + apply once the account is verified."
  type        = bool
  default     = true
}
