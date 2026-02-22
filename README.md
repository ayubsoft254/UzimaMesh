<p align="center">
  <img src="https://img.shields.io/badge/Django-5.0-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django 5.0" />
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/Azure_AI_Foundry-0078D4?style=for-the-badge&logo=microsoftazure&logoColor=white" alt="Azure AI Foundry" />
  <img src="https://img.shields.io/badge/HTMX-2.0-3366CC?style=for-the-badge&logo=htmx&logoColor=white" alt="HTMX" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License" />
</p>

# UzimaMesh

> **AI-driven healthcare coordination platform designed for Kenya's healthcare system.**
>
> Uzima Mesh optimizes patient intake, appointment scheduling, health data analysis, and real-time emergency monitoring — leveraging Azure AI Foundry Agents, MCP, and GitHub Copilot.

---

## 🚀 Live Sandbox

The latest version of Uzima Mesh is deployed and ready for testing.

**URL:** [https://app-uzima-mesh.azurewebsites.net/](https://app-uzima-mesh.azurewebsites.net/)

### Test Credentials

| Role | Email | Password | Status |
|---|---|---|---|
| **Administrator** | `admin@uzimamesh.com` | `uzima123` | Active |
| **Doctor** | `smith@uzima.com` | `password123` | Active |
| **Patient** | `jane@example.com` | `uzima123` | **Disabled** ⚠️ |

> **⚠️ Notice:** Patient account login and registration flows are currently under development and do not work. However, patients can still use the public-facing AI Intake chat without logging in.

---

## Overview

Uzima Mesh is a modern, full-stack triage and healthcare coordination platform built with **Django 5.0**. It connects patients to medical professionals through an intelligent, AI-assisted workflow that prioritizes cases by urgency, generates clinical summaries, and empowers doctors with a real-time command center.

### Key Capabilities

- **Real-Time AI Intake Agent** — Patients do not fill out long forms. Instead, they chat directly with an Azure AI Foundry Agent via the `azure-ai-projects` SDK. The conversational AI fluidly gathers demographics, symptoms, and medical history.
- **AI-Powered Triage** — After gathering sufficient information, the Azure Agent assigns an urgency score (1–5), generates a clinical summary, and can use tools to create the triage record directly in the backend.
- **Doctor Command Center** — Authenticated doctors access a real-time dashboard to view, accept, escalate, or request vitals for queued triage sessions, sorted by priority.
- **Model Context Protocol (MCP)** — An MCP server exposes tools like `get_doctor_availability` and `create_triage_record`, enabling AI agents to interact with the Django database programmatically.
- **Microsoft Entra ID SSO** — Enterprise-grade authentication via Azure AD / Microsoft Entra ID using `django-allauth`.
- **Live Updates with HTMX** — Patient queues and doctor dashboards refresh via HTMX partial renders — no full-page reloads needed.

---

## Architecture

```text
UzimaMesh/
├── uzima_mesh/            # Django project settings & root URL conf
├── triage/                # Core application
│   ├── models.py          # Patient, Doctor, TriageSession, ChatMessage
│   ├── views.py           # Dashboard, intake UI, doctor command center
│   ├── services.py        # Azure AI Projects SDK connection logic
│   └── serializers.py     # DRF serializers
│
├── mcp_server/            # Model Context Protocol server
│   └── server.py          # FastMCP tools injected with Django context
│
├── templates/             # Django templates
│   ├── base.html          # Shared layout (nav, auth, static)
│   ├── account/           # Allauth authentication pages
│   └── triage/            # Intake form, dashboards, HTMX partials
│       ├── patient_intake.html
│       ├── doctor_dashboard.html
│       └── dashboard.html
│
├── static/                # Static assets (CSS, JS, images)
├── requirements.txt       # Python dependencies (strictly pinned)
├── entrypoint.sh          # Production deployment script
├── .env.example           # Environment variable template
└── manage.py              # Django CLI
```

---

## Data Models

| Model | Purpose |
|---|---|
| **Patient** | Stores demographics, contact info, medical history, and current prescriptions. |
| **Doctor** | Linked to a user account. Tracks specialty, availability, and bio for doctor matching. |
| **TriageSession** | Core workflow entity. Tracks symptoms, urgency score (1--5), status (Pending / In Progress / Completed / Cancelled), AI summary, and recommended action. |
| **ChatMessage** | Conversational log between the patient and the AI triage agent. |

---

## Getting Started

### Prerequisites

- **Python 3.10+**
- **pip** (or `venv`)
- *Optional:* PostgreSQL (for production; SQLite is used by default for local development)

### 1. Clone the Repository

```bash
git clone https://github.com/ayubsoft254/UzimaMesh.git
cd UzimaMesh
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your values:

| Variable | Description |
|---|---|
| `DJANGO_SECRET_KEY` | Django secret key |
| `DJANGO_DEBUG` | Debug mode (`True`/`False`) |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `DATABASE_URL` | PostgreSQL connection string |
| `AZURE_CLIENT_ID` | Microsoft Entra ID client ID (Service Principal) |
| `AZURE_CLIENT_SECRET` | Microsoft Entra ID client secret |
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `AZURE_AI_PROJECT_CONNECTION_STRING` | Azure AI Foundry connection string |
| `AZURE_AI_AGENT_ID` | Azure AI Assistant/Agent ID (`asst_...`) |

### 5. Apply Migrations & Create a Superuser

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. Run the Development Server

```bash
python manage.py runserver
```

Visit **http://127.0.0.1:8000/** to access the application. Local server `uvicorn` can also be used if ASGI is preferred for async tools.

---

## Usage

### Patient Intake (`/intake/`)

Patients initiate a real-time chat with the Azure AI Agent. The agent asks questions to determine symptoms and medical history, and uses its MCP tools to formally lodge a `TriageSession` into the database.

### Doctor Command Center (`/doctor/`)

Authenticated doctors see a priority-sorted queue of pending triage sessions. Each card displays the patient name, symptoms, urgency level, and AI-generated summary. Doctors can:
- **Accept** a session to begin treatment
- **Escalate** a critical case
- **Request Vitals** for more diagnostic data

The queue auto-refreshes via HTMX polling.

### Admin Panel (`/admin/`)

Django's built-in admin interface for managing records, users, and roles.

---

## Production Deployment

### Using Gunicorn (Recommended)

The included `entrypoint.sh` automates migrations, static file collection, and Gunicorn startup:

```bash
chmod +x entrypoint.sh
./entrypoint.sh
```

### Static Files

Static files are served in production via **WhiteNoise** with compressed manifest storage.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Django 5.0, Django REST Framework |
| **Frontend** | Django Templates, HTMX, Vanilla CSS |
| **Authentication** | django-allauth, Microsoft Entra ID (Azure AD) |
| **AI / Agents** | Azure AI SDK (`azure-ai-projects`), FastMCP |
| **Database** | SQLite (dev) / PostgreSQL (prod) via `dj-database-url` |
| **Static Files** | WhiteNoise |
| **WSGI Server** | Gunicorn |

---

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

<p align="center">
  <sub>Built with care for Kenya's healthcare system</sub>
</p>
