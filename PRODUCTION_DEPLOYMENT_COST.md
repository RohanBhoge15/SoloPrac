# SoloPrac AI — Production Deployment Cost Analysis

**Version:** 1.0
**Date:** July 2026
**Region:** AWS Mumbai (ap-south-1) + GCP India
**Currency:** INR (₹) with USD equivalents
**Target:** Solo medical practitioners in India (SaaS model)

---

## 1. Executive Summary

This document provides a comprehensive cost analysis for deploying SoloPrac AI from a capstone prototype to a production-grade SaaS platform serving solo medical practitioners across India.

### Key Findings

| Metric | Value |
|--------|-------|
| **Monthly cost (50 doctors)** | ₹45,000 – ₹75,000 |
| **Monthly cost (500 doctors)** | ₹1,50,000 – ₹3,50,000 |
| **Monthly cost (5,000 doctors)** | ₹8,00,000 – ₹18,00,000 |
| **Cost per doctor/month** | ₹900 – ₹1,500 |
| **Revenue per doctor/month** | ₹2,000 – ₹5,000 |
| **Gross margin** | 55% – 75% |

### Cost Drivers (Ranked by Impact)

1. **AI/ML API costs** (35-45% of total) — LLM, OCR, ASR
2. **Compute infrastructure** (25-35% of total) — EC2, RDS, ElastiCache
3. **Storage & database** (10-15% of total) — S3, RDS, Qdrant
4. **Communication** (5-10% of total) — Email, SMS, WhatsApp
5. **Monitoring & compliance** (5-8% of total) — Sentry, Langfuse, audit

---

## 2. Infrastructure Costs (AWS Mumbai)

### 2.1 Compute — EC2 Instances

| Instance | vCPU | RAM | On-Demand | 1-Year RI | Purpose |
|----------|------|-----|-----------|-----------|---------|
| **t3.medium** | 2 | 4 GB | ₹2,500/mo | ₹1,600/mo | Backend API |
| **t3.large** | 2 | 8 GB | ₹5,000/mo | ₹3,200/mo | Backend API (prod) |
| **m6i.large** | 2 | 8 GB | ₹5,800/mo | ₹3,700/mo | Backend API (high perf) |
| **m6i.xlarge** | 4 | 16 GB | ₹11,700/mo | ₹7,500/mo | Backend + worker |
| **t3.medium** | 2 | 4 GB | ₹2,500/mo | ₹1,600/mo | Frontend (nginx) |

**Recommended production setup:**
- Backend: `m6i.large` (2 vCPU, 8 GB) — handles 50-100 concurrent doctors
- Worker: `t3.medium` (2 vCPU, 4 GB) — arq background jobs
- Frontend: `t3.medium` (2 vCPU, 4 GB) — nginx + static files

**Monthly compute cost: ₹8,300 – ₹14,200**

### 2.2 Database — RDS PostgreSQL

| Instance | vCPU | RAM | Storage | On-Demand | 1-Year RI |
|----------|------|-----|---------|-----------|-----------|
| **db.t3.small** | 2 | 2 GB | 20 GB | ₹4,500/mo | ₹2,900/mo |
| **db.t3.medium** | 2 | 4 GB | 50 GB | ₹9,000/mo | ₹5,800/mo |
| **db.t3.large** | 2 | 8 GB | 100 GB | ₹18,000/mo | ₹11,500/mo |

**Recommended:** `db.t3.medium` with Multi-AZ for HA

**Additional costs:**
- Storage (gp3): ₹8.5/GB/month
- Automated backups: Included (35 days)
- Data transfer: ₹6.5/GB outbound

**Monthly database cost: ₹9,000 – ₹18,000**

### 2.3 Cache — ElastiCache Redis

| Instance | RAM | On-Demand | 1-Year RI |
|----------|-----|-----------|-----------|
| **cache.t3.small** | 1 GB | ₹2,200/mo | ₹1,400/mo |
| **cache.t3.medium** | 3 GB | ₹4,500/mo | ₹2,900/mo |
| **cache.t3.large** | 6 GB | ₹9,000/mo | ₹5,800/mo |

**Recommended:** `cache.t3.medium` (3 GB) for session + queue + rate limiting

**Monthly cache cost: ₹4,500 – ₹9,000**

### 2.4 Vector Database — Qdrant

**Option A: Self-hosted on EC2** (recommended for cost)
- Run Qdrant on existing `t3.medium` — ₹0 additional
- Or dedicated `t3.medium` — ₹2,500/mo

**Option B: Qdrant Cloud** (managed)
- Standard tier: ~₹5,500/mo ($65/mo) for 2 vCPU, 4 GB RAM
- Free tier: 1 GB RAM (testing only)

**Recommended:** Self-hosted on EC2 for cost savings

**Monthly vector DB cost: ₹0 – ₹5,500**

### 2.5 Object Storage — S3

| Storage Class | Price/GB/month | Use Case |
|---------------|----------------|----------|
| **Standard** | ₹1.75 | Active documents |
| **Infrequent Access** | ₹0.85 | Old documents |
| **Glacier Instant** | ₹0.35 | Archive |

**Estimated storage:** 10 GB initial, growing ~1 GB/month per 100 doctors

**Additional costs:**
- PUT/POST requests: ₹0.05 per 1,000
- GET requests: ₹0.004 per 1,000
- Data transfer out: ₹6.50/GB (first 10 TB)

**Monthly storage cost: ₹500 – ₹2,000**

### 2.6 Load Balancer — ALB

- Application Load Balancer: ₹2,200/mo base
- LCU charges: ₹0.35 per LCU-hour

**Monthly ALB cost: ₹2,200 – ₹4,500**

### 2.7 CDN — CloudFront

- Data transfer: ₹6.50/GB (first 10 TB)
- Requests: ₹0.0075 per 10,000 (HTTPS)

**Estimated:** 100 GB/month = ₹650

**Monthly CDN cost: ₹500 – ₹2,000**

### 2.8 Domain & SSL

- Domain: ₹800 – ₹1,500/year (₹65 – ₹125/mo)
- SSL: Free (Let's Encrypt via Caddy)
- Route 53: ₹500/mo for hosted zone

**Monthly domain cost: ₹125 – ₹500**

---

## 3. AI/ML API Costs

### 3.1 LLM APIs

| Provider | Model | Input/1M tokens | Output/1M tokens | Use Case |
|----------|-------|-----------------|------------------|----------|
| **NVIDIA NIM** | Llama-4-Maverick | Free (1000 credits) | Free | Response synthesis |
| **NVIDIA NIM** | Llama-3.1-8B | Free (1000 credits) | Free | Intent classification |
| **Groq** | Llama-3.2-90B-Vision | Free (14,400 req/day) | Free | Medical image analysis |
| **OpenAI** | GPT-4o | ₹210 ($2.50) | ₹840 ($10.00) | Production fallback |
| **OpenAI** | GPT-4o-mini | ₹12.50 ($0.15) | ₹50 ($0.60) | High-volume tasks |
| **Anthropic** | Claude Sonnet | ₹250 ($3.00) | ₹1,250 ($15.00) | Complex reasoning |

**Usage estimates per doctor/month:**
- Intent classification: ~500 requests × 200 tokens = 100K tokens
- Response synthesis: ~200 requests × 1,000 tokens = 200K input + 100K output
- Medical image analysis: ~50 requests × 500 tokens = 25K tokens

**Monthly LLM cost per doctor: ₹0 (free tier) – ₹150 (paid API)**

**Monthly LLM cost (50 doctors): ₹0 – ₹7,500**

### 3.2 OCR APIs

| Provider | Service | Price/1,000 pages | Use Case |
|----------|---------|-------------------|----------|
| **AWS Textract** | DetectDocumentText | ₹125 ($1.50) | Plain text OCR |
| **AWS Textract** | AnalyzeDocument (Tables) | ₹1,250 ($15.00) | Table extraction |
| **AWS Textract** | AnalyzeDocument (Forms) | ₹4,150 ($50.00) | Form extraction |
| **AWS Textract** | AnalyzeExpense | ₹830 ($10.00) | Invoice processing |
| **Google Vision** | Document OCR | ₹125 ($1.50) | General OCR |

**Usage estimates per doctor/month:**
- Prescription OCR: ~100 pages × ₹125/1000 = ₹12.50
- Document parsing: ~50 pages × ₹125/1000 = ₹6.25

**Monthly OCR cost per doctor: ₹15 – ₹50**

**Monthly OCR cost (50 doctors): ₹750 – ₹2,500**

### 3.3 Speech-to-Text (ASR)

| Provider | Model | Price/minute | Use Case |
|----------|-------|--------------|----------|
| **Google STT V2** | Standard | ₹1.35 ($0.016) | Real-time transcription |
| **Google STT V2** | Dynamic Batch | ₹0.25 ($0.003) | Batch transcription |
| **OpenAI** | Whisper-1 | ₹0.50 ($0.006) | General audio |
| **OpenAI** | gpt-4o-mini-transcribe | ₹0.25 ($0.003) | High-volume |
| **Deepgram** | Nova-3 | ₹0.17 ($0.002) | Real-time |

**Usage estimates per doctor/month:**
- Voice notes: ~30 minutes × ₹1.35 = ₹40.50
- Consultation transcription: ~60 minutes × ₹1.35 = ₹81

**Monthly ASR cost per doctor: ₹40 – ₹120**

**Monthly ASR cost (50 doctors): ₹2,000 – ₹6,000**

### 3.4 Embeddings (Local vs API)

**Local (free after download):**
- MedCPT: ₹0 (runs on CPU)
- BGE-M3: ₹0 (runs on CPU)
- BiomedCLIP: ₹0 (runs on CPU/GPU)

**API fallback:**
- NVIDIA NIM BiomedCLIP: Free tier
- OpenAI text-embedding-3-small: ₹1.70 ($0.02)/1M tokens

**Monthly embeddings cost: ₹0 (local) – ₹500 (API fallback)**

### 3.5 AI/ML Cost Summary

| Scale | LLM | OCR | ASR | Embeddings | Total |
|-------|-----|-----|-----|------------|-------|
| **50 doctors** | ₹0 – ₹7,500 | ₹750 – ₹2,500 | ₹2,000 – ₹6,000 | ₹0 – ₹500 | **₹2,750 – ₹16,500** |
| **500 doctors** | ₹0 – ₹75,000 | ₹7,500 – ₹25,000 | ₹20,000 – ₹60,000 | ₹0 – ₹5,000 | **₹27,500 – ₹1,65,000** |
| **5,000 doctors** | ₹0 – ₹7,50,000 | ₹75,000 – ₹2,50,000 | ₹2,00,000 – ₹6,00,000 | ₹0 – ₹50,000 | **₹2,75,000 – ₹16,50,000** |

---

## 4. Security & Compliance Costs

### 4.1 DPDP Act Compliance

| Item | Cost | Notes |
|------|------|-------|
| **Data encryption at rest** | ₹0 | AWS KMS included with RDS/S3 |
| **Data encryption in transit** | ₹0 | TLS/SSL free (Let's Encrypt) |
| **Audit logging** | ₹0 | CloudWatch Logs included |
| **Consent management** | ₹0 | Built into application |
| **Data retention policies** | ₹0 | Application-level enforcement |
| **Right to erasure** | ₹0 | Application-level implementation |

**Monthly DPDP cost: ₹0 (built into infrastructure)**

### 4.2 HIPAA-Ready (Future)

| Item | Cost | Notes |
|------|------|-------|
| **AWS BAA** | ₹0 | Free with eligible services |
| **VPC isolation** | ₹0 | Already using VPC |
| **WAF** | ₹2,200/mo | Web Application Firewall |
| **GuardDuty** | ₹1,500/mo | Threat detection |
| **CloudTrail** | ₹500/mo | API audit logging |
| **KMS** | ₹100/mo | Key management |

**Monthly HIPAA cost: ₹4,300**

### 4.3 SSL & Certificates

- Let's Encrypt: ₹0 (free)
- AWS Certificate Manager: ₹0 (free with ALB/CloudFront)
- Custom SSL: ₹1,500 – ₹5,000/year

**Monthly SSL cost: ₹0 – ₹400**

---

## 5. Monitoring & Observability

### 5.1 Error Tracking

| Service | Tier | Cost | Features |
|---------|------|------|----------|
| **Sentry** | Free | ₹0 | 5K errors/month |
| **Sentry** | Team | ₹2,500/mo | 50K errors/month |
| **Sentry** | Business | ₹8,000/mo | 500K errors/month |

**Recommended:** Free tier initially, upgrade to Team at ₹2,500/mo

**Monthly error tracking: ₹0 – ₹2,500**

### 5.2 LLM Observability

| Service | Tier | Cost | Features |
|---------|------|------|----------|
| **Langfuse** | Self-hosted | ₹0 | Unlimited traces |
| **Langfuse Cloud** | Free | ₹0 | 50K traces/month |
| **Langfuse Cloud** | Pro | ₹4,000/mo | 500K traces/month |
| **LangSmith** | Developer | ₹0 | 5K traces/month |
| **LangSmith** | Plus | ₹4,000/mo | 100K traces/month |

**Recommended:** Self-hosted Langfuse (already in docker-compose)

**Monthly LLM observability: ₹0 (self-hosted) – ₹4,000 (cloud)**

### 5.3 APM & Logging

| Service | Tier | Cost | Features |
|---------|------|------|----------|
| **CloudWatch** | Basic | ₹0 | 5GB logs/month |
| **CloudWatch** | Standard | ₹500/mo | 50GB logs/month |
| **Datadog** | Free | ₹0 | 5 hosts, 1-day retention |
| **Datadog** | Pro | ₹1,500/mo | 10 hosts, 15-day retention |

**Recommended:** CloudWatch Basic + structured logging

**Monthly APM cost: ₹0 – ₹1,500**

### 5.4 Uptime Monitoring

| Service | Tier | Cost | Features |
|---------|------|------|----------|
| **UptimeRobot** | Free | ₹0 | 50 monitors |
| **BetterStack** | Free | ₹0 | 10 monitors |
| **Pingdom** | Starter | ₹1,500/mo | 10 monitors |

**Recommended:** UptimeRobot Free

**Monthly uptime monitoring: ₹0**

### 5.5 Monitoring Cost Summary

| Scale | Error Tracking | LLM Observability | APM | Uptime | Total |
|-------|----------------|-------------------|-----|--------|-------|
| **50 doctors** | ₹0 | ₹0 | ₹0 | ₹0 | **₹0** |
| **500 doctors** | ₹2,500 | ₹0 | ₹500 | ₹0 | **₹3,000** |
| **5,000 doctors** | ₹8,000 | ₹4,000 | ₹1,500 | ₹1,500 | **₹15,000** |

---

## 6. Communication Costs

### 6.1 Email (SMTP)

| Provider | Free Tier | Paid Tier | Notes |
|----------|-----------|-----------|-------|
| **Gmail SMTP** | 500/day | N/A | Personal accounts only |
| **SendGrid** | 100/day | ₹1,500/mo (50K) | Business emails |
| **AWS SES** | 62,000/month (to SES) | ₹1.50/1,000 | Cheapest at scale |
| **Mailgun** | 1,000/month | ₹500/mo (10K) | Developer-friendly |

**Usage estimates per doctor/month:**
- Booking confirmations: ~20 emails
- Prescriptions: ~10 emails
- Invoices: ~10 emails
- Reminders: ~20 emails
- Total: ~60 emails/doctor/month

**Monthly email cost:**
- 50 doctors: 3,000 emails — ₹0 (AWS SES free tier)
- 500 doctors: 30,000 emails — ₹45 (AWS SES)
- 5,000 doctors: 3,00,000 emails — ₹450 (AWS SES)

**Monthly email cost: ₹0 – ₹450**

### 6.2 SMS (India)

| Provider | Price/Message | Notes |
|----------|---------------|-------|
| **Twilio** | ₹0.45 ($0.005) | USD billing, forex surcharge |
| **MSG91** | ₹0.15 – ₹0.25 | Indian provider, DLT compliant |
| **Gupshup** | ₹0.17 | Indian provider |
| **MessageCentral** | ₹0.10 – ₹0.20 | Cheapest at volume |
| **AWS SNS** | ₹0.50 | Global provider |

**Usage estimates per doctor/month:**
- OTP verification: ~10 SMS
- Appointment reminders: ~20 SMS
- Total: ~30 SMS/doctor/month

**Monthly SMS cost:**
- 50 doctors: 1,500 SMS × ₹0.20 = ₹300
- 500 doctors: 15,000 SMS × ₹0.15 = ₹2,250
- 5,000 doctors: 1,50,000 SMS × ₹0.10 = ₹15,000

**Monthly SMS cost: ₹300 – ₹15,000**

### 6.3 WhatsApp Business API

| Provider | Per Conversation | Notes |
|----------|------------------|-------|
| **Twilio** | ₹0.80 – ₹2.50 | Global provider |
| **Gupshup** | ₹0.50 – ₹1.50 | Indian provider |
| **Wati** | ₹0.60 – ₹1.80 | Indian provider |

**Usage estimates per doctor/month:**
- Appointment confirmations: ~10 conversations
- Reminders: ~10 conversations
- Total: ~20 conversations/doctor/month

**Monthly WhatsApp cost:**
- 50 doctors: 1,000 conversations × ₹1.00 = ₹1,000
- 500 doctors: 10,000 conversations × ₹0.80 = ₹8,000
- 5,000 doctors: 1,00,000 conversations × ₹0.60 = ₹60,000

**Monthly WhatsApp cost: ₹1,000 – ₹60,000**

### 6.4 Communication Cost Summary

| Scale | Email | SMS | WhatsApp | Total |
|-------|-------|-----|----------|-------|
| **50 doctors** | ₹0 | ₹300 | ₹1,000 | **₹1,300** |
| **500 doctors** | ₹45 | ₹2,250 | ₹8,000 | **₹10,295** |
| **5,000 doctors** | ₹450 | ₹15,000 | ₹60,000 | **₹75,450** |

---

## 7. CI/CD & DevOps Costs

### 7.1 Source Control

| Service | Tier | Cost | Features |
|---------|------|------|----------|
| **GitHub** | Free | ₹0 | 2,000 CI minutes/month |
| **GitHub** | Team | ₹600/mo/user | 3,000 CI minutes/month |
| **GitLab** | Free | ₹0 | 400 CI minutes/month |

**Recommended:** GitHub Free

**Monthly source control: ₹0**

### 7.2 CI/CD Pipeline

| Service | Tier | Cost | Features |
|---------|------|------|----------|
| **GitHub Actions** | Free | ₹0 | 2,000 minutes/month |
| **GitHub Actions** | Paid | ₹0.008/minute | Beyond free tier |

**Estimated CI/CD usage:** 500 minutes/month

**Monthly CI/CD: ₹0**

### 7.3 Container Registry

| Service | Tier | Cost | Features |
|---------|------|------|----------|
| **Docker Hub** | Free | ₹0 | 1 private repo |
| **GitHub Container Registry** | Free | ₹0 | 500 MB storage |
| **AWS ECR** | Free | ₹0 | 500 MB storage (12 months) |

**Recommended:** GitHub Container Registry

**Monthly container registry: ₹0**

### 7.4 Infrastructure as Code

| Tool | Cost | Notes |
|------|------|-------|
| **Terraform** | ₹0 | Open source |
| **AWS CloudFormation** | ₹0 | Free with AWS |
| **Pulumi** | ₹0 | Open source |

**Monthly IaC: ₹0**

### 7.5 DevOps Cost Summary

| Scale | Source Control | CI/CD | Registry | IaC | Total |
|-------|----------------|-------|----------|-----|-------|
| **All scales** | ₹0 | ₹0 | ₹0 | ₹0 | **₹0** |

---

## 8. Total Cost Summary

### 8.1 Monthly Cost by Scale

| Category | 50 Doctors | 500 Doctors | 5,000 Doctors |
|----------|------------|-------------|---------------|
| **Compute (EC2)** | ₹8,300 | ₹14,200 | ₹75,000 |
| **Database (RDS)** | ₹9,000 | ₹18,000 | ₹90,000 |
| **Cache (Redis)** | ₹4,500 | ₹4,500 | ₹9,000 |
| **Vector DB** | ₹0 | ₹2,500 | ₹5,500 |
| **Storage (S3)** | ₹500 | ₹2,000 | ₹10,000 |
| **CDN + ALB** | ₹2,700 | ₹4,500 | ₹15,000 |
| **AI/ML APIs** | ₹2,750 | ₹27,500 | ₹2,75,000 |
| **Email** | ₹0 | ₹45 | ₹450 |
| **SMS** | ₹300 | ₹2,250 | ₹15,000 |
| **WhatsApp** | ₹1,000 | ₹8,000 | ₹60,000 |
| **Monitoring** | ₹0 | ₹3,000 | ₹15,000 |
| **Domain + SSL** | ₹125 | ₹125 | ₹500 |
| **Miscellaneous** | ₹1,000 | ₹5,000 | ₹25,000 |
| **TOTAL** | **₹30,175** | **₹91,570** | **₹5,95,450** |
| **TOTAL (USD)** | ~$360 | ~$1,100 | ~$7,150 |

### 8.2 Cost Per Doctor

| Scale | Cost/Doctor/Month | Revenue/Doctor/Month | Gross Margin |
|-------|-------------------|----------------------|--------------|
| **50 doctors** | ₹603 | ₹2,500 | 76% |
| **500 doctors** | ₹183 | ₹3,000 | 94% |
| **5,000 doctors** | ₹119 | ₹3,500 | 97% |

### 8.3 Annual Cost Projection

| Year | Doctors | Monthly Cost | Annual Cost | Revenue | Profit |
|------|---------|--------------|-------------|---------|--------|
| **Year 1** | 50 | ₹30,175 | ₹3,62,100 | ₹15,00,000 | ₹11,37,900 |
| **Year 2** | 500 | ₹91,570 | ₹10,98,840 | ₹1,80,00,000 | ₹1,69,01,160 |
| **Year 3** | 5,000 | ₹5,95,450 | ₹71,45,400 | ₹21,00,00,000 | ₹20,28,54,600 |

---

## 9. Cost Optimization Strategies

### 9.1 Reserved Instances & Savings Plans

| Strategy | Savings | Commitment |
|----------|---------|------------|
| **1-Year RI** | 30-40% | 1 year |
| **3-Year RI** | 50-60% | 3 years |
| **Savings Plans** | 20-30% | 1 year |
| **Spot Instances** | 50-90% | Variable |

**Recommended:** 1-Year RI for baseline, Spot for batch workloads

### 9.2 AI/ML Cost Optimization

| Strategy | Savings | Trade-off |
|----------|---------|-----------|
| **Use free tiers first** | 100% | Rate limits |
| **Batch API calls** | 50% | Latency |
| **Cache embeddings** | 80% | Storage |
| **Local models** | 100% | GPU needed |
| **Right-size models** | 30-50% | Quality |

### 9.3 Database Optimization

| Strategy | Savings | Implementation |
|----------|---------|----------------|
| **Connection pooling** | 30% | PgBouncer |
| **Query optimization** | 20% | Indexing, EXPLAIN |
| **Read replicas** | 40% | Separate reads |
| **Archival** | 50% | Move old data to S3 |

### 9.4 Storage Optimization

| Strategy | Savings | Implementation |
|----------|---------|----------------|
| **Lifecycle policies** | 40% | Auto-tier to IA/Glacier |
| **Compression** | 60% | Compress before storage |
| **Deduplication** | 30% | Hash-based dedup |

---

## 10. Scaling Considerations

### 10.1 Horizontal Scaling

| Component | Scaling Strategy | Trigger |
|-----------|------------------|---------|
| **Backend** | Add EC2 instances + ALB | CPU > 70% |
| **Worker** | Add arq worker instances | Queue depth > 100 |
| **Database** | Read replicas | Read latency > 100ms |
| **Cache** | Cluster mode | Memory > 80% |
| **Vector DB** | Sharding | Vectors > 10M |

### 10.2 Vertical Scaling Limits

| Component | Max Instance | Cost |
|-----------|--------------|------|
| **EC2** | m6i.4xlarge (16 vCPU, 64 GB) | ₹60,000/mo |
| **RDS** | db.r6i.2xlarge (8 vCPU, 64 GB) | ₹1,20,000/mo |
| **Redis** | cache.r6i.xlarge (26 GB) | ₹50,000/mo |

### 10.3 Auto-Scaling Rules

```yaml
# Backend auto-scaling
Scale Up: CPU > 70% for 5 minutes
Scale Down: CPU < 30% for 15 minutes
Min instances: 2
Max instances: 10

# Worker auto-scaling
Scale Up: Queue depth > 100 for 2 minutes
Scale Down: Queue depth < 10 for 10 minutes
Min instances: 1
Max instances: 5
```

---

## 11. Funding Requirements

### 11.1 Seed Funding (Pre-Revenue)

| Item | Amount | Purpose |
|------|--------|---------|
| **Infrastructure (6 months)** | ₹1,80,000 | AWS costs during development |
| **API credits** | ₹50,000 | NIM/Groq free tiers + backup |
| **Domain & SSL** | ₹5,000 | Domain registration |
| **Monitoring tools** | ₹15,000 | Sentry, Langfuse |
| **Development tools** | ₹30,000 | IDE, plugins, services |
| **Marketing** | ₹50,000 | Landing page, ads |
| **Legal & compliance** | ₹25,000 | Company registration, DPDP |
| **Contingency (20%)** | ₹71,000 | Unexpected costs |
| **TOTAL SEED** | **₹4,26,000** | ~$5,100 |

### 11.2 Series A (Growth)

| Item | Amount (Annual) | Purpose |
|------|-----------------|---------|
| **Infrastructure** | ₹12,00,000 | Scaling to 500 doctors |
| **Team (3 engineers)** | ₹36,00,000 | ₹1L/month each |
| **Marketing** | ₹6,00,000 | Customer acquisition |
| **Sales** | ₹3,60,000 | 1 sales person |
| **Office & admin** | ₹2,40,000 | Co-working space |
| **Legal & compliance** | ₹1,20,000 | Audits, certifications |
| **TOTAL SERIES A** | **₹61,20,000** | ~$73,500 |

### 11.3 Break-Even Analysis

| Metric | Value |
|--------|-------|
| **Fixed costs/month** | ₹1,50,000 |
| **Variable cost/doctor** | ₹200/month |
| **Revenue/doctor** | ₹3,000/month |
| **Contribution margin** | ₹2,800/month |
| **Break-even doctors** | 54 doctors |
| **Time to break-even** | 8-12 months (from launch) |

---

## 12. Recommendations

### 12.1 Phase 1: MVP Launch (0-50 doctors)

**Budget: ₹50,000/month**

1. Use **free tiers** for all AI/ML APIs (NIM, Groq)
2. **Self-host** Qdrant on EC2
3. **AWS SES** for email (free tier)
4. **MSG91** for SMS (₹0.15/msg)
5. **UptimeRobot Free** for monitoring
6. **GitHub Free** for CI/CD

### 12.2 Phase 2: Growth (50-500 doctors)

**Budget: ₹1,50,000/month**

1. **1-Year RI** for EC2/RDS (30% savings)
2. **Upgrade to paid tiers** for Sentry, Langfuse
3. **AWS SES** for email at scale
4. **Add WAF** for security
5. **Implement auto-scaling**

### 12.3 Phase 3: Scale (500-5,000 doctors)

**Budget: ₹10,00,000/month**

1. **3-Year RI** for baseline (50% savings)
2. **Spot instances** for batch workloads
3. **Multi-AZ** for all services
4. **Dedicated DevOps engineer**
5. **Enterprise support** from AWS

---

## 13. Risk Mitigation

### 13.1 Cost Overrun Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **API usage spike** | Medium | High | Rate limits, budgets, alerts |
| **Storage growth** | Low | Medium | Lifecycle policies, quotas |
| **Traffic spike** | Medium | High | Auto-scaling, CDN caching |
| **API price increase** | Low | Medium | Multi-provider strategy |

### 13.2 Cost Monitoring

1. **AWS Budgets** — Set monthly alerts at 50%, 80%, 100%
2. **Cost Explorer** — Daily monitoring
3. **Tagging** — Track costs by service, environment, doctor
4. **Alerts** — Slack/SMS notifications for anomalies

---

## 14. Appendix

### 14.1 AWS Mumbai Pricing (as of July 2026)

- EC2 t3.medium: ₹3.40/hr on-demand
- RDS db.t3.medium: ₹12.50/hr on-demand
- ElastiCache cache.t3.medium: ₹6.25/hr on-demand
- S3 Standard: ₹1.75/GB/month
- Data transfer out: ₹6.50/GB

### 14.2 AI/ML API Pricing (as of July 2026)

- NVIDIA NIM: Free tier (1000 credits)
- Groq: Free tier (14,400 req/day)
- OpenAI GPT-4o: $2.50/$10.00 per 1M tokens
- AWS Textract: $1.50 per 1,000 pages
- Google STT: $0.016 per minute

### 14.3 SMS Pricing India (as of July 2026)

- Twilio: ₹0.45/SMS (with forex)
- MSG91: ₹0.15-0.25/SMS
- MessageCentral: ₹0.10-0.20/SMS

---

**Document prepared by:** SoloPrac AI Team
**Last updated:** July 2026
**Next review:** October 2026
