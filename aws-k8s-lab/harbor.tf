# ============================================
# harbor.tf — Box2: Harbor registry (Phase 1 on-prem lab)
# ============================================

resource "aws_instance" "harbor" {
  ami                    = data.aws_ami.ubuntu.id     # tái dùng data source Ubuntu 22.04
  instance_type          = "c7i-flex.large"           # 4GB, free-tier eligible cho account
  subnet_id              = aws_subnet.public.id        # cùng subnet 10.10.1.0/24
  vpc_security_group_ids = [aws_security_group.k8s.id] # CHUNG SG -> node<->harbor tự thông
  key_name               = aws_key_pair.lab.key_name

  root_block_device {
    volume_size = 40     # registry cần dung lượng hơn node
    volume_type = "gp3"
  }

  tags = { Name = "harbor" }
}

# Mở 443 để laptop vào UI + push image (node<->harbor đã có internal_all lo)
resource "aws_vpc_security_group_ingress_rule" "harbor_https" {
  security_group_id = aws_security_group.k8s.id
  cidr_ipv4         = "0.0.0.0/0"   # lab; thực tế nên giới hạn IP của bạn
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  description       = "Harbor HTTPS / registry"
}