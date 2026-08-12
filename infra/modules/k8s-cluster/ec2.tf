# EC2 for self-managed kubeadm nodes.
#
# - Control-plane: single aws_instance (no user_data / kubeadm yet)
# - Workers: launch template + Auto Scaling Group (no user_data / kubeadm yet)
#
# SSH key_name is optional: SSM Session Manager is the primary access path when
# enable_ssm = true. Set key_name only if you also configure allowed_ssh_cidrs.

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
  # Empty string means "no EC2 key pair" (SSM-only access).
  key_name_effective = var.key_name != "" ? var.key_name : null
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

  # Intentionally empty — kubeadm bootstrap comes in a later step.
  user_data = null

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
}

################################################################################
# Workers — launch template + Auto Scaling Group
################################################################################

resource "aws_launch_template" "workers" {
  name_prefix   = "${local.name_prefix}-workers-"
  image_id      = data.aws_ami.ubuntu.id
  instance_type = local.worker_instance_type
  key_name      = local.key_name_effective

  # Intentionally empty — kubeadm join comes in a later step.
  user_data = null

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
    http_put_response_hop_limit = 1
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
  }
}

resource "aws_autoscaling_group" "workers" {
  name                = "${local.name_prefix}-workers"
  vpc_zone_identifier = aws_subnet.public[*].id
  min_size            = var.worker_min_size
  max_size            = var.worker_max_size
  desired_capacity    = var.worker_desired_capacity

  health_check_type         = "EC2"
  health_check_grace_period = 60

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
}
