# Auto-generate an EC2 SSH key pair when key_pair_name is empty, and write the
# private key to disk locally (gitignored). Lets rsync/SSH to the box work out of
# the box. Provide key_pair_name to use an existing pair instead.
resource "tls_private_key" "ec2" {
  count     = var.key_pair_name == "" ? 1 : 0
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "ec2" {
  count      = var.key_pair_name == "" ? 1 : 0
  key_name   = "${var.project}-key"
  public_key = tls_private_key.ec2[0].public_key_openssh
}

resource "local_sensitive_file" "ec2_pem" {
  count           = var.key_pair_name == "" ? 1 : 0
  content         = tls_private_key.ec2[0].private_key_pem
  filename        = "${path.module}/${var.project}-ec2.pem"
  file_permission = "0600"
}

locals {
  ec2_key_name = var.key_pair_name != "" ? var.key_pair_name : aws_key_pair.ec2[0].key_name
  ec2_key_file = var.key_pair_name != "" ? "" : local_sensitive_file.ec2_pem[0].filename
}
