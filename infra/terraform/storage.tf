resource "random_id" "suffix" {
  byte_length = 4
}

# ---------------------------------------------------------------------------
# ECR — holds the prebuilt app image pushed by CI
# ---------------------------------------------------------------------------
resource "aws_ecr_repository" "app" {
  name                 = var.project
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Keep only recent images to avoid ECR storage creep.
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

# ---------------------------------------------------------------------------
# S3 — 17GB MP3 catalog (private; served only through CloudFront via OAC)
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "audio" {
  bucket = "${var.project}-audio-${random_id.suffix.hex}"
}

resource "aws_s3_bucket_public_access_block" "audio" {
  bucket                  = aws_s3_bucket.audio.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CORS so the browser's crossOrigin="anonymous" audio (Web Audio crossfade)
# is not tainted. CloudFront also re-applies CORS via the response headers policy.
resource "aws_s3_bucket_cors_configuration" "audio" {
  bucket = aws_s3_bucket.audio.id
  cors_rule {
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = [var.app_origins]
    allowed_headers = ["*"]
    expose_headers  = ["Content-Length", "Content-Range", "Accept-Ranges"]
    max_age_seconds = 3000
  }
}

resource "aws_cloudfront_origin_access_control" "audio" {
  name                              = "${var.project}-audio-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "audio" {
  enabled         = true
  comment         = "${var.project} audio CDN"
  price_class     = "PriceClass_200" # includes SE Asia; cheaper than All
  http_version    = "http2and3"
  is_ipv6_enabled = true

  origin {
    domain_name              = aws_s3_bucket.audio.bucket_regional_domain_name
    origin_id                = "s3-audio"
    origin_access_control_id = aws_cloudfront_origin_access_control.audio.id
  }

  default_cache_behavior {
    target_origin_id       = "s3-audio"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = false # MP3 already compressed

    # Managed "CachingOptimized" — forwards Range, long TTL, good for static media.
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
    # Managed "CORS-and-SecurityHeaders" so audio responses carry Access-Control-Allow-Origin.
    response_headers_policy_id = "e61eb60c-9c35-4d20-a928-2b84e02af89c"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# Allow only this CloudFront distribution to read the bucket.
data "aws_iam_policy_document" "audio_s3" {
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.audio.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.audio.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "audio" {
  bucket = aws_s3_bucket.audio.id
  policy = data.aws_iam_policy_document.audio_s3.json
}
