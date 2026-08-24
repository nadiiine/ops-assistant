# EC2 for self-managed kubeadm nodes.
#
# - Control-plane: aws_instance + user_data (control-plane.sh)
# - Workers: launch template + ASG + user_data (worker.sh)
# Join coordination: SSM Parameter Store SecureString (see iam.tf + scripts).

################################################################################
# Ubuntu AMI (Canonical) — resolved dynamically; not hardcoded
################################################################################

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = [var.ubuntu_ami_name_filter]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

locals {
  worker_instance_type = var.worker_instance_type != "" ? var.worker_instance_type : var.instance_type
  key_name_effective   = var.key_name != "" ? var.key_name : null

  control_plane_user_data = templatefile("${path.module}/scripts/control-plane.sh", local.bootstrap_template_vars)
  worker_user_data = templatefile("${path.module}/scripts/worker.sh", merge(local.bootstrap_template_vars, {
    ecr_kubelet_creds_script = file("${path.module}/scripts/install-ecr-kubelet-creds.sh")
  }))
}

################################################################################
# Control-plane (single instance)
################################################################################

resource "aws_instance" "control_plane" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.control_plane.id]
  iam_instance_profile        = aws_iam_instance_profile.control_plane.name
  associate_public_ip_address = true
  key_name                    = local.key_name_effective

  user_data = local.control_plane_user_data
  # Live cluster is healthy. Do not replace the instance when bootstrap
  # scripts or the Ubuntu AMI data source change.
  user_data_replace_on_change = false

  lifecycle {
    ignore_changes = [ami, user_data]
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_volume_size_gb
    encrypted   = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-control-plane"
    Role = "control-plane"
  })

  depends_on = [
    aws_iam_role_policy.control_plane_join_ssm,
    aws_internet_gateway.this,
  ]
}

################################################################################
# Workers — launch template + Auto Scaling Group
################################################################################

resource "aws_launch_template" "workers" {
  name_prefix   = "${local.name_prefix}-workers-"
  image_id      = data.aws_ami.ubuntu.id
  instance_type = local.worker_instance_type
  key_name      = local.key_name_effective

  user_data = base64encode(local.worker_user_data)

  iam_instance_profile {
    name = aws_iam_instance_profile.workers.name
  }

  network_interfaces {
    associate_public_ip_address = true
    security_groups             = [aws_security_group.workers.id]
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  block_device_mappings {
    device_name = "/dev/sda1"

    ebs {
      volume_type = "gp3"
      volume_size = var.root_volume_size_gb
      encrypted   = true
    }
  }

  tag_specifications {
    resource_type = "instance"

    tags = merge(local.common_tags, {
      Name = "${local.name_prefix}-worker"
      Role = "worker"
    })
  }

  tag_specifications {
    resource_type = "volume"

    tags = merge(local.common_tags, {
      Name = "${local.name_prefix}-worker-root"
      Role = "worker"
    })
  }

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-workers-lt"
    Role = "worker"
  })

  lifecycle {
    create_before_destroy = true
    # Avoid rewriting worker user_data on CRLF/template drift. Live hop-limit/AMI
    # changes still apply as new LT versions without replacing the control plane.
    ignore_changes = [user_data]
  }

  depends_on = [
    aws_iam_role_policy.workers_join_ssm,
    aws_iam_role_policy_attachment.workers_ecr,
  ]
}

resource "aws_autoscaling_group" "workers" {
  name                = "${local.name_prefix}-workers"
  vpc_zone_identifier = aws_subnet.public[*].id
  min_size            = var.worker_min_size
  max_size            = var.worker_max_size
  desired_capacity    = var.worker_desired_capacity

  health_check_type         = "EC2"
  health_check_grace_period = 900

  launch_template {
    id      = aws_launch_template.workers.id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "${local.name_prefix}-worker"
    propagate_at_launch = true
  }

  tag {
    key                 = "Project"
    value               = var.project_name
    propagate_at_launch = true
  }

  tag {
    key                 = "Environment"
    value               = var.environment
    propagate_at_launch = true
  }

  tag {
    key                 = "ManagedBy"
    value               = "terraform"
    propagate_at_launch = true
  }

  tag {
    key                 = "Phase"
    value               = "2"
    propagate_at_launch = true
  }

  tag {
    key                 = "Role"
    value               = "worker"
    propagate_at_launch = true
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_instance.control_plane,
  ]
}
