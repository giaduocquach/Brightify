# Latest Canonical Ubuntu 22.04 LTS (amd64) — matches the existing amd64 Dockerfile.
data "aws_ssm_parameter" "ubuntu" {
  name = "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id"
}

resource "aws_instance" "app" {
  ami                    = data.aws_ssm_parameter.ubuntu.value
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name
  key_name               = local.ec2_key_name

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_gb
    encrypted   = true
  }

  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    project      = var.project
    aws_region   = var.aws_region
    ecr_repo_url = aws_ecr_repository.app.repository_url
    audio_bucket = aws_s3_bucket.audio.id
    cdn_domain   = aws_cloudfront_distribution.audio.domain_name
  })

  # Re-run user_data only when its content changes.
  user_data_replace_on_change = true

  tags = { Name = "${var.project}-app" }
}

resource "aws_eip" "app" {
  instance = aws_instance.app.id
  domain   = "vpc"
  tags     = { Name = "${var.project}-eip" }
}
