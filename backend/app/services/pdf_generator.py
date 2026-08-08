"""Shared PDF Generation Pipeline — Jinja2 → Playwright → PDF → S3.

Single pipeline for all three document types (Prescription, Invoice, Certificate).
Each type has a Jinja2 template with clinic letterhead, inline Tailwind CSS,
and a shared Playwright rendering step.

Clinic branding is pulled dynamically from the Doctor model — every doctor
gets their own clinic name, address, phone, and registration on their PDFs.

Usage:
    from app.services.pdf_generator import PDFGenerator
    pdf = PDFGenerator()
    s3_key = await pdf.generate_prescription(data, db=db, doctor_id=doc.id)
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from jinja2 import BaseLoader, Environment, TemplateNotFound
from playwright.async_api import async_playwright
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.storage import storage_service

logger = logging.getLogger(__name__)

# ─── Jinja2 Templates (inline) ─────────────────────

PRESCRIPTION_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { font-family: 'Inter', Arial, sans-serif; font-size: 11pt; line-height: 1.4; margin: 0; padding: 20px; color: #1a1a1a; }
  .letterhead { text-align: center; border-bottom: 2px solid #2563eb; padding-bottom: 8px; margin-bottom: 16px; }
  .letterhead .logo { max-height: 56px; max-width: 200px; margin: 0 auto 4px auto; display: block; object-fit: contain; }
  .letterhead .name { font-size: 16pt; font-weight: bold; color: #1e40af; }
  .letterhead .details { font-size: 8pt; color: #64748b; }
  .state-header { font-size: 8pt; color: #1e40af; font-weight: bold; margin-top: 4px; }
  .state-footer { font-size: 7pt; color: #64748b; font-style: italic; margin-top: 4px; }
  .header { display: flex; justify-content: space-between; margin-bottom: 12px; font-size: 9pt; }
  .rx-box { border: 2px solid #eab308; background: #fffbeb; padding: 16px; border-radius: 8px; margin: 12px 0; }
  .rx-box h3 { margin: 0 0 8px 0; font-size: 10pt; color: #92400e; }
  table { width: 100%; border-collapse: collapse; font-size: 9pt; }
  table th { background: #f1f5f9; text-align: left; padding: 4px 6px; border-bottom: 1px solid #e2e8f0; }
  table td { padding: 4px 6px; border-bottom: 1px solid #f1f5f9; }
  .warning-pill { display: inline-block; background: #fef2f2; color: #dc2626; padding: 1px 6px; border-radius: 4px; font-size: 8pt; }
  .signature-block { margin-top: 20px; text-align: right; }
  .signature-block img { max-height: 44px; max-width: 160px; display: inline-block; }
  .signature-line { border-top: 1px solid #94a3b8; width: 160px; margin-left: auto; margin-top: 2px; padding-top: 2px; font-size: 8pt; color: #94a3b8; }
  .footer { margin-top: 20px; font-size: 8pt; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 8px; }
  .disclaimer { font-size: 7pt; color: #94a3b8; text-align: center; margin-top: 4px; font-style: italic; }
</style></head><body>
<div class="letterhead">
  {% if clinic.clinic_logo_data_uri %}<img class="logo" src="{{ clinic.clinic_logo_data_uri }}" alt="Clinic logo" />{% endif %}
  <div class="name">{{ clinic.clinic_name }}</div>
  <div class="details">{{ clinic.clinic_address }} | {{ clinic.clinic_phone }} | {{ clinic.clinic_email }}</div>
  {% if clinic.state_header %}<div class="state-header">{{ clinic.state_header }}</div>{% endif %}
</div>
<div class="header">
  <div><strong>Patient:</strong> {{ patient_name }}<br><strong>Age/Sex:</strong> {{ patient_age }}/{{ patient_gender }}<br><strong>Date:</strong> {{ date }}</div>
  <div><strong>Doctor:</strong> {{ clinic.doctor_name }}<br><strong>Reg No:</strong> {{ clinic.registration_number }}</div>
</div>
<div class="rx-box">
  <h3>Prescription</h3>
  {% if diagnosis %}<p><strong>Diagnosis:</strong> {{ diagnosis }}</p>{% endif %}
  <table><tr><th>#</th><th>Drug</th><th>Strength</th><th>Dose</th><th>Frequency</th><th>Duration</th></tr>
  {% for med in medications %}
  <tr><td>{{ loop.index }}</td><td>{{ med.drug }}</td><td>{{ med.strength }}</td><td>{{ med.dose }}</td><td>{{ med.frequency }}</td><td>{{ med.duration }}</td></tr>
  {% endfor %}
  </table>
  {% if instructions %}<p style="margin-top:8px;"><strong>Instructions:</strong> {{ instructions }}</p>{% endif %}
  {% if follow_up %}<p><strong>Follow-up:</strong> {{ follow_up }}</p>{% endif %}
</div>
<div class="signature-block">
  {% if clinic.signature_data_uri %}<img src="{{ clinic.signature_data_uri }}" alt="Signature" />{% endif %}
  <div class="signature-line">Dr. {{ clinic.doctor_name }}{% if clinic.registration_number %} · Reg. {{ clinic.registration_number }}{% endif %}</div>
</div>
<div class="footer">This is an AI-assisted draft — validated by Dr. {{ clinic.doctor_name }}. Not a substitute for clinical judgement.</div>
{% if clinic.state_footer %}<div class="state-footer">{{ clinic.state_footer }}</div>{% endif %}
<div class="disclaimer">Verified by AI · Doctor review recommended. Generated by SoloPrac AI on {{ now }}.</div>
</body></html>"""

INVOICE_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { font-family: 'Inter', Arial, sans-serif; font-size: 11pt; margin: 0; padding: 20px; color: #1a1a1a; }
  .letterhead { text-align: center; border-bottom: 2px solid #2563eb; padding-bottom: 8px; margin-bottom: 16px; }
  .letterhead .logo { max-height: 56px; max-width: 200px; margin: 0 auto 4px auto; display: block; object-fit: contain; }
  .letterhead .name { font-size: 16pt; font-weight: bold; color: #1e40af; }
  .letterhead .details { font-size: 8pt; color: #64748b; }
  .header { display: flex; justify-content: space-between; margin-bottom: 12px; font-size: 9pt; }
  .inv-no { font-size: 12pt; font-weight: bold; color: #1e40af; margin-bottom: 8px; }
  table { width: 100%; border-collapse: collapse; font-size: 9pt; }
  table th { background: #f1f5f9; text-align: left; padding: 6px; border-bottom: 2px solid #2563eb; }
  table td { padding: 6px; border-bottom: 1px solid #e2e8f0; }
  .totals { margin-top: 8px; text-align: right; font-size: 10pt; }
  .totals .total { font-size: 14pt; font-weight: bold; color: #1e40af; }
  .status-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 8pt; font-weight: bold; }
  .status-paid { background: #dcfce7; color: #16a34a; }
  .status-pending { background: #fef9c3; color: #ca8a04; }
  .payment { margin-top: 12px; font-size: 9pt; }
  .amount-words { margin-top: 8px; font-size: 9pt; color: #475569; font-style: italic; }
  .footer { margin-top: 20px; font-size: 8pt; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 8px; }
  .qr { text-align: center; margin-top: 12px; font-size: 8pt; color: #64748b; }
</style></head><body>
<div class="letterhead">
  {% if clinic.clinic_logo_data_uri %}<img class="logo" src="{{ clinic.clinic_logo_data_uri }}" alt="Clinic logo" />{% endif %}
  <div class="name">{{ clinic.clinic_name }}</div>
  <div class="details">{{ clinic.clinic_address }} | {{ clinic.clinic_phone }} | {{ clinic.clinic_email }}</div>
</div>
<div class="inv-no">Invoice: {{ invoice_number }}</div>
<div class="header">
  <div><strong>Patient:</strong> {{ patient_name }}<br><strong>Date:</strong> {{ date }}</div>
  <div><strong>Status:</strong> <span class="status-badge status-{{ status }}">{{ status|upper }}</span></div>
</div>
<table><tr><th>#</th><th>Description</th><th>Amount</th></tr>
{% for item in items %}
<tr><td>{{ loop.index }}</td><td>{{ item.description }}</td><td>₹{{ item.amount }}</td></tr>
{% endfor %}
</table>
<div class="totals">
  <p class="total">Total: ₹{{ total }}</p>
</div>
{% if payment_method %}
<div class="payment">
  <strong>Paid via:</strong> {{ payment_method|upper }}
</div>
{% endif %}
{% if amount_in_words %}
<div class="amount-words">{{ amount_in_words }}</div>
{% endif %}
{% if upi_id %}
<div class="qr">UPI ID: {{ upi_id }}</div>
{% endif %}
{% if notes %}<p style="font-size:9pt;margin-top:8px;"><strong>Notes:</strong> {{ notes }}</p>{% endif %}
<div style="margin-top:24px;text-align:right;">
  {% if clinic.signature_data_uri %}<img src="{{ clinic.signature_data_uri }}" alt="Signature" style="max-height:44px;max-width:160px;display:inline-block;" />{% endif %}
  <p style="font-size:9pt;">{{ clinic.doctor_name }}{% if clinic.registration_number %}, Reg. {{ clinic.registration_number }}{% endif %}</p>
  <div style="border-top:1px solid #94a3b8;width:150px;margin-left:auto;margin-top:4px;padding-top:4px;font-size:8pt;color:#94a3b8;">Signature</div>
</div>
<div class="footer">Generated by SoloPrac AI on {{ now }}. Thank you for your visit.</div>
<div class="disclaimer" style="font-size:7pt;color:#94a3b8;text-align:center;font-style:italic;">Verified by AI · Doctor review recommended.</div>
</body></html>"""

CERTIFICATE_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { font-family: 'Inter', Arial, sans-serif; font-size: 11pt; margin: 0; padding: 20px; color: #1a1a1a; }
  .letterhead { text-align: center; border-bottom: 2px solid #2563eb; padding-bottom: 8px; margin-bottom: 16px; }
  .letterhead .logo { max-height: 56px; max-width: 200px; margin: 0 auto 4px auto; display: block; object-fit: contain; }
  .letterhead .name { font-size: 16pt; font-weight: bold; color: #1e40af; }
  .letterhead .details { font-size: 8pt; color: #64748b; }
  h2 { text-align: center; color: #1e40af; font-size: 14pt; margin: 16px 0; }
  .content { margin: 16px 0; line-height: 1.6; font-size: 10pt; }
  .qr { text-align: center; margin: 16px 0; }
  .qr img { width: 80px; height: 80px; }
  .verify { text-align: center; font-size: 8pt; color: #64748b; }
  .footer { margin-top: 20px; font-size: 8pt; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 8px; }
</style></head><body>
<div class="letterhead">
  {% if clinic.clinic_logo_data_uri %}<img class="logo" src="{{ clinic.clinic_logo_data_uri }}" alt="Clinic logo" />{% endif %}
  <div class="name">{{ clinic.clinic_name }}</div>
  <div class="details">{{ clinic.clinic_address }} | {{ clinic.clinic_phone }} | {{ clinic.clinic_email }}</div>
</div>
<h2>Medical Certificate</h2>
<p style="text-align:center;font-size:9pt;color:#64748b;">{{ cert_type | replace('_', ' ') | title }}</p>
<div class="content">
  <p><strong>Patient:</strong> {{ patient_name }}</p>
  <p><strong>Date:</strong> {{ date }}</p>
  <p><strong>This is to certify that</strong> {{ patient_name }} {% if patient_age %} ({{ patient_age }} years) {% endif %} is under my medical care.</p>
  {% if body %}<p>{{ body }}</p>{% endif %}
  {% if recommended_rest %}<p><strong>Recommended rest:</strong> {{ recommended_rest }}</p>{% endif %}
</div>
<div class="qr">
  {% if verification_code %}<p style="font-size:9pt;">Verification Code: <strong>{{ verification_code }}</strong></p>{% endif %}
  <p class="verify">Verify at: {{ verify_url }}</p>
</div>
<div style="margin-top:24px;text-align:right;">
  {% if clinic.signature_data_uri %}<img src="{{ clinic.signature_data_uri }}" alt="Signature" style="max-height:44px;max-width:160px;display:inline-block;" />{% endif %}
  <p>{{ clinic.doctor_name }}</p>
  <p style="font-size:9pt;color:#64748b;">{{ clinic.registration_number }}</p>
  <p style="font-size:9pt;color:#64748b;">{{ clinic.clinic_name }}</p>
</div>
<div class="footer">Generated by SoloPrac AI on {{ now }}. This is a computer-generated certificate.</div>
<div class="disclaimer" style="font-size:7pt;color:#94a3b8;text-align:center;font-style:italic;">Verified by AI · Doctor review recommended.</div>
</body></html>"""

# ─── Weekly Report Template ──────────────────────────

WEEKLY_REPORT_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  body { font-family: 'Inter', Arial, sans-serif; font-size: 10pt; line-height: 1.5; margin: 0; padding: 20px; color: #1a1a1a; }
  .letterhead { text-align: center; border-bottom: 3px solid #2563eb; padding-bottom: 10px; margin-bottom: 20px; }
  .letterhead .logo { max-height: 64px; max-width: 220px; margin: 0 auto 6px auto; display: block; object-fit: contain; }
  .letterhead .name { font-size: 18pt; font-weight: bold; color: #1e40af; }
  .letterhead .details { font-size: 8pt; color: #64748b; margin-top: 4px; }
  .report-header { margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid #e2e8f0; }
  .report-header h1 { font-size: 14pt; color: #1e40af; margin: 0 0 4px 0; text-align: center; }
  .report-header .subtitle { font-size: 9pt; color: #64748b; text-align: center; margin: 4px 0; }
  .patient-info { display: flex; justify-content: space-between; margin-bottom: 16px; font-size: 9pt; padding: 8px; background: #f8fafc; border-radius: 6px; }
  .patient-info div { line-height: 1.6; }
  .section { margin-bottom: 16px; }
  .section-title { font-size: 10pt; font-weight: bold; color: #1e40af; padding-bottom: 4px; border-bottom: 1px solid #e2e8f0; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
  .section-title .badge { font-size: 7pt; padding: 1px 6px; border-radius: 4px; font-weight: bold; text-transform: uppercase; }
  .badge-critical { background: #fef2f2; color: #dc2626; }
  .badge-notable { background: #fffbeb; color: #ca8a04; }
  .badge-routine { background: #dbeafe; color: #2563eb; }
  .badge-informational { background: #f1f5f9; color: #64748b; }
  .event { margin-bottom: 10px; padding: 8px; background: #fafafa; border-radius: 6px; border-left: 3px solid #e2e8f0; }
  .event-critical { border-left-color: #dc2626; background: #fef2f2; }
  .event-notable { border-left-color: #ca8a04; background: #fffbeb; }
  .event-routine { border-left-color: #2563eb; background: #eff6ff; }
  .event-informational { border-left-color: #94a3b8; background: #f8fafc; }
  .event-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
  .event-date { font-size: 8pt; color: #64748b; font-weight: 500; }
  .event-summary { font-size: 9pt; color: #1a1a1a; line-height: 1.5; }
  .event-meta { font-size: 7.5pt; color: #64748b; margin-top: 4px; display: flex; gap: 12px; flex-wrap: wrap; }
  .event-meta span { background: #f1f5f9; padding: 1px 6px; border-radius: 3px; }
  .score-breakdown { font-size: 7pt; color: #94a3b8; margin-top: 4px; }
  .images-section { margin-top: 20px; }
  .images-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 8px; margin-top: 8px; }
  .image-card { border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden; background: #fff; }
  .image-card img { width: 100%; height: 90px; object-fit: cover; }
  .image-card .caption { font-size: 7pt; padding: 4px; color: #64748b; text-align: center; background: #f8fafc; border-top: 1px solid #e2e8f0; }
  .footer { margin-top: 30px; font-size: 7pt; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 12px; }
  .disclaimer { font-size: 6.5pt; color: #94a3b8; text-align: center; margin-top: 4px; font-style: italic; }
  .signature-block { margin-top: 24px; text-align: right; font-size: 9pt; }
  .qr-section { text-align: center; margin-top: 16px; }
  .qr-section img { width: 70px; height: 70px; }
  .qr-section p { font-size: 7pt; color: #64748b; margin-top: 4px; }
</style></head><body>
<div class="letterhead">
  {% if clinic.clinic_logo_data_uri %}<img class="logo" src="{{ clinic.clinic_logo_data_uri }}" alt="Clinic logo" />{% endif %}
  <div class="name">{{ clinic.clinic_name }}</div>
  <div class="details">{{ clinic.clinic_address }} | {{ clinic.clinic_phone }} | {{ clinic.clinic_email }}</div>
</div>

<div class="report-header">
  <h1>{{ title }}</h1>
  <div class="subtitle">{{ description }}</div>
  <div class="subtitle">Period: {{ period_start }} to {{ period_end }} | Generated: {{ generated_at }}</div>
</div>

<div class="patient-info">
  <div><strong>Patient:</strong> {{ patient_name }}<br><strong>Age/Sex:</strong> {{ patient_age }}/{{ patient_gender }}<br><strong>MRN:</strong> {{ patient_mrn }}</div>
  <div><strong>Doctor:</strong> {{ clinic.doctor_name }}<br><strong>Reg No:</strong> {{ clinic.registration_number }}</div>
</div>

{% if layout == "clinical" %}
  {% if critical %}
  <div class="section">
    <div class="section-title">
      <span class="badge badge-critical">Critical ({{ critical_count }})</span>
      Critical Findings
    </div>
    {% for e in critical %}
    <div class="event event-critical">
      <div class="event-header"><span class="event-date">{{ e.date }}</span></div>
      <div class="event-summary">{{ e.summary }}</div>
      <div class="event-meta">
        <span>v{{ e.version }}</span>
        <span>Score: {{ e.score }}</span>
        <span>Tier: {{ e.tier }}</span>
        {% if e.edit_type %}<span>{{ e.edit_type }}</span>{% endif %}
      </div>
      {% if e.components %}
      <div class="score-breakdown">
        {% for k, v in e.components.items() %}{{ k }}: {{ v }} {% endfor %}
      </div>
      {% endif %}
    </div>
    {% endfor %}
  </div>
  {% endif %}

  {% if notable %}
  <div class="section">
    <div class="section-title">
      <span class="badge badge-notable">Notable ({{ notable_count }})</span>
      Notable Findings
    </div>
    {% for e in notable %}
    <div class="event event-notable">
      <div class="event-header"><span class="event-date">{{ e.date }}</span></div>
      <div class="event-summary">{{ e.summary }}</div>
      <div class="event-meta">
        <span>v{{ e.version }}</span>
        <span>Score: {{ e.score }}</span>
        <span>Tier: {{ e.tier }}</span>
        {% if e.edit_type %}<span>{{ e.edit_type }}</span>{% endif %}
      </div>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  {% if routine %}
  <div class="section">
    <div class="section-title">
      <span class="badge badge-routine">Routine ({{ routine_count }})</span>
      Routine Events
    </div>
    {% for e in routine %}
    <div class="event event-routine">
      <div class="event-header"><span class="event-date">{{ e.date }}</span></div>
      <div class="event-summary">{{ e.summary }}</div>
      <div class="event-meta"><span>v{{ e.version }}</span><span>Score: {{ e.score }}</span></div>
    </div>
    {% endfor %}
  </div>
  {% endif %}
{% endif %}

{% if layout == "executive" %}
  <div class="section">
    <div class="section-title">Key Findings</div>
    {% for e in sections %}
    <div class="event event-{{ e.tier }}">
      <div class="event-header"><span class="event-date">{{ e.date }}</span></div>
      <div class="event-summary">{{ e.summary }}</div>
      <div class="event-meta"><span>Score: {{ e.score }}</span><span>Tier: {{ e.tier }}</span></div>
    </div>
    {% endfor %}
  </div>
{% endif %}

{% if layout == "family_friendly" %}
  <div class="section">
    <div class="section-title">Your Health Summary</div>
    <p style="font-size: 9pt; color: #374151; margin-bottom: 12px;">{{ introduction }}</p>
    {% for e in sections %}
    <div class="event event-{{ e.tier }}">
      <div class="event-header"><span class="event-date">{{ e.date }}</span></div>
      <div class="event-summary" style="font-size: 9.5pt;">{{ e.summary }}</div>
    </div>
    {% endfor %}
  </div>
{% endif %}

{% if images and images|length > 0 %}
<div class="images-section">
  <div class="section-title">Clinical Images</div>
  <div class="images-grid">
    {% for img in images %}
    <div class="image-card">
      <img src="{{ img.url }}" alt="{{ img.caption }}">
      <div class="caption">{{ img.caption }}</div>
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}

<div class="signature-block">
  <p>{{ clinic.doctor_name }}</p>
  <p style="font-size: 8pt; color: #64748b;">{{ clinic.registration_number }}</p>
  <p style="font-size: 8pt; color: #64748b;">{{ clinic.clinic_name }}</p>
</div>

{% if qr_code %}
<div class="qr-section">
  <img src="{{ qr_code }}" alt="Verification QR Code">
  <p>Verify at: {{ verify_url }}</p>
</div>
{% endif %}

<div class="footer">
  Generated by SoloPrac AI on {{ now }} | {{ clinic.clinic_name }}
</div>
<div class="disclaimer">Verified by AI · Doctor review recommended. This report is computer-generated and should be reviewed by a healthcare professional.</div>
</body></html>"""


# ─── Template Loader ────────────────────────────────


class _InlineLoader(BaseLoader):
    def __init__(self):
        self.templates = {
            "prescription": PRESCRIPTION_TEMPLATE,
            "invoice": INVOICE_TEMPLATE,
            "certificate": CERTIFICATE_TEMPLATE,
            "weekly_report": WEEKLY_REPORT_TEMPLATE,
        }

    def get_source(self, environment, template):
        if template in self.templates:
            return self.templates[template], template, None
        raise TemplateNotFound(template)


_jinja_env = Environment(loader=_InlineLoader(), autoescape=True)


# ─── PDF Generator ──────────────────────────────────

# Fallback clinic defaults when no doctor info is available
FALLBACK_CLINIC = {
    "clinic_name": "SoloPrac Clinic",
    "clinic_address": "Aundh, Pune, Maharashtra",
    "clinic_phone": "+91-9876543210",
    "clinic_email": "clinic@soloprac.ai",
    "doctor_name": "Doctor",
    "registration_number": "",
}

# State-specific prescription header/footer requirements
STATE_PRESCRIPTION_OVERRIDES = {
    "Tamil Nadu": {
        "header_text": "Registered Medical Practitioner — Tamil Nadu Medical Council",
        "footer_text": "This prescription is issued under the Tamil Nadu Medical Registration Act.",
    },
    "Karnataka": {
        "header_text": "Registered Medical Practitioner — Karnataka Medical Council",
        "footer_text": "This prescription is issued under the Karnataka Medical Registration Act.",
    },
    "Maharashtra": {
        "header_text": "Registered Medical Practitioner — Maharashtra Medical Council",
        "footer_text": "This prescription is issued under the Maharashtra Medical Registration Act.",
    },
    "Delhi": {
        "header_text": "Registered Medical Practitioner — Delhi Medical Council",
        "footer_text": "This prescription is issued under the Delhi Medical Registration Act.",
    },
    "Uttar Pradesh": {
        "header_text": "Registered Medical Practitioner — UP Medical Council",
        "footer_text": "This prescription is issued under the UP Medical Registration Act.",
    },
    "Gujarat": {
        "header_text": "Registered Medical Practitioner — Gujarat Medical Council",
        "footer_text": "This prescription is issued under the Gujarat Medical Registration Act.",
    },
    "Rajasthan": {
        "header_text": "Registered Medical Practitioner — Rajasthan Medical Council",
        "footer_text": "This prescription is issued under the Rajasthan Medical Registration Act.",
    },
    "West Bengal": {
        "header_text": "Registered Medical Practitioner — West Bengal Medical Council",
        "footer_text": "This prescription is issued under the West Bengal Medical Registration Act.",
    },
    "Kerala": {
        "header_text": "Registered Medical Practitioner — Kerala Medical Council",
        "footer_text": "This prescription is issued under the Kerala Medical Registration Act.",
    },
    "Andhra Pradesh": {
        "header_text": "Registered Medical Practitioner — AP Medical Council",
        "footer_text": "This prescription is issued under the AP Medical Registration Act.",
    },
    "Telangana": {
        "header_text": "Registered Medical Practitioner — Telangana Medical Council",
        "footer_text": "This prescription is issued under the Telangana Medical Registration Act.",
    },
    "Madhya Pradesh": {
        "header_text": "Registered Medical Practitioner — MP Medical Council",
        "footer_text": "This prescription is issued under the MP Medical Registration Act.",
    },
    "Bihar": {
        "header_text": "Registered Medical Practitioner — Bihar Medical Council",
        "footer_text": "This prescription is issued under the Bihar Medical Registration Act.",
    },
    "Punjab": {
        "header_text": "Registered Medical Practitioner — Punjab Medical Council",
        "footer_text": "This prescription is issued under the Punjab Medical Registration Act.",
    },
    "Haryana": {
        "header_text": "Registered Medical Practitioner — Haryana Medical Council",
        "footer_text": "This prescription is issued under the Haryana Medical Registration Act.",
    },
    "Odisha": {
        "header_text": "Registered Medical Practitioner — Odisha Medical Council",
        "footer_text": "This prescription is issued under the Odisha Medical Registration Act.",
    },
    "Jharkhand": {
        "header_text": "Registered Medical Practitioner — Jharkhand Medical Council",
        "footer_text": "This prescription is issued under the Jharkhand Medical Registration Act.",
    },
    "Chhattisgarh": {
        "header_text": "Registered Medical Practitioner — Chhattisgarh Medical Council",
        "footer_text": "This prescription is issued under the Chhattisgarh Medical Registration Act.",
    },
    "Assam": {
        "header_text": "Registered Medical Practitioner — Assam Medical Council",
        "footer_text": "This prescription is issued under the Assam Medical Registration Act.",
    },
    "Uttarakhand": {
        "header_text": "Registered Medical Practitioner — Uttarakhand Medical Council",
        "footer_text": "This prescription is issued under the Uttarakhand Medical Registration Act.",
    },
    "Himachal Pradesh": {
        "header_text": "Registered Medical Practitioner — HP Medical Council",
        "footer_text": "This prescription is issued under the HP Medical Registration Act.",
    },
    "Goa": {
        "header_text": "Registered Medical Practitioner — Goa Medical Council",
        "footer_text": "This prescription is issued under the Goa Medical Registration Act.",
    },
    "Jammu and Kashmir": {
        "header_text": "Registered Medical Practitioner — J&K Medical Council",
        "footer_text": "This prescription is issued under the J&K Medical Registration Act.",
    },
    "Chandigarh": {
        "header_text": "Registered Medical Practitioner — Chandigarh Medical Council",
        "footer_text": "This prescription is issued under the Chandigarh Medical Registration Act.",
    },
}


class PDFGenerator:
    """Shared Jinja2 → Playwright → PDF → S3 generation for all document types.

    Clinic branding is pulled from the Doctor model dynamically.
    Pass db + doctor_id to use real doctor branding; omitting them
    falls back to default values.

    P0.6 optimization: we keep a single persistent Playwright browser alive
    across all PDF renders instead of launching one per call. Chromium launch
    is 2-5 seconds — doing it per PDF was the biggest single-request latency
    bottleneck in the prescription/invoice/certificate paths.
    """

    # Class-level browser handle — one per process. Async-safe because we
    # guard init with an asyncio.Lock.
    _playwright = None
    _browser = None
    _browser_lock = None  # asyncio.Lock — lazy-created (see __init__)

    def __init__(self):
        # Lazy-create the lock only when we actually have a running loop.
        # Storing it on the class is fine because uvicorn workers each get
        # their own process → their own class-level state.
        import asyncio as _asyncio

        if PDFGenerator._browser_lock is None:
            PDFGenerator._browser_lock = _asyncio.Lock()

    @classmethod
    async def _get_browser(cls):
        """Return the shared Chromium browser, launching it once on first use.

        Called from _render_to_pdf. Uses an asyncio.Lock so concurrent PDF
        requests don't race on the initial launch.
        """
        # Fast path: already up and healthy.
        if cls._browser is not None and cls._browser.is_connected():
            return cls._browser

        async with cls._browser_lock:
            # Double-check inside the lock — another coroutine may have just
            # finished the launch while we were waiting.
            if cls._browser is not None and cls._browser.is_connected():
                return cls._browser

            # Launch (or relaunch) the browser.
            if cls._playwright is None:
                cls._playwright = await async_playwright().start()
            cls._browser = await cls._playwright.chromium.launch(
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
            return cls._browser

    @classmethod
    async def shutdown(cls):
        """Close the shared browser + playwright on FastAPI shutdown."""
        try:
            if cls._browser is not None:
                await cls._browser.close()
                cls._browser = None
            if cls._playwright is not None:
                await cls._playwright.stop()
                cls._playwright = None
        except Exception as e:
            logger.warning("PDFGenerator shutdown: %s", e)

    @staticmethod
    async def _asset_data_uri(url: Optional[str]) -> str:
        """Turn a stored `/api/v1/documents/{key}/file` URL into an embeddable data URI.

        Playwright renders the PDF in a headless browser that can't reach the
        FastAPI app by its public URL, so we pull the object bytes directly
        from MinIO and inline them as base64. Returns "" for missing / bad URLs.
        """
        if not url or not isinstance(url, str):
            return ""
        # We only handle the internal /api/v1/documents/{key}/file shape.
        marker = "/api/v1/documents/"
        if marker not in url:
            return ""
        try:
            tail = url.split(marker, 1)[1]  # "{key}/file"
            if tail.endswith("/file"):
                tail = tail[: -len("/file")]
            # Guess MIME from extension; MinIO/S3 may also return it, but the
            # exposed helper only gives us bytes.
            ext = tail.rsplit(".", 1)[-1].lower() if "." in tail else "png"
            mime = {
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "webp": "image/webp",
                "svg": "image/svg+xml",
            }.get(ext, "image/png")
            data = await storage_service.download_file("documents", tail)
            if not data:
                return ""
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except Exception as exc:
            logger.debug("Could not inline branding asset %s: %s", url, exc)
            return ""

    async def _get_clinic_context(
        self,
        db: Optional[AsyncSession] = None,
        doctor_id: Optional[UUID] = None,
    ) -> dict:
        """Pull clinic branding from Doctor model dynamically.

        Reads both direct Doctor fields and doctor.settings JSONB.
        Falls back to FALLBACK_CLINIC if no db/doctor_id provided.
        """
        if db is not None and doctor_id is not None:
            from app.models import Doctor

            try:
                result = await db.execute(select(Doctor).where(Doctor.id == doctor_id))
                doc = result.scalar_one_or_none()
                if doc:
                    settings = doc.settings or {}
                    state = settings.get("state", "")
                    state_overrides = STATE_PRESCRIPTION_OVERRIDES.get(state, {})
                    # Inline logo + signature as data URIs (Playwright can't
                    # reach our own /api endpoints).
                    logo_data_uri = await self._asset_data_uri(settings.get("clinic_logo_url"))
                    signature_data_uri = await self._asset_data_uri(settings.get("signature_url"))
                    return {
                        "clinic_name": settings.get("clinic_name") or doc.clinic_name or FALLBACK_CLINIC["clinic_name"],
                        "clinic_address": settings.get("clinic_address")
                        or doc.clinic_address
                        or FALLBACK_CLINIC["clinic_address"],
                        "clinic_phone": settings.get("clinic_phone") or doc.phone or FALLBACK_CLINIC["clinic_phone"],
                        "clinic_email": settings.get("clinic_email") or FALLBACK_CLINIC["clinic_email"],
                        "doctor_name": doc.name or FALLBACK_CLINIC["doctor_name"],
                        "registration_number": doc.registration_number or "",
                        "state_header": state_overrides.get("header_text", ""),
                        "state_footer": state_overrides.get("footer_text", ""),
                        "clinic_logo_data_uri": logo_data_uri,
                        "signature_data_uri": signature_data_uri,
                    }
            except Exception as exc:
                logger.warning("Failed to load clinic context from DB: %s", exc)

        fallback = dict(FALLBACK_CLINIC)
        fallback.setdefault("clinic_logo_data_uri", "")
        fallback.setdefault("signature_data_uri", "")
        return fallback

    def _prepare_context(self, data: Dict[str, Any], clinic: dict) -> Dict[str, Any]:
        """Merge clinic branding into the template context."""
        context = {"clinic": clinic}
        context.update(data)
        context["now"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return context

    async def _render_to_pdf(
        self, template_name: str, context: Dict[str, Any], s3_key: str, watermark_text: str = ""
    ) -> str:
        """Render Jinja2 template → HTML → Playwright → PDF → optional watermark → S3."""
        template = _jinja_env.get_template(template_name)
        html = template.render(**context)

        # Render to temp file, then upload to S3
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # P0.6: reuse the shared browser — saves ~2-5s per PDF vs launching one.
            browser = await PDFGenerator._get_browser()
            page = await browser.new_page()
            try:
                await page.set_content(html, wait_until="networkidle")
                await page.pdf(
                    path=tmp_path,
                    format="A5",
                    margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
                )
            finally:
                await page.close()

            # Apply watermark if text provided
            if watermark_text:
                try:
                    from app.services.pdf_security import PDFSecurityService

                    pss = PDFSecurityService()
                    await pss.add_watermark(tmp_path, output_path=tmp_path, custom_text=watermark_text)
                except Exception as exc:
                    logger.warning("Watermark failed (non-blocking): %s", exc)

            # Upload to S3 with local filesystem fallback
            with open(tmp_path, "rb") as f:
                pdf_bytes = f.read()

            try:
                await storage_service.upload_file(
                    file_data=pdf_bytes,
                    bucket_type="pdfs",
                    key=s3_key,
                    content_type="application/pdf",
                )
                logger.info("PDF generated and uploaded to S3: %s (%s)", s3_key, template_name)
                return s3_key
            except Exception as exc:
                logger.warning("S3 upload failed, saving locally: %s", exc)
                local_dir = os.path.join(tempfile.gettempdir(), "soloprac_pdfs", os.path.dirname(s3_key))
                os.makedirs(local_dir, exist_ok=True)
                local_path = os.path.join(tempfile.gettempdir(), "soloprac_pdfs", s3_key)
                import shutil

                shutil.copy(tmp_path, local_path)
                logger.info("PDF saved locally: %s", local_path)
                return local_path
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ─── Prescription ───

    async def generate_prescription(
        self,
        patient_name: str,
        patient_age: int = 0,
        patient_gender: str = "",
        date: str = "",
        diagnosis: str = "",
        medications: list = None,
        instructions: str = "",
        follow_up: str = "",
        doctor_name: str = "",
        db: Optional[AsyncSession] = None,
        doctor_id: Optional[UUID] = None,
    ) -> str:
        s3_key = f"pdfs/{doctor_id}/rx_{uuid.uuid4().hex[:12]}.pdf"
        clinic = await self._get_clinic_context(db, doctor_id)
        # If doctor_name explicitly passed, use it
        if doctor_name:
            clinic = dict(clinic, doctor_name=doctor_name)
        context = self._prepare_context(
            {
                "patient_name": patient_name,
                "patient_age": patient_age,
                "patient_gender": patient_gender,
                "date": date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "diagnosis": diagnosis,
                "medications": medications or [],
                "instructions": instructions,
                "follow_up": follow_up,
            },
            clinic,
        )

        wm_text = f"Dr. {clinic.get('doctor_name', '')} · {clinic.get('clinic_name', '')}".strip(" ·")
        return await self._render_to_pdf("prescription", context, s3_key, watermark_text=wm_text)

    # ─── Invoice ───

    async def generate_invoice(
        self,
        patient_name: str,
        invoice_number: str,
        date: str = "",
        items: list = None,
        subtotal: float = 0.0,
        tax: float = 0.0,
        total: float = 0.0,
        amount_in_words: str = "",
        payment_method: str = "",
        upi_id: str = "",
        status: str = "pending",
        notes: str = "",
        db: Optional[AsyncSession] = None,
        doctor_id: Optional[UUID] = None,
    ) -> str:
        s3_key = f"pdfs/{doctor_id}/inv_{uuid.uuid4().hex[:12]}.pdf"
        clinic = await self._get_clinic_context(db, doctor_id)
        context = self._prepare_context(
            {
                "patient_name": patient_name,
                "invoice_number": invoice_number,
                "date": date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "items": items or [],
                "subtotal": subtotal,
                "tax": tax,
                "total": total,
                "amount_in_words": amount_in_words,
                "payment_method": payment_method,
                "upi_id": upi_id,
                "status": status,
                "notes": notes,
            },
            clinic,
        )

        # Watermark: "Dr. Name · Clinic Name"
        wm_text = f"Dr. {clinic.get('doctor_name', '')} · {clinic.get('clinic_name', '')}".strip(" ·")

        return await self._render_to_pdf("invoice", context, s3_key, watermark_text=wm_text)

    # ─── Certificate ───

    async def generate_certificate(
        self,
        patient_name: str,
        patient_age: int = 0,
        cert_type: str = "sick_leave",
        body: str = "",
        recommended_rest: str = "",
        verification_code: str = "",
        verify_url: str = "",
        date: str = "",
        db: Optional[AsyncSession] = None,
        doctor_id: Optional[UUID] = None,
    ) -> str:
        s3_key = f"pdfs/{doctor_id}/cert_{uuid.uuid4().hex[:12]}.pdf"
        clinic = await self._get_clinic_context(db, doctor_id)
        context = self._prepare_context(
            {
                "patient_name": patient_name,
                "patient_age": patient_age,
                "cert_type": cert_type,
                "body": body,
                "recommended_rest": recommended_rest,
                "verification_code": verification_code,
                "verify_url": verify_url,
                "date": date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            },
            clinic,
        )
        return await self._render_to_pdf("certificate", context, s3_key)

    # ─── Weekly Report ───

    async def generate_weekly_report(
        self,
        report_data: Dict[str, Any],
        db: Optional[AsyncSession] = None,
        doctor_id: Optional[UUID] = None,
    ) -> str:
        """Generate a weekly clinical report PDF from the report data structure."""
        s3_key = f"pdfs/{doctor_id}/weekly_report_{uuid.uuid4().hex[:12]}.pdf"
        clinic = await self._get_clinic_context(db, doctor_id)

        # Extract and format data for template
        layout = report_data.get("layout", "clinical")
        patient_name = report_data.get("patient_name", "Patient")
        patient_age = report_data.get("patient_age", 0)
        patient_gender = report_data.get("patient_gender", "")
        patient_mrn = report_data.get("patient_mrn", str(uuid.uuid4())[:8])

        # Build sections based on layout
        sections = report_data.get("sections", [])
        critical = report_data.get("critical", [])
        notable = report_data.get("notable", [])
        routine = report_data.get("routine", [])

        # Format dates
        def fmt_date(dt_str):
            if not dt_str:
                return ""
            try:
                dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                return dt.strftime("%b %d")
            except:
                return dt_str[:10] if dt_str else ""

        # Format events for template
        def format_events(events):
            formatted = []
            for e in events:
                formatted.append(
                    {
                        "date": fmt_date(e.get("created_at") or e.get("date")),
                        "summary": e.get("summary", ""),
                        "version": e.get("version", e.get("version_number", "")),
                        "score": e.get("significance_score", e.get("score", 0)),
                        "tier": e.get("tier", ""),
                        "edit_type": e.get("edit_type", ""),
                        "components": e.get("score_components") or e.get("components"),
                    }
                )
            return formatted

        critical_fmt = format_events(critical)
        notable_fmt = format_events(notable)
        routine_fmt = format_events(routine)
        sections_fmt = format_events(sections)

        # Images from report_data — embed as base64 data URIs for Playwright rendering
        images = []
        if report_data.get("images"):
            for img in report_data["images"]:
                filepath = img.get("url", "")
                url = filepath
                caption = img.get("caption") or img.get("filename", "Clinical Image")
                # Convert S3 keys or local file paths to base64 data URIs so Playwright can render them
                if filepath and not filepath.startswith("http") and not filepath.startswith("data:"):
                    try:
                        # Check if it's an S3 key (contains /images/ or /pdfs/)
                        if "/images/" in filepath or "/pdfs/" in filepath:
                            # Download from S3
                            bucket = "images" if "/images/" in filepath else "pdfs"
                            img_bytes = await storage_service.download_file(bucket, filepath)
                        else:
                            # Local file fallback
                            with open(filepath, "rb") as f_img:
                                img_bytes = f_img.read()

                        if img_bytes:
                            # Determine MIME type from extension
                            ext = os.path.splitext(filepath)[1].lower()
                            mime_map = {
                                ".jpg": "image/jpeg",
                                ".jpeg": "image/jpeg",
                                ".png": "image/png",
                                ".webp": "image/webp",
                            }
                            mime = mime_map.get(ext, "image/jpeg")
                            b64 = base64.b64encode(img_bytes).decode()
                            url = f"data:{mime};base64,{b64}"
                    except Exception as exc:
                        logger.warning("Could not read image for PDF: %s (%s)", filepath, exc)
                        url = (
                            "data:image/svg+xml;base64,"
                            + base64.b64encode(
                                b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="120" viewBox="0 0 200 120"><rect width="200" height="120" fill="#f1f5f9" rx="4"/><text x="100" y="65" text-anchor="middle" fill="#94a3b8" font-size="11" font-family="sans-serif">Image unavailable</text></svg>'
                            ).decode()
                        )
                images.append({"url": url, "caption": caption})

        # QR code verification data
        qr_code = report_data.get("qr_code", "")
        verify_url = report_data.get("verify_url", "")

        # Build period strings
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        period_start = week_ago.strftime("%Y-%m-%d")
        period_end = now.strftime("%Y-%m-%d")
        generated_at = now.strftime("%Y-%m-%d %H:%M UTC")

        # Build context for template
        data = {
            "layout": layout,
            "title": report_data.get("title", "Weekly Clinical Report"),
            "description": report_data.get("description", "Weekly clinical summary"),
            "period_start": period_start,
            "period_end": period_end,
            "generated_at": generated_at,
            "patient_name": patient_name,
            "patient_age": patient_age,
            "patient_gender": patient_gender,
            "patient_mrn": patient_mrn,
            "critical_count": len(critical_fmt),
            "notable_count": len(notable_fmt),
            "routine_count": len(routine_fmt),
            "critical": critical_fmt,
            "notable": notable_fmt,
            "routine": routine_fmt,
            "sections": sections_fmt,
            "images": images,
            "qr_code": qr_code,
            "verify_url": verify_url,
        }

        context = self._prepare_context(data, clinic)

        wm_text = f"Dr. {clinic.get('doctor_name', '')} · {clinic.get('clinic_name', '')}".strip(" ·")
        return await self._render_to_pdf("weekly_report", context, s3_key, watermark_text=wm_text)


pdf_generator = PDFGenerator()
