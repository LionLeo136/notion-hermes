# ============================================
# network.tf — Hạ tầng mạng cho lab K8s
# ============================================

# 1. VPC — mạng riêng ảo, "khu đất" chứa mọi thứ
resource "aws_vpc" "main" {
  cidr_block           = "10.10.0.0/16"   # dải IP nội bộ của VPC (65k địa chỉ)
  enable_dns_support   = true             # cho phép phân giải DNS trong VPC
  enable_dns_hostnames = true             # cấp hostname DNS cho instance

  tags = {
    Name = "k8s-lab-vpc"
  }
}

# 2. Public Subnet — "lô đất" con trong VPC, nơi đặt EC2
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id   # thuộc VPC ở trên
  cidr_block              = "10.10.1.0/24"    # dải con (256 địa chỉ)
  availability_zone       = "ap-southeast-1a" # đặt trong 1 AZ cụ thể
  map_public_ip_on_launch = true              # EC2 tạo ra tự có IP public

  tags = {
    Name = "k8s-lab-public-subnet"
  }
}

# 3. Internet Gateway — "cổng" để VPC ra Internet
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "k8s-lab-igw"
  }
}

# 4. Route Table — "bảng chỉ đường" cho traffic
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"                       # mọi traffic đi ra ngoài
    gateway_id = aws_internet_gateway.igw.id       # ...đi qua Internet Gateway
  }

  tags = {
    Name = "k8s-lab-public-rt"
  }
}

# 5. Route Table Association — gắn bảng chỉ đường vào subnet
resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}