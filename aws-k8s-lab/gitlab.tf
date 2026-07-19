# ============================================
# gitlab.tf — Box1: GitLab self-hosted (Phase 2)
# ============================================

resource "aws_instance" "gitlab" {
  ami                    = data.aws_ami.ubuntu.id      # tái dùng Ubuntu 22.04
  instance_type          = "m7i-flex.large"            # 8GB, free-tier eligible
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.k8s.id] # chung SG -> nội bộ tự thông
  key_name               = aws_key_pair.lab.key_name

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
  }

  tags = { Name = "gitlab" }
}

# Mở 80 cho GitLab (443 đã mở sẵn từ rule harbor_https)
resource "aws_vpc_security_group_ingress_rule" "gitlab_http" {
  security_group_id = aws_security_group.k8s.id
  cidr_ipv4         = "0.0.0.0/0"   # lab; thực tế nên giới hạn IP
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  description       = "GitLab HTTP"
}