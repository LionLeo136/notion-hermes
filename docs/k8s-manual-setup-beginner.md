# Hướng Dẫn Tự Dựng Kubernetes Cluster Bằng Kubeadm Cho Người Mới Bắt Đầu

> **Mục tiêu:** Tự tay dựng một cụm Kubernetes hoàn chỉnh bằng `kubeadm`, hiểu rõ từng thành phần và lý do đằng sau mỗi bước — không dùng script tự động, không dùng Ansible/kubespray.
>
> **Ngôn ngữ:** Tiếng Việt
>
> **Thời gian ước tính:** 45–90 phút (tùy tốc độ làm quen)
>
> **Lab đề xuất:** 3 máy Ubuntu 22.04 (1 control-plane + 2 worker), mỗi máy tối thiểu 2 vCPU / 2 GB RAM / 20 GB disk.

---

## Mục Lục

1. [Phase 0 — Chuẩn bị hạ tầng](#phase-0--chuẩn-bị-hạ-tầng)
2. [Phase 1 — Cài container runtime (containerd)](#phase-1--cài-container-runtime-containerd)
3. [Phase 2 — Cài kubeadm, kubelet, kubectl](#phase-2--cài-kubeadm-kubelet-kubectl)
4. [Phase 3 — kubeadm init trên control-plane](#phase-3--kubeadm-init-trên-control-plane)
5. [Phase 4 — Cài CNI (Cilium / Calico)](#phase-4--cài-cni-cilium--calico)
6. [Phase 5 — Join worker node vào cluster](#phase-5--join-worker-node-vào-cluster)
7. [Phase 6 — Kiểm tra & deploy app test](#phase-6--kiểm-tra--deploy-app-test)
8. [Phase 7 — Khái niệm cốt lõi cần nắm](#phase-7--khái-niệm-cốt-lõi-cần-nắm)
9. [Troubleshooting thường gặp](#troubleshooting-thường-gặp)
10. [Bước tiếp theo (Roadmap)](#bước-tiếp-theo-roadmap)
11. [Checklist hoàn thành](#checklist-hoàn-thành)

---

## Phase 0 — Chuẩn bị hạ tầng

### 0.1 Yêu cầu node

Bạn cần ít nhất 2 máy Ubuntu 22.04:

| Node | Vai trò | vCPU | RAM | Disk |
|------|---------|------|-----|------|
| k8s-master | control-plane | 2 | 2 GB | 20 GB |
| k8s-worker-1 | worker | 2 | 2 GB | 20 GB |
| k8s-worker-2 | worker | 2 | 2 GB | 20 GB |

**Nếu tiết kiệm chi phí:** Bạn có thể bỏ worker-2, chỉ cần 1 master + 1 worker (2 node). Mọi thứ vẫn chạy được, chỉ là bạn không có tính sẵn sàng cao (high availability) và không thấy được cách pod phân tán qua nhiều worker.

> **Tại sao 2 vCPU / 2 GB?** Control-plane chạy etcd, API server, scheduler, controller-manager — tất cả đều ngốn RAM. Dưới 2 GB, kubelet sẽ bị OOM Kill, cluster không khởi động nổi.

### 0.2 Đặt hostname và /etc/hosts

> **Tại sao cần đặt hostname và /etc/hosts?** Kubernetes dùng hostname để định danh node. Nếu hai node trùng hostname `ubuntu`, cluster sẽ lỗi. Thiết lập /etc/hosts giúp các node phân giải tên nhau mà không cần DNS server.

Chạy trên **từng node** (thay tên phù hợp):

```bash
# === CHẠY TRÊN ALL NODES ===

# Đổi hostname (chạy trên từng node với tên tương ứng)
sudo hostnamectl set-hostname k8s-master    # node control-plane
sudo hostnamectl set-hostname k8s-worker-1  # node worker 1
sudo hostnamectl set-hostname k8s-worker-2  # node worker 2

# Thêm vào /etc/hosts trên TẤT CẢ các node
# Thay IP bên dưới bằng IP thật của máy bạn
sudo tee -a /etc/hosts <<EOF
10.0.1.10  k8s-master
10.0.1.11  k8s-worker-1
10.0.1.12  k8s-worker-2
EOF
```

Xác nhận:
```bash
hostname          # phải ra đúng tên bạn vừa đặt
ping k8s-master   # phải ping được từ worker
```

### 0.3 Mở port trên firewall

> **Tại sao cần mở port?** Các thành phần Kubernetes giao tiếp qua mạng. Nếu port bị chặn, API server không nhận được request, kubelet không báo cáo được trạng thái, pod không giao tiếp được với nhau.

Chạy trên **all nodes**:

```bash
# === CHẠY TRÊN ALL NODES ===

# Nếu dùng ufw (phổ biến trên Ubuntu)
sudo ufw allow 6443/tcp          # Kubernetes API server
sudo ufw allow 2379:2380/tcp     # etcd (chỉ cần trên control-plane)
sudo ufw allow 10250/tcp         # kubelet API
sudo ufw allow 10251/tcp         # kube-scheduler
sudo ufw allow 10252/tcp         # kube-controller-manager
sudo ufw allow 30000:32767/tcp   # NodePort services
sudo ufw allow 8285/udp          # Cilium VXLAN (nếu dùng Cilium)
sudo ufw allow 8472/udp          # Flannel VXLAN (nếu dùng Flannel)

# Hoặc nếu bạn dùng cloud (AWS, GCP), mở các port trên trong Security Group
```

### 0.4 Tắt swap

> **Tại sao Kubernetes yêu cầu tắt swap?** Kubernetes lên lịch pod dựa trên tài nguyên thực (RAM). Nếu swap được bật, kernel có thể đẩy một phần memory ra disk, khiến kubelet nghĩ rằng node còn trống RAM trong khi thực tế ứng dụng đang dùng swap (chậm kinh khủng). Điều này phá vỡ cơ chế lập lịch của Kubernetes. Phiên bản 1.28+ có hỗ trợ swap beta nhưng không khuyến khích cho người mới.

```bash
# === CHẠY TRÊN ALL NODES ===

# Tắt swap ngay lập tức
sudo swapoff -a

# Tắt swap vĩnh viễn (comment dòng swap trong fstab)
sudo sed -i '/ swap / s/^\(.*\)$/#\1/g' /etc/fstab

# Kiểm tra swap đã tắt (phải ra dòng trống hoặc 0)
free -h | grep Swap
# Swap:           0Mi          0Mi          0Mi
```

### 0.5 Bật kernel modules và sysctl

> **Tại sao cần bật overlay và br_netfilter?** `overlay` là kernel module cần thiết cho overlay filesystem — thứ mà container image dùng để chồng các layer lên nhau. `br_netfilter` cho phép iptables nhìn thấy traffic đi qua Linux bridge — nếu thiếu, các rule iptables của Kubernetes (dùng để routing Service → Pod) sẽ không hoạt động, pod không giao tiếp được.

```bash
# === CHẠY TRÊN ALL NODES ===

# Load kernel modules
cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF

sudo modprobe overlay
sudo modprobe br_netfilter

# Kiểm tra đã load chưa
lsmod | grep overlay
lsmod | grep br_netfilter
```

> **Tại sao cần bật ip_forward?** `net.ipv4.ip_forward=1` cho phép Linux chuyển tiếp gói tin giữa các network interface. Kubernetes cần cái này để pod trên các node khác nhau giao tiếp được với nhau qua pod network.

```bash
# === CHẠY TRÊN ALL NODES ===

cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF

# Áp dụng ngay không cần reboot
sudo sysctl --system

# Kiểm tra
sysctl net.bridge.bridge-nf-call-iptables  # phải ra = 1
sysctl net.ipv4.ip_forward                  # phải ra = 1
```

Kết thúc Phase 0, **reboot tất cả node** để đảm bảo mọi thay đổi được áp dụng sạch sẽ:
```bash
sudo reboot
```

---

## Phase 1 — Cài container runtime (containerd)

### CRI là gì?

> **CRI (Container Runtime Interface)** là giao diện chuẩn mà Kubernetes dùng để giao tiếp với container runtime. Thay vì nói chuyện trực tiếp với Docker/containerd/CRI-O, kubelet nói chuyện qua CRI. Điều này giống như USB-C: chuẩn chung, nhiều thiết bị khác nhau cùng cắm được. Kubernetes 1.24+ đã bỏ hỗ trợ Docker trực tiếp (dockershim), nên containerd là lựa chọn mặc định và phổ biến nhất.

### Cài containerd

```bash
# === CHẠY TRÊN ALL NODES ===

# Cập nhật package list
sudo apt update && sudo apt upgrade -y

# Cài containerd
sudo apt install -y containerd

# Kiểm tra version
containerd --version
```

### Cấu hình containerd (SystemdCgroup)

> **Tại sao phải cấu hình SystemdCgroup=true?** Có 2 cách quản lý cgroup trên Linux: cgroupfs và systemd. Nếu containerd dùng cgroupfs nhưng kubelet dùng systemd (mặc định), 2 bên sẽ "cãi nhau" về giới hạn tài nguyên — container có thể vượt quá giới hạn CPU/RAM mà không bị chặn. Đặt `SystemdCgroup = true` đồng bộ cả 2 về systemd, tránh xung đột.

```bash
# === CHẠY TRÊN ALL NODES ===

# Tạo thư mục config nếu chưa có
sudo mkdir -p /etc/containerd

# Tạo config mặc định và ghi vào file
containerd config default | sudo tee /etc/containerd/config.toml > /dev/null

# Sửa SystemdCgroup từ false → true
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml

# Kiểm tra đã sửa đúng chưa
grep "SystemdCgroup" /etc/containerd/config.toml
# Phải ra: SystemdCgroup = true

# Restart containerd
sudo systemctl restart containerd
sudo systemctl enable containerd
sudo systemctl status containerd
```

---

## Phase 2 — Cài kubeadm, kubelet, kubectl

> **Phân biệt 3 thành phần:**
> - **kubeadm:** Công cụ "khởi tạo" — dùng để `init` cluster (chạy 1 lần) và `join` node mới. Nó không phải là service chạy nền.
> - **kubelet:** Service chạy trên MỌI node, là "quản đốc" của node đó. Nó nhận lệnh từ control-plane (API server) và đảm bảo container trong pod chạy đúng như khai báo. Kubelet là thành phần DUY NHẤT không được quản lý bởi Kubernetes (nó chạy như systemd service).
> - **kubectl:** CLI tool để bạn (con người) ra lệnh cho cluster. Bạn cài nó trên máy cá nhân hoặc trên control-plane. Nó nói chuyện với API server qua REST.

```bash
# === CHẠY TRÊN ALL NODES ===

# Thêm Kubernetes APT repo
sudo apt install -y apt-transport-https ca-certificates curl gpg

# Tạo thư mục keyrings
sudo mkdir -p /etc/apt/keyrings

# Download và cài GPG key của Kubernetes
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

# Thêm repo (pin version 1.29 — ổn định, phổ biến)
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /" \
  | sudo tee /etc/apt/sources.list.d/kubernetes.list

# Cài đặt
sudo apt update
sudo apt install -y kubelet kubeadm kubectl

# Pin version (giữ nguyên version, không tự upgrade khi apt upgrade)
sudo apt-mark hold kubelet kubeadm kubectl

# Kiểm tra version
kubeadm version
kubelet --version
kubectl version --client

# Kubelet sẽ khởi động nhưng chưa join cluster nên sẽ báo lỗi — bình thường!
sudo systemctl status kubelet
```

> **Tại sao pin version?** Kubernetes release mỗi 4 tháng. Nếu `apt upgrade` tự động nâng kubelet từ 1.29 lên 1.31 nhưng control-plane vẫn chạy 1.29, cluster sẽ vỡ (kubelet chỉ tương thích với API server chênh lệch tối đa 1 minor version). `apt-mark hold` ngăn chặn việc này.

---

## Phase 3 — kubeadm init trên control-plane

### 3.1 Chạy kubeadm init

> **Chỉ chạy trên control-plane node (k8s-master).**

```bash
# === CHẠY TRÊN CONTROL-PLANE (k8s-master) ===

# Khởi tạo cluster với pod network CIDR
# --pod-network-cidr: dải IP cho pod (pod sẽ được gán IP trong dải này)
# Chọn 10.244.0.0/16 nếu dùng Flannel, 10.0.0.0/8 hoặc để mặc định với Cilium/Calico
sudo kubeadm init \
  --pod-network-cidr=10.0.0.0/8 \
  --apiserver-advertise-address=<ĐỊA-CHỈ-IP-CỦA-MASTER>
```

> **Tại sao chọn --pod-network-cidr=10.0.0.0/8?** Cilium (CNI mình sẽ dùng) mặc định không yêu cầu CIDR cụ thể, nhưng cung cấp CIDR rộng giúp sau này không bị giới hạn số lượng pod. Nếu bạn chọn dùng Calico, CIDR mặc định của nó là `192.168.0.0/16`. Nếu chọn Flannel, bạn phải dùng `10.244.0.0/16`.

**Khi chạy thành công, bạn sẽ thấy output giống thế này:**

```
Your Kubernetes control-plane has initialized successfully!

To start using your cluster, you need to run the following as a regular user:

  mkdir -p $HOME/.kube
  sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
  sudo chown $(id -u):$(id -g) $HOME/.kube/config

You can now join any number of worker nodes by running the following on each as root:

kubeadm join 10.0.1.10:6443 --token abcdef.0123456789abcdef \
    --discovery-token-ca-cert-hash sha256:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3.2 Cấu hình kubectl cho user thường

> **Tại sao cần copy admin.conf?** `kubectl` đọc config từ `~/.kube/config` để biết API server ở đâu và xác thực thế nào. File `/etc/kubernetes/admin.conf` chứa certificate + token admin, nhưng chỉ root mới đọc được. Copy về home directory để user thường dùng được kubectl.

```bash
# === CHẠY TRÊN CONTROL-PLANE (k8s-master) ===

mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config

# Test
kubectl version
kubectl cluster-info
```

### 3.3 Quan sát output ban đầu

```bash
# Xem các pod đang chạy trong namespace kube-system
kubectl get pods -n kube-system
```

Bạn sẽ thấy output đại loại:

```
NAME                               READY   STATUS    RESTARTS   AGE
coredns-xxxxx-xxxxx                0/1     Pending   0          2m
coredns-xxxxx-yyyyy                0/1     Pending   0          2m
etcd-k8s-master                    1/1     Running   0          2m
kube-apiserver-k8s-master          1/1     Running   0          2m
kube-controller-manager-k8s-master 1/1     Running   0          2m
kube-proxy-xxxxx                   1/1     Running   0          2m
kube-scheduler-k8s-master          1/1     Running   0          2m
```

> **Tại sao CoreDNS đang Pending?** CoreDNS cần một pod network (CNI) để được gán IP. Hiện tại chưa cài CNI nên không pod nào có IP — CoreDNS không thể khởi động. Sau khi cài CNI ở Phase 4, CoreDNS sẽ tự chuyển sang Running. Đây là hành vi hoàn toàn bình thường.

**Giải thích nhanh các pod trong kube-system:**

| Pod | Vai trò |
|-----|---------|
| etcd | Database lưu toàn bộ trạng thái cluster |
| kube-apiserver | Cổng giao tiếp chính — mọi thứ đều qua đây |
| kube-controller-manager | Chạy các controller (node, deployment, ...) |
| kube-scheduler | Quyết định pod chạy trên node nào |
| kube-proxy | Quản lý network rules để Service → Pod |
| coredns | DNS nội bộ cho cluster |

### 3.4 Lưu lệnh join

> **Quan trọng:** Lưu lại dòng `kubeadm join ...` từ output. Bạn sẽ cần nó để join worker node. Nếu lỡ mất, đừng lo — xem cách tạo lại token ở Phase 5.

```bash
# Lưu ra file cho chắc
echo "kubeadm join 10.0.1.10:6443 --token abcdef.0123456789abcdef \
    --discovery-token-ca-cert-hash sha256:xxxxx" > ~/join-command.txt
```

---

## Phase 4 — Cài CNI (Cilium / Calico)

### CNI là gì?

> **CNI (Container Network Interface)** là plugin mạng cho Kubernetes. Nó chịu trách nhiệm gán IP cho pod, định tuyến traffic giữa các pod trên các node khác nhau, và thực thi Network Policy. Không có CNI, pod không có IP và không thể giao tiếp — đó là lý do CoreDNS đang Pending.

### 4.1 Cilium (Khuyến nghị)

> **Tại sao Cilium?** Cilium dùng eBPF (công nghệ kernel hiện đại) thay vì iptables truyền thống — nhanh hơn, ít overhead hơn, có built-in observability (Hubble) và Network Policy mạnh mẽ. Đây là CNI phổ biến nhất hiện nay trong production.

```bash
# === CHẠY TRÊN CONTROL-PLANE (k8s-master) ===

# Cài Cilium CLI
CILIUM_CLI_VERSION=$(curl -s https://raw.githubusercontent.com/cilium/cilium-cli/main/stable.txt)
CLI_ARCH=amd64
if [ "$(uname -m)" = "aarch64" ]; then CLI_ARCH=arm64; fi
curl -L --fail --remote-name-all \
  https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-linux-${CLI_ARCH}.tar.gz{,.sha256sum}
sha256sum --check cilium-linux-${CLI_ARCH}.tar.gz.sha256sum
sudo tar xzvfC cilium-linux-${CLI_ARCH}.tar.gz /usr/local/bin
rm cilium-linux-${CLI_ARCH}.tar.gz{,.sha256sum}

# Cài Cilium vào cluster
cilium install

# Kiểm tra trạng thái Cilium
cilium status --wait
```

Đợi đến khi tất cả deployment sẵn sàng:

```bash
# Xem các pod Cilium
kubectl get pods -n kube-system | grep cilium

# Kiểm tra node đã Ready chưa
kubectl get nodes
# NAME          STATUS   ROLES           AGE   VERSION
# k8s-master    Ready    control-plane   5m   v1.29.x
```

```bash
# Test kết nối giữa các pod Cilium
cilium connectivity test
```

### 4.2 Calico (Phương án thay thế)

Nếu bạn muốn dùng Calico thay vì Cilium:

```bash
# === CHẠY TRÊN CONTROL-PLANE (k8s-master) ===

# Cài Calico operator + CRDs
kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/v3.27/manifests/tigera-operator.yaml

# Tạo custom resource cho Calico installation
kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/v3.27/manifests/custom-resources.yaml

# Kiểm tra
kubectl get pods -n calico-system
kubectl get nodes
```

> **Lưu ý:** Nếu bạn dùng Calico, CIDR khi `kubeadm init` nên để `--pod-network-cidr=192.168.0.0/16` (mặc định của Calico). Nếu bạn đã init với CIDR khác, sửa trong file `custom-resources.yaml` trước khi apply.

---

## Phase 5 — Join worker node vào cluster

### 5.1 Join worker node

```bash
# === CHẠY TRÊN TỪNG WORKER NODE (k8s-worker-1, k8s-worker-2) ===

# Dùng lệnh join từ Phase 3
sudo kubeadm join 10.0.1.10:6443 \
  --token abcdef.0123456789abcdef \
  --discovery-token-ca-cert-hash sha256:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Output thành công:
```
This node has joined the cluster:
* Certificate signing request was sent to apiserver and a response was received.
* The Kubelet was informed of the new secure connection details.

Run 'kubectl get nodes' on the control-plane to see this node join the cluster.
```

### 5.2 Kiểm tra từ control-plane

```bash
# === CHẠY TRÊN CONTROL-PLANE (k8s-master) ===

kubectl get nodes -w
# Gõ Ctrl+C khi tất cả node đều Ready
```

### 5.3 Tạo lại token nếu token cũ hết hạn

> **Tại sao token hết hạn?** Token mặc định chỉ có hiệu lực 24 giờ. Nếu bạn dựng cluster hôm qua, hôm nay join worker, token đã hết hạn.

```bash
# === CHẠY TRÊN CONTROL-PLANE (k8s-master) ===

# Kiểm tra token còn không
kubeadm token list

# Nếu trống → tạo token mới
kubeadm token create --print-join-command
# Output: lệnh join mới với token mới, copy paste vào worker node
```

---

## Phase 6 — Kiểm tra & deploy app test

### 6.1 Kiểm tra tổng quan cluster

```bash
# === CHẠY TRÊN CONTROL-PLANE (k8s-master) ===

kubectl get nodes
kubectl get pods -A
kubectl get namespaces
```

### 6.2 Deploy ứng dụng test (nginx)

Tạo file `nginx-demo.yaml`:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: demo
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
  namespace: demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:latest
        ports:
        - containerPort: 80
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 200m
            memory: 256Mi
---
apiVersion: v1
kind: Service
metadata:
  name: nginx-svc
  namespace: demo
spec:
  type: NodePort
  selector:
    app: nginx
  ports:
  - port: 80
    targetPort: 80
    nodePort: 30080
```

```bash
# === CHẠY TRÊN CONTROL-PLANE (k8s-master) ===

# Lưu file YAML (copy nội dung trên)
cat > nginx-demo.yaml <<'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: demo
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
  namespace: demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: nginx
  template:
    metadata:
      labels:
        app: nginx
    spec:
      containers:
      - name: nginx
        image: nginx:latest
        ports:
        - containerPort: 80
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 200m
            memory: 256Mi
---
apiVersion: v1
kind: Service
metadata:
  name: nginx-svc
  namespace: demo
spec:
  type: NodePort
  selector:
    app: nginx
  ports:
  - port: 80
    targetPort: 80
    nodePort: 30080
EOF

# Apply
kubectl apply -f nginx-demo.yaml

# Kiểm tra
kubectl get all -n demo
# Bạn sẽ thấy Deployment, ReplicaSet, và 2 Pod nginx
```

### 6.3 Test truy cập

```bash
# Test từ chính control-plane hoặc worker node
curl http://localhost:30080
# Hoặc từ máy của bạn: curl http://<IP-CỦA-WORKER>:30080
```

Bạn sẽ thấy HTML mặc định của nginx — chào mừng, cluster của bạn đã hoạt động!

### 6.4 Giới thiệu k9s (terminal UI)

k9s là giao diện terminal giúp bạn quản lý Kubernetes dễ hơn nhiều so với gõ `kubectl` liên tục.

```bash
# === CHẠY TRÊN CONTROL-PLANE (k8s-master) ===

# Cài k9s
curl -sS https://webinstall.dev/k9s | bash

# Hoặc cài bằng snap
sudo snap install k9s

# Mở k9s
k9s
```

Trong k9s:
- Phím `0` — xem tất cả namespace
- Phím `:` — gõ lệnh (vd: `:deploy` để xem deployments)
- Phím `d` — describe resource đang chọn
- Phím `l` — logs của pod đang chọn
- Phím `s` — shell vào pod đang chọn
- Phím `Ctrl+C` — thoát

---

## Phase 7 — Khái niệm cốt lõi cần nắm

Sau khi dựng xong cluster và chạy được app, đây là những khái niệm bạn PHẢI hiểu:

### Pod
Đơn vị nhỏ nhất trong Kubernetes — 1 pod = 1 hoặc nhiều container chạy cùng nhau, chia sẻ IP và volume. Pod là "nhà" của container. Pod là ephemeral (tạm thời) — khi pod chết, IP mất, pod mới được tạo với IP mới.

### Deployment
Khai báo trạng thái mong muốn: "Tôi muốn 3 bản sao của nginx luôn chạy". Deployment tạo ra ReplicaSet, ReplicaSet tạo ra Pod. Khi bạn update image, Deployment tạo ReplicaSet mới và roll từng pod (rolling update).

### ReplicaSet
Đảm bảo số lượng pod luôn đúng như khai báo. Nếu 1 pod chết → tạo pod mới ngay. Bạn hiếm khi tạo ReplicaSet trực tiếp — Deployment quản lý nó cho bạn.

### Service
Pod có IP tạm thời → Service cung cấp 1 IP/DNS cố định để truy cập pod. Service dùng label selector để tìm pod. Các loại Service phổ biến:
- **ClusterIP** (mặc định): Chỉ truy cập được trong cluster
- **NodePort**: Mở port trên tất cả node → truy cập từ ngoài qua `<node-ip>:<port>`
- **LoadBalancer**: Tự động tạo cloud load balancer (dùng trên cloud)

### Namespace
"Thư mục ảo" để phân chia tài nguyên trong cluster. VD: `demo`, `production`, `monitoring`. Giúp cô lập tài nguyên và quản lý RBAC.

### kubectl cơ bản

| Lệnh | Công dụng |
|------|-----------|
| `kubectl get pods` | Liệt kê pod |
| `kubectl get pods -A` | Liệt kê pod TẤT CẢ namespace |
| `kubectl describe pod <name>` | Chi tiết pod (event, state, ...) |
| `kubectl logs <pod>` | Xem log của pod |
| `kubectl logs -f <pod>` | Follow log (realtime) |
| `kubectl exec -it <pod> -- sh` | Vào shell trong pod |
| `kubectl apply -f file.yaml` | Tạo/cập nhật resource từ file |
| `kubectl delete -f file.yaml` | Xóa resource từ file |
| `kubectl delete pod <name>` | Xóa pod (Deployment sẽ tự tạo lại) |
| `kubectl get events` | Xem events trong namespace hiện tại |
| `kubectl get events -A` | Xem events toàn cluster |
| `kubectl api-resources` | Liệt kê tất cả loại resource |

---

## Troubleshooting thường gặp

### Node NotReady

```bash
# Kiểm tra chi tiết node
kubectl describe node <node-name>

# Kiểm tra kubelet
sudo systemctl status kubelet
sudo journalctl -u kubelet -f
```

Nguyên nhân thường gặp:
- **CNI chưa cài** — xem Phase 4
- **containerd không chạy** — `sudo systemctl restart containerd`
- **Swap chưa tắt** — `sudo swapoff -a`
- **Port bị chặn** — kiểm tra firewall/Security Group

### CoreDNS Pending

```bash
kubectl describe pod -n kube-system -l k8s-app=kube-dns
```

Nguyên nhân: 99% là do chưa cài CNI. Sau khi cài CNI, CoreDNS tự chuyển Running trong 30-60 giây.

### Token hết hạn

```bash
# Tạo token mới
kubeadm token create --print-join-command
```

### Lỗi swap

```bash
# Kiểm tra
swapon --show

# Nếu vẫn thấy swap → tắt triệt để
sudo swapoff -a
sudo sed -i '/ swap / s/^/#/' /etc/fstab
sudo systemctl daemon-reload
```

### Lỗi containerd cgroup

```bash
# Kiểm tra cấu hình
grep SystemdCgroup /etc/containerd/config.toml
# Phải ra: SystemdCgroup = true

# Nếu sai → sửa và restart
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
sudo systemctl restart containerd
sudo systemctl restart kubelet
```

### Reset toàn bộ cluster

Nếu mọi thứ quá rối và bạn muốn làm lại từ đầu:

```bash
# === CHẠY TRÊN TẤT CẢ NODE ===

# Reset kubeadm (xóa cluster state)
sudo kubeadm reset -f

# Dọn dẹp CNI config
sudo rm -rf /etc/cni/net.d

# Dọn dẹp iptables rules
sudo iptables -F && sudo iptables -t nat -F && sudo iptables -t mangle -F
sudo iptables -X

# Dọn dẹp IPVS (nếu dùng)
sudo ipvsadm --clear 2>/dev/null

# Xóa Kubernetes config
sudo rm -rf ~/.kube
sudo rm -rf /etc/kubernetes/

# Restart containerd
sudo systemctl restart containerd

# Giờ bạn có thể chạy lại kubeadm init từ Phase 3
```

---

## Bước tiếp theo (Roadmap)

Sau khi đã thành thạo dựng cluster bằng tay và hiểu được các khái niệm cốt lõi, đây là lộ trình tiếp theo:

| Bước | Chủ đề | Mô tả ngắn |
|------|--------|------------|
| 1 | **Ingress + cert-manager** | Expose HTTP service ra ngoài với domain + HTTPS tự động (Let's Encrypt). Dùng ingress-nginx hoặc Traefik. |
| 2 | **Storage (Longhorn / Rook-Ceph)** | Persistent storage cho database và stateful app. Longhorn nhẹ, dễ cài, phù hợp homelab. |
| 3 | **Observability (kube-prometheus-stack)** | Monitoring với Prometheus + Grafana + AlertManager. Dashboard có sẵn, alert khi có vấn đề. |
| 4 | **GitOps (ArgoCD)** | Quản lý toàn bộ config cluster qua Git. Mọi thay đổi = commit + push, ArgoCD tự sync. |
| 5 | **Security (Falco, Trivy, OPA)** | Runtime security, scan image vulnerability, policy-as-code. |
| 6 | **Service Mesh (Istio / Linkerd)** | Advanced traffic management, mTLS, observability giữa các service. |
| 7 | **Multi-cluster (Karmada / Cluster API)** | Quản lý nhiều cluster cùng lúc, disaster recovery. |

> Mỗi bước trên đều nên được thực hành trên cluster bạn vừa dựng. Đừng nhảy cóc — hiểu vững bước trước rồi mới qua bước sau.

---

## Checklist hoàn thành

Tick vào ô khi bạn đã hoàn thành từng bước:

- [ ] **Phase 0:** Hostname + /etc/hosts + firewall + swap + kernel modules + sysctl đã cấu hình trên tất cả node
- [ ] **Phase 1:** containerd đã cài + SystemdCgroup=true trên tất cả node; `sudo systemctl status containerd` → active
- [ ] **Phase 2:** kubeadm, kubelet, kubectl đã cài + `apt-mark hold` trên tất cả node
- [ ] **Phase 3:** `kubeadm init` thành công; `kubectl get nodes` thấy control-plane; CoreDNS đang Pending (bình thường!)
- [ ] **Phase 4:** Cilium (hoặc Calico) đã cài; `kubectl get nodes` → control-plane Ready
- [ ] **Phase 4:** CoreDNS đã Running (xác nhận bằng `kubectl get pods -n kube-system`)
- [ ] **Phase 5:** Worker node đã join; `kubectl get nodes` → tất cả node Ready
- [ ] **Phase 6:** Đã deploy nginx + Service NodePort; `curl` thành công
- [ ] **Phase 6:** Đã cài và mở k9s, thử navigate qua các resource
- [ ] **Phase 7:** Hiểu Pod, Deployment, ReplicaSet, Service, Namespace là gì
- [ ] **Phase 7:** Đã thử `kubectl get/describe/logs/exec/apply/delete`
- [ ] **Troubleshooting:** Đã thử `kubeadm reset` và dựng lại từ đầu (khuyến khích làm ít nhất 1 lần để nhớ!)

---

> **Lời kết:** Bạn vừa tự tay dựng một cụm Kubernetes hoàn chỉnh. Bạn đã hiểu từng thành phần làm gì và tại sao cần nó — đó là nền tảng vững chắc hơn bất kỳ script tự động nào. Từ đây, bạn có thể tự tin học các chủ đề nâng cao hơn. Chúc bạn vững tay lái trên con đường Kubernetes!
