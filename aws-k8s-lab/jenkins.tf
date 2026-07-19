# jenkins.tf — mở cổng Jenkins UI (Jenkins chạy container trên Box1)
resource "aws_vpc_security_group_ingress_rule" "jenkins_web" {
  security_group_id = aws_security_group.k8s.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 8081     # đổi
  to_port           = 8081     # đổi
  description       = "Jenkins web UI"
}