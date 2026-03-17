

# Product Requirements Document

# Crime & Incident Intelligence Map — Trinidad & Tobago

Version: 1.0
Author: Surenjanath Singh
Product Type: AI-Driven Geospatial Intelligence Platform
Target Stack: Python, Django, PostgreSQL + PostGIS, Google Gemini API, Google Maps Platform

---

# 1. Executive Summary

The **Crime & Incident Intelligence Map** is an AI-powered geospatial monitoring system that automatically ingests news sources across Trinidad & Tobago, extracts incident data using natural language processing, and visualizes events such as:

* Crime incidents
* Traffic accidents
* Fires
* Natural disasters
* Police activity
* Public safety alerts

The platform transforms unstructured text articles into structured datasets that are plotted onto an **interactive national map**.

The system acts as a **real-time intelligence dashboard** for:

• Journalists
• Government agencies
• Insurance companies
• Security analysts
• Citizens

This system functions as a **Caribbean OSINT (Open Source Intelligence) monitoring system.**

---

# 2. Problem Statement

In Trinidad & Tobago, critical public safety information is fragmented across:

* News websites
* Social media
* Police bulletins
* Community reports

There is **no centralized system that aggregates, analyzes, and visualizes these incidents geographically**.

Current limitations include:

• Manual searching across multiple news sites
• No structured incident database
• No geospatial visualization of national incidents
• Poor historical trend analysis

This results in:

• Limited situational awareness
• Slow response by organizations
• Lack of data-driven policy decisions

---

# 3. Goals & Objectives

### Primary Goals

1. Automatically ingest news articles in Trinidad & Tobago
2. Use AI to extract incident details
3. Convert extracted data into structured geographic records
4. Plot incidents on an interactive map
5. Provide real-time incident analytics

### Secondary Goals

• Identify crime hotspots
• Analyze incident trends
• Provide insurance risk intelligence
• Improve public awareness

---

# 4. Target Users

### Citizens

Monitor incidents happening near their location.

### Journalists

Track emerging stories and breaking incidents.

### Government Agencies

Analyze crime and accident trends.

### Insurance Companies

Assess regional risk exposure.

### Security Firms

Monitor real-time threats.

---

# 5. Core Features

---

# 5.1 Automated News Ingestion

The system continuously monitors news sources such as:

Example sources:

* Guardian
* Newsday
* CNC3
* Loop TT
* Express
* Police press releases
* Government alerts

### Methods

RSS Feed ingestion
Web scraping
API ingestion where available

### Data collected

* Headline
* Article content
* Publication date
* Author
* Source URL

---

# 5.2 AI Incident Extraction Engine

Articles are processed using **LLM-based entity extraction**.

The AI identifies and extracts:

Incident Type
Location
Time
Description
People involved
Severity

Example extraction:

Article:

> “A man was shot near Ariapita Avenue on Tuesday night.”

Extracted data:

```
Incident Type: Shooting
Location: Ariapita Avenue
City: Port of Spain
Date: Tuesday
Category: Violent Crime
Severity: High
```

AI Model:

OLLAMA

---

# 5.3 Location Geocoding Engine

Extracted locations are converted to geographic coordinates.

Example:

"Ariapita Avenue" → Latitude / Longitude

Services used:

Google Maps Geocoding API
OpenStreetMap fallback

Output:

```
Latitude: 10.666
Longitude: -61.516
Region: Port of Spain
```

---

# 5.4 Incident Classification Engine

Incidents are categorized automatically.

### Crime Types

Violent Crime
Robbery
Assault
Shooting
Murder
Kidnapping

### Accident Types

Traffic Accident
Vehicle Collision
Pedestrian Accident

### Other Incidents

Fire
Flood
Natural Disaster
Police Activity

---

# 5.5 Interactive National Incident Map

The main interface displays all incidents on a **Trinidad & Tobago map**.

Users can:

Zoom
Filter incidents
Click markers to view details

Map Layers:

Crime
Accidents
Emergency events

Markers use color coding.

Example:

Red = Violent crime
Orange = Robbery
Yellow = Traffic accident
Blue = Fire
Purple = Disaster

---

# 5.6 Incident Detail Panel

Clicking a map marker reveals:

Incident title
Location
Category
Date and time
Summary
News source link

Example:

```
Incident: Shooting
Location: Ariapita Avenue
Date: 12 March 2026
Source: Guardian
Summary: A man was shot outside a nightclub...
```

---

# 5.7 Time-Based Incident Playback

Users can replay incidents over time.

Example:

Last 24 hours
Last 7 days
Last 30 days
Historical archive

This creates a **timeline visualization of incidents**.

---

# 5.8 Analytics Dashboard

Provides national insights.

Metrics include:

Total incidents today
Crime by region
Accidents by region
Crime trends over time
Most dangerous areas

Example analytics:

```
Port of Spain:
Violent Crime: 34
Robbery: 22
Accidents: 14
```

---

# 5.9 AI Incident Confidence Score

AI assigns confidence scores based on extraction reliability.

Example:

```
Confidence: 92%
```

Low confidence incidents are flagged for review.

---

# 5.10 Admin Moderation System

Editors can:

Approve incidents
Edit extracted data
Merge duplicates
Delete incorrect entries

This ensures data accuracy.

---

# 6. System Architecture

### Data Pipeline

```
News Sources
      ↓
Article Scraper
      ↓
Article Database
      ↓
AI Extraction Engine
      ↓
Incident Parser
      ↓
Geocoding Engine
      ↓
Incident Database
      ↓
Map Visualization
```

---

# 7. Data Model

### Table: Articles

```
id
title
content
source
url
published_date
scraped_date
```

---

### Table: Incidents

```
id
incident_type
category
description
location_name
latitude
longitude
region
incident_date
confidence_score
article_id
```

---

### Table: Sources

```
id
source_name
rss_url
scraper_type
last_checked
```

---

# 8. Technology Stack

Backend

Python
Django
Celery (background jobs)

Database

PostgreSQL
PostGIS (geospatial queries)

AI

Google Gemini API
Natural language processing

Map

Google Maps API
Mapbox alternative

Infrastructure

Docker
Cloud Run / GCP
Redis queue

---

# 9. AI Processing Workflow

Step 1
Scrape article

Step 2
Send to AI extraction model

Prompt example:

```
Extract incident information from this article.

Return JSON format:

{
incident_type:
category:
location:
date:
description:
severity:
}
```

Step 3
Parse AI output

Step 4
Geocode location

Step 5
Save incident

---

# 10. UI Pages

### Homepage

Interactive Trinidad map
Recent incidents feed

---

### Incident Dashboard

Statistics
Charts
Trend analysis

---

### Incident List

Table of all incidents

Filters:

Date
Region
Incident type

---

### Incident Detail

Full article
Map location
AI extracted summary

---

### Admin Panel

Approve incidents
Edit incident data
Manage sources

---

# 11. Security & Reliability

Prevent scraping abuse
Validate AI outputs
Manual moderation layer

---

# 12. Future Features

Crowdsourced incident reporting
Police API integration
SMS alerts
Predictive crime modeling
Mobile app

---

# 13. Success Metrics

Number of incidents processed daily
AI extraction accuracy
Active users
Average response latency

---

# 14. MVP Scope

For Version 1:

News ingestion
AI extraction
Map visualization
Basic analytics

Advanced prediction features come later.

---

# 15. Example User Flow

User opens platform.

Map loads.

User sees:

Red markers in Port of Spain.

User clicks marker.

Popup shows:

```
Shooting
Ariapita Avenue
March 12
Source: Guardian
```

User opens article.

---

# 16. Strategic Value

This system becomes a **national intelligence dashboard**.

Potential clients:

Insurance companies
Government
Security firms
Media

It could evolve into the **Caribbean Crime Intelligence Platform**.

---

# Prompt for Google AI Studio

Use this to generate architecture and UI automatically:

```
Design a full stack AI system called "Trinidad Incident Intelligence Map".

The system ingests news articles from multiple Trinidad and Tobago news sources using RSS and scraping.

An AI model extracts incident details including:
incident type, category, location, date, description, and severity.

Locations are geocoded to coordinates and plotted on an interactive Trinidad and Tobago map.

Users can filter incidents by type, region, and time.

The UI includes:
- national map dashboard
- incident analytics dashboard
- incident list view
- incident detail page
- admin moderation panel

Technology stack:
Python Django backend


The UI should be modern, dark themed, intelligence dashboard style similar to Palantir or ArcGIS.
```
