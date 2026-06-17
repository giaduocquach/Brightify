output "app_public_ip" {
  description = "Elastic IP of the app server. Point your DNS A record here."
  value       = aws_eip.app.public_ip
}

output "instance_id" {
  description = "EC2 instance id (used by the CI deploy via SSM)."
  value       = aws_instance.app.id
}

output "cloudfront_domain" {
  description = "Audio CDN domain (empty when CloudFront is disabled)."
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.audio[0].domain_name : ""
}

output "audio_base_url" {
  description = "Base URL for audio. Set AUDIO_CDN_BASE to this in the app .env."
  value       = local.audio_base_url
}

output "audio_bucket" {
  description = "S3 bucket for MP3s. Upload with: aws s3 sync music_files/ s3://<bucket>/ --content-type audio/mpeg"
  value       = aws_s3_bucket.audio.id
}

output "ecr_repository_url" {
  description = "ECR repo URL. APP_IMAGE=<this>:<tag>"
  value       = aws_ecr_repository.app.repository_url
}

output "github_deploy_role_arn" {
  description = "Role ARN for GitHub Actions (set as AWS_DEPLOY_ROLE_ARN secret)."
  value       = aws_iam_role.github_deploy.arn
}

output "ssh_key_file" {
  description = "Path to the generated private key (empty if you supplied key_pair_name)."
  value       = local.ec2_key_file
}

output "ssh_command" {
  description = "Ready-to-use SSH command."
  value       = local.ec2_key_file != "" ? "ssh -i ${local.ec2_key_file} ubuntu@${aws_eip.app.public_ip}" : "ssh ubuntu@${aws_eip.app.public_ip}"
}
