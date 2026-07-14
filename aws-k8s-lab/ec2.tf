# ============================================
# ec2.tf — 3 máy EC2 cho cụm K8s
# ============================================

# 1. Tìm AMI Ubuntu 22.04 mới nhất (x86_64)
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]   # tài khoản chính thức của Canonical (Ubuntu)

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# 2. Khai báo SSH key để vào máy (dùng public key sẵn trên laptop)
resource "aws_key_pair" "lab" {
  key_name   = "k8s-lab-key"
  public_key = file("~/.ssh/id_ed25519.pub")   # đổi path nếu key bạn tên khác
}

# 3. Control-plane (1 máy, cần khỏe hơn -> c7i-flex.large / 4GB)
resource "aws_instance" "control_plane" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "c7i-flex.large"
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.k8s.id]
  key_name               = aws_key_pair.lab.key_name

  root_block_device {
    volume_size = 20      # GB
    volume_type = "gp3"
  }

  tags = { Name = "k8s-control-plane" }
}

# 4. Worker (2 máy giống nhau -> dùng count để khỏi lặp code)
resource "aws_instance" "worker" {
  count                  = 2
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.small"
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.k8s.id]
  key_name               = aws_key_pair.lab.key_name

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  tags = { Name = "k8s-worker-${count.index + 1}" }   # k8s-worker-1, k8s-worker-2
}

# Role cho EC2 node
resource "aws_iam_role" "node" {
  name = "k8s-lab-node-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Quyền đọc ECR (pull + GetAuthorizationToken)
resource "aws_iam_role_policy_attachment" "node_ecr_ro" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_instance_profile" "node" {
  name = "k8s-lab-node-profile"
  role = aws_iam_role.node.name
}