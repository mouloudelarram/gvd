# AWS EC2 DEPLOYMENT QUICK START GUIDE

> Fast track to production GVD deployment on AWS EC2

## Prerequisites

- AWS account with EC2 access
- GitHub OAuth App created
- Domain name (with DNS access)
- AWS CLI configured (optional but recommended)

## 5-Minute Setup

### Step 1: Launch EC2 Instance (2 min)

```bash
# Via AWS CLI (fastest)
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --key-name your-key-pair \
  --security-groups default \
  --block-device-mappings DeviceName=/dev/xvda,Ebs={VolumeSize=100,VolumeType=gp3} \
  --region us-east-1

# Or via AWS Console (manual)
# EC2 > Instances > Launch Instances
# Select Ubuntu 22.04 LTS
# t3.medium
# 100GB gp3 volume
# Security group: Allow 22, 80, 443
```

### Step 2: Connect & Setup (2 min)

```bash
# SSH into instance
ssh -i your-key.pem ubuntu@your-instance-ip

# Run setup script
curl -fsSL https://raw.githubusercontent.com/your-org/gvd/main/scripts/ec2-setup.sh | bash

# Or manually:
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### Step 3: Deploy GVD (1 min)

```bash
cd /opt
sudo git clone https://github.com/your-org/gvd.git
sudo chown -R ubuntu:ubuntu gvd
cd gvd

# Create directories
mkdir -p data/{scan_reports,repos,uploads,temp,ssl} logs/{nginx,app,scanner}

# Configure
cp .env.production.template .env.production
nano .env.production  # Add your GitHub OAuth credentials

# Start
docker-compose -f docker-compose.production.yml up -d
```

## Points to Verify

```bash
# Health check
curl http://localhost/health

# Services running
docker-compose -f docker-compose.production.yml ps

# Logs
docker-compose -f docker-compose.production.yml logs -f gvd-saas
```

## Next Steps

1. **Configure SSL**: See PRODUCTION_DEPLOYMENT_GUIDE.md - SSL/TLS Setup section
2. **Setup Domain**: Point DNS A record to your EC2 Public IP
3. **Enable Auto-Restart**: `sudo systemctl enable gvd.service`
4. **Monitor**: Set up CloudWatch alarms for CPU, Memory, Disk

## Cost Estimation (AWS)

| Component | Type | Cost/Month |
|-----------|------|-----------|
| EC2 t3.medium | compute | $30-40 |
| EBS gp3 100GB | storage | $10-12 |
| Data transfer (if heavy) | egress | varies |
| **Total** | | **$40-52** |

## Troubleshooting

```bash
# Can't SSH?
# Check security group allows SSH (port 22)

# Containers won't start?
docker logs $(docker ps -aq)

# Out of memory?
free -h  # Check available memory
docker stats  # Monitor container memory

# Nginx 502?
docker-compose -f docker-compose.production.yml logs nginx

# SSL errors?
# Ensure certificates are in data/ssl/cert.pem and data/ssl/key.pem
ls -la data/ssl/
```

## Security Quick Checklist

```bash
# Restrict security group
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxx \
  --protocol tcp \
  --port 22 \
  --cidr YOUR_IP/32

# Enable IMDSv2 (at instance launch)
# AWS Console > Launch > Advanced > IMDSv2 Required

# Enable termination protection
aws ec2 modify-instance-attribute --instance-id i-xxxxx --disable-api-termination

# Enable encryption (EBS)
# Already enabled for gp3 by default
```

## Useful AWS CLI Commands

```bash
# Describe instance
aws ec2 describe-instances --instance-ids i-xxxxx

# Get public IP
aws ec2 describe-instances --instance-ids i-xxxxx --query 'Reservations[0].Instances[0].PublicIpAddress'

# Stop instance (saves money when not in use)
aws ec2 stop-instances --instance-ids i-xxxxx

# Terminate instance
aws ec2 terminate-instances --instance-ids i-xxxxx

# Create AMI from instance (for easy replication)
aws ec2 create-image --instance-id i-xxxxx --name "gvd-production-$(date +%s)"
```

## Production Checklist

Before going live:

- [ ] Domain pointing to EC2 public IP
- [ ] SSL certificates installed
- [ ] GitHub OAuth configured and tested
- [ ] Backups automated
- [ ] Monitoring enabled
- [ ] Security groups restricted
- [ ] SSH key backed up securely
- [ ] .env.production is NOT in git
- [ ] Tested login and basic scanning
- [ ] Reviewed logs for errors

## Need Help?

See main PRODUCTION_DEPLOYMENT_GUIDE.md for detailed troubleshooting and advanced configuration.
