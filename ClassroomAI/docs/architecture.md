# Classroom AI

## Project Overview

Classroom AI is an AI Microservice that integrates with the School Platform.

The AI service is responsible for:

- Face Recognition
- Attendance Detection
- Hand Raise Detection
- Attention Monitoring
- AI Analytics
- Exporting Results

The School Platform remains the master system.

---

## High Level Architecture

```
School Platform
        │
 REST API
        │
        ▼
 Classroom AI API
        │
 Session Manager
        │
 Stream Manager
        │
 AI Pipeline
        │
 Local Database
        │
 Export Service
        │
 School Platform
```

---

## AI Pipeline

```
Frame

↓

Face Recognition

↓

Student Identification

↓

Pose Detection

↓

Hand Raise Detection

↓

Attention Detection

↓

Future AI Modules
```

---

## Main Components

- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- OpenCV
- Face Recognition
- MediaPipe
- Event Engine
- Export Service

---

## Project Goals

- Detect attendance automatically.
- Detect student participation.
- Monitor classroom attention.
- Generate AI reports.
- Integrate with existing School Platform.

---

## Project Structure

```
app/

api/

core/

database/

models/

schemas/

services/

ai/

utils/

websocket/
```
