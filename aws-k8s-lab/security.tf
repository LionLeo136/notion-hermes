# ============================================
# security.tf — Security Group cho cụm K8s
# ============================================

resource "aws_security_group" "k8s" {
  name        = "k8s-lab-sg"
  description = "Security group cho lab Kubernetes"
  vpc_id      = aws_vpc.main.id

  tags = { Name = "k8s-lab-sg" }
}

# --- 1. Cho phép MỌI traffic GIỮA CÁC NODE trong cùng SG ---
# Đây là rule quan trọng nhất: node ↔ node (api-server, etcd,
# kubelet, CNI/pod-to-pod...) đều thông, khỏi liệt kê từng port.
resource "aws_vpc_security_group_ingress_rule" "internal_all" {
  security_group_id            = aws_security_group.k8s.id
  referenced_security_group_id = aws_security_group.k8s.id  # tự tham chiếu chính nó
  ip_protocol                  = "-1"                        # -1 = mọi protocol/port
  description                  = "Cho phep tat ca traffic noi bo giua cac node"
}

# --- 2. SSH (22) để bạn vào máy ---
resource "aws_vpc_security_group_ingress_rule" "ssh" {
  security_group_id = aws_security_group.k8s.id
  cidr_ipv4         = "0.0.0.0/0"   # lab: mở rộng; thực tế nên giới hạn IP của bạn
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  description       = "SSH"
}

# --- 3. API server (6443) để kubectl từ laptop gọi vào ---
resource "aws_vpc_security_group_ingress_rule" "apiserver" {
  security_group_id = aws_security_group.k8s.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 6443
  to_port           = 6443
  description       = "Kubernetes API server"
}

# --- 4. NodePort (30000-32767) để truy cập Service kiểu NodePort ---
resource "aws_vpc_security_group_ingress_rule" "nodeport" {
  security_group_id = aws_security_group.k8s.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 30000
  to_port           = 32767
  description       = "NodePort services"
}

# --- 5. Egress: cho ra ngoài tất cả (tải image, apt...) ---
resource "aws_vpc_security_group_egress_rule" "all_out" {
  security_group_id = aws_security_group.k8s.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "Cho phep tat ca traffic ra ngoai"
}