resource "aws_ecr_repository" "flask_hello" {
  name                 = "flask-hello"
  image_tag_mutability = "IMMUTABLE"   # 1 tag = 1 image, không ghi đè
  force_delete         = true          # cho destroy dù còn image (lab)

  image_scanning_configuration {
    scan_on_push = true                # tự quét lỗ hổng khi push
  }

  tags = {
    Project = "k8s-lab"
  }
}

output "ecr_repo_url" {
  value = aws_ecr_repository.flask_hello.repository_url
}