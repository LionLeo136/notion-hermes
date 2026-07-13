# ============================================
# outputs.tf — In ra thông tin sau khi apply
# ============================================

# 1. IP public của control-plane
output "control_plane_public_ip" {
  description = "IP public cua control-plane"
  value       = aws_instance.control_plane.public_ip
}

# 2. IP private của control-plane (dùng khi kubeadm init / join)
output "control_plane_private_ip" {
  description = "IP private cua control-plane (dung cho kubeadm)"
  value       = aws_instance.control_plane.private_ip
}

# 3. IP public của tất cả worker (list)
output "worker_public_ips" {
  description = "IP public cua cac worker"
  value       = aws_instance.worker[*].public_ip
}

# 4. IP private của tất cả worker
output "worker_private_ips" {
  description = "IP private cua cac worker"
  value       = aws_instance.worker[*].private_ip
}

# 5. Lệnh SSH sẵn sàng copy-paste cho từng máy
output "ssh_commands" {
  description = "Lenh SSH vao tung may"
  value = {
    control_plane = "ssh ubuntu@${aws_instance.control_plane.public_ip}"
    workers       = [for w in aws_instance.worker : "ssh ubuntu@${w.public_ip}"]
  }
}