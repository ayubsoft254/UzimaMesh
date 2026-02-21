<p align="center">
  <img src="https://img.shields.io/badge/Django-5.0-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django 5.0" />
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/Azure-Entra_ID-0078D4?style=for-the-badge&logo=microsoftazure&logoColor=white" alt="Azure" />
  <img src="https://img.shields.io/badge/HTMX-2.0-3366CC?style=for-the-badge&logo=htmx&logoColor=white" alt="HTMX" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License" />
</p>

# UzimaMesh

> **AI-driven healthcare coordination platform designed for Kenya's healthcare system.**
>
> Uzima Mesh optimizes patient intake, appointment scheduling, health data analysis, and real-time emergency monitoring — leveraging Microsoft Agent Framework, Azure MCP, and GitHub Copilot.

---

## 🚀 Live Sandbox

The latest version of Uzima Mesh is deployed and ready for testing.

**URL:** [https://app-uzima-mesh.azurewebsites.net/](https://app-uzima-mesh.azurewebsites.net/)

### Test Credentials

| Role | Username | Password |
|---|---|---|
| **Administrator** | `admin_uzima` | `uzima123` |
| **Doctor** | `dr_smith` | `password123` |
| **Patient** | `patient_jane` | `uzima123` |

---

## Overview

Uzima Mesh is a modern, full-stack triage and healthcare coordination platform built with **Django 5.0**. It connects patients to medical professionals through an intelligent, AI-assisted workflow that prioritizes cases by urgency, generates clinical summaries, and empowers doctors with a real-time command center.

### Key Capabilities

- **Conversational Patient Intake** — A guided, multi-step intake form collects patient demographics, symptoms, medical history, and prescriptions in a friendly conversational UI.
- **AI-Powered Triage** — Each session receives an AI-generated urgency score (1--5), a 3-bullet clinical summary, and a recommended action for the attending doctor.
- **Doctor Command Center** — A real-time dashboard where doctors can view, accept, escalate, or request vitals for queued triage sessions, sorted by priority.
- **Model Context Protocol (MCP) Server** — An MCP endpoint exposes tools like `get_doctor_availability` and `create_triage_record`, enabling AI agents (e.g., GitHub Copilot) to interact with the system programmatically.
- **Microsoft Entra ID SSO** — Enterprise-grade authentication via Azure AD / Microsoft Entra ID using `django-allauth`.
- **REST API** — Full CRUD API for Patients, Doctors, and Triage Sessions powered by Django REST Framework.
- **Live Updates with HTMX** — Patient queues and doctor dashboards refresh via HTMX partial renders — no full-page reloads needed.

---

## Architecture

```
UzimaMesh/
├── uzima_mesh/            # Django project settings & root URL conf
│   ├── settings.py        # Project configuration (Azure, DRF, Allauth, HTMX)
│   ├── urls.py            # Root URL routing
│   ├── wsgi.py            # WSGI entrypoint
│   └── asgi.py            # ASGI entrypoint
│
├── triage/                # Core application
│   ├── models.py          # Patient, Doctor, TriageSession, ChatMessage
│   ├── views.py           # Dashboard, intake, doctor command center, REST API
│   ├── serializers.py     # DRF serializers
│   ├── urls.py            # App URL routes
│   └── management/        # Custom management commands
│
├── mcp_server/            # Model Context Protocol server
│   └── server.py          # FastMCP tools for AI agent integration
│
├── templates/             # Django templates
│   ├── base.html          # Shared layout (nav, auth, static)
│   ├── account/           # Allauth authentication pages
│   └── triage/            # Intake form, dashboards, HTMX partials
│       ├── patient_intake.html
│       ├── doctor_dashboard.html
│       ├── dashboard.html
│       └── partials/      # HTMX partial templates
│
├── static/                # Static assets (CSS, JS, images)
├── requirements.txt       # Python dependencies
├── entrypoint.sh          # Production entrypoint (migrate + collectstatic + gunicorn)
├── .env.example           # Environment variable template
└── manage.py              # Django management CLI
```

---

## Data Models

| Model | Purpose |
|---|---|
| **Patient** | Stores demographics, contact info, medical history, and current prescriptions. Optionally linked to a Django user. |
| **Doctor** | Linked to a user account. Tracks specialty, availability, and bio for doctor matching. |
| **TriageSession** | Core workflow entity. Tracks symptoms, urgency score (1--5), status (Pending / In Progress / Completed / Cancelled), AI summary, and recommended action. |
| **ChatMessage** | Conversational log between the patient and the AI triage agent within a session. |

---

## Getting Started

### Prerequisites

- **Python 3.10+**
- **pip** (or a virtual environment manager like `venv`)
- *Optional:* PostgreSQL (for production; SQLite is used by default for development)

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

| Variable | Description | Default |
|---|---|---|
| `DJANGO_SECRET_KEY` | Django secret key | Auto-generated insecure key |
| `DJANGO_DEBUG` | Debug mode (`True`/`False`) | `True` |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts | *(empty)* |
| `DATABASE_URL` | PostgreSQL connection string | SQLite fallback |
| `AZURE_CLIENT_ID` | Microsoft Entra ID client ID | — |
| `AZURE_CLIENT_SECRET` | Microsoft Entra ID client secret | — |
| `AZURE_TENANT_ID` | Azure AD tenant ID | `common` |

### 5. Apply Migrations & Create a Superuser

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 6. Run the Development Server

```bash
python manage.py runserver
```

Visit **http://127.0.0.1:8000/** to access the application.

---

## Usage

### Patient Intake (`/intake/`)

Patients walk through a conversational multi-step form to report their symptoms, provide medical history, and submit an intake request. The system assigns an urgency score and creates a triage session.

### Doctor Command Center (`/doctor/`)

Authenticated doctors see a priority-sorted queue of pending triage sessions. Each card displays the patient name, symptoms, urgency level, and AI-generated summary. Doctors can:

- **Accept** a session to begin treatment
- **Escalate** a critical case
- **Request Vitals** for more diagnostic data

The queue auto-refreshes via HTMX polling.

### Admin Panel (`/admin/`)

Django's built-in admin interface for managing patients, doctors, sessions, and user accounts.

---

## API Reference

All endpoints require authentication (session or token-based).

| Endpoint | Method | Description |
|---|---|---|
| `/api/patients/` | GET, POST | List / create patients |
| `/api/patients/<id>/` | GET, PUT, DELETE | Retrieve / update / delete a patient |
| `/api/doctors/` | GET, POST | List / create doctors |
| `/api/doctors/<id>/` | GET, PUT, DELETE | Retrieve / update / delete a doctor |
| `/api/sessions/` | GET, POST | List / create triage sessions |
| `/api/sessions/<id>/` | GET, PUT, DELETE | Retrieve / update / delete a session |
| `/api/triage/updates/` | GET | HTMX partial: live triage queue |

---

## MCP Server (AI Agent Integration)

The MCP server exposes healthcare tools to AI agents via the **Model Context Protocol**:

```bash
python mcp_server/server.py
```

### Available Tools

| Tool | Description |
|---|---|
| `get_doctor_availability(specialty?)` | Returns a list of available doctors, optionally filtered by specialty. |
| `create_triage_record(...)` | Creates a new patient and triage session with the given demographics and symptoms. |

> This enables AI assistants (e.g., GitHub Copilot, custom agents) to query doctor availability and submit triage records programmatically.

---

## Production Deployment

### Using Gunicorn (Recommended)

The included `entrypoint.sh` automates migrations, static file collection, and Gunicorn startup:

```bash
chmod +x entrypoint.sh
./entrypoint.sh
```

This runs:
1. `python manage.py migrate --noinput`
2. `python manage.py collectstatic --noinput`
3. `gunicorn uzima_mesh.wsgi:application --bind 0.0.0.0:8000`

### Static Files

Static files are served in production via **WhiteNoise** with compressed manifest storage. No external file server (Nginx, S3) is required for basic deployments.

### Database

Set `DATABASE_URL` in `.env` to a PostgreSQL connection string for production:

```
DATABASE_URL=postgres://user:password@host:5432/uzimamesh
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Django 5.0, Django REST Framework |
| **Frontend** | Django Templates, HTMX, Vanilla CSS |
| **Authentication** | django-allauth, Microsoft Entra ID (Azure AD) |
| **AI / Agents** | FastMCP (Model Context Protocol), Azure Identity |
| **Database** | SQLite (dev) / PostgreSQL (prod) via `dj-database-url` |
| **Static Files** | WhiteNoise |
| **WSGI Server** | Gunicorn |
| **CORS** | django-cors-headers |

---

## Contributing

1. **Fork** the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes: `git commit -m "Add your feature"`
4. Push to the branch: `git push origin feature/your-feature`
5. Open a **Pull Request**

---

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for details.

---

<p align="center">
  <sub>Built with care for Kenya's healthcare system</sub>
</p>
