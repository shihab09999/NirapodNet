# NirapodNet — Project Roadmap

## Overview
This roadmap tracks the development of NirapodNet through 14 phases (Phase 0–13). Each phase represents a major milestone with specific deliverables. Progress is tracked using checkboxes.

---

## Phase 0 — Foundation
**Goal:** Establish core development environment and foundational skills.

- [x] Set up Python development environment
- [x] Configure Git and GitHub repository
- [x] Set up Linux development environment (WSL or native)
- [ ] Configure VS Code with extensions (Python, Docker, GitLens)
- [ ] Learn networking fundamentals (TCP/IP, WebSockets, HTTP)
- [ ] Build basic web development skills (HTML, CSS, JavaScript)
- [x] Create initial project structure and documentation

**Target Completion:** Week 1-2

---

## Phase 1 — Core Prototype
**Goal:** Build a working LAN messaging system with a local server.

- [x] Design local network communication protocol
- [x] Implement FastAPI/Flask backend server
- [x] Create WebSocket-based real-time messaging
- [x] Build basic frontend (HTML/CSS/JS) for messaging
- [x] Implement user registration and login (local only)
- [x] Test multi-device communication on same LAN
- [x] Document API endpoints and message formats
- [ ] Create Docker Compose for local development

**Target Completion:** Week 3-4

---

## Phase 2 — Emergency System
**Goal:** Implement core emergency communication features.

- [x] Design role-based access control (Admin, Operator, Responder, User)
- [x] Implement authentication with secure password hashing (bcrypt/argon2)
- [x] Build Emergency Broadcast system
  - [x] Authenticated broadcast messages
  - [x] Priority levels (Critical, High, Medium, Low — implemented 2026-10-20; info/warning remain accepted as legacy aliases)
  - [ ] Geographic targeting
- [x] Implement SOS System
  - [x] SOS request with location, type, description
  - [x] Incident ID assignment
  - [x] Routing to operator dashboard
- [x] Implement Safety Check-In
  - [x] Four status options (Safe, Need Help, Not at Location, Unable to Respond)
  - [x] Aggregation dashboard for operators
- [x] Build operator/admin dashboard UI
- [x] Add audit logging for critical actions

**Target Completion:** Week 5-7

> Note (2026-10-20): Geographic targeting for broadcasts is deferred to Phase 6 (Geospatial Layer) — user areas/locations do not exist before that phase, and phases proceed serially. In Phase 2 a broadcast targets the whole local network. That checkbox stays open until Phase 6. All other Phase 2 items are complete; see `tests/phase-2-test-log.md`.

---

## Phase 3 — Security
**Goal:** Harden the system with comprehensive security measures.

- [ ] Implement end-to-end encryption for messages
- [ ] Add message signing for emergency broadcasts
- [ ] Implement replay protection (unique IDs, timestamps, sequences)
- [ ] Conduct threat modeling exercise
- [ ] Implement rate limiting and DoS protection
- [ ] Add input validation and sanitization
- [ ] Secure WebSocket connections (WSS)
- [ ] Implement session management with secure tokens
- [ ] Add security headers (CSP, HSTS, etc.)
- [ ] Perform security testing (OWASP Top 10)
- [ ] Document security architecture and threat model

**Target Completion:** Week 8-10

---

## Phase 4 — Measurement
**Goal:** Establish performance baselines and reliability metrics.

- [ ] Build automated testing framework (pytest)
- [ ] Implement latency measurement (end-to-end, broadcast propagation)
- [ ] Measure throughput under various loads
- [ ] Test packet loss and delivery reliability
- [ ] Load test with 10, 20, 50 concurrent users
- [ ] Security penetration testing
- [ ] Resilience testing (network partition, node failure)
- [ ] Document test methodology and results
- [ ] Set up CI/CD pipeline with automated tests
- [ ] Create performance benchmark reports

**Target Completion:** Week 11-12

---

## Phase 5 — First Real Pilot
**Goal:** Deploy in a controlled real-world environment with real users.

- [ ] Prepare deployment package (Docker, configuration)
- [ ] Create operator training materials
- [ ] Conduct school/community pilot deployment
- [ ] Run structured emergency drill scenario
- [ ] Collect user feedback and usability data
- [ ] Document lessons learned
- [ ] Iterate on UX based on pilot feedback
- [ ] Fix critical bugs identified during pilot

**Target Completion:** Week 13-15

---

## Phase 6 — Geospatial Layer
**Goal:** Add offline-capable mapping and location features.

- [ ] Integrate offline map tiles (MapLibre/Leaflet with MBTiles)
- [ ] Implement GPS location capture and display
- [ ] Build shelter management system
  - [ ] Shelter CRUD with capacity, resources, contacts
  - [ ] Occupancy tracking
- [ ] Implement rescue team tracking
  - [ ] Team registration, location, status, capabilities
- [ ] Add map layers:
  - [ ] Shelters
  - [ ] Hospitals
  - [ ] Rescue teams
  - [ ] Communication nodes
  - [ ] Incidents
  - [ ] Safe zones
  - [ ] Flood zones
- [ ] Implement offline map caching strategy
- [ ] Add geofencing and proximity alerts

**Target Completion:** Week 16-19

---

## Phase 7 — Sensor Network
**Goal:** Deploy physical flood and environmental monitoring sensors.

- [ ] Design sensor node hardware (ESP32/STM32 + sensors)
- [ ] Implement firmware for water level, rainfall, temperature, humidity
- [ ] Build sensor data ingestion pipeline
- [ ] Implement sensor node registration and management
- [ ] Create sensor dashboard with real-time telemetry
- [ ] Add historical data visualization (charts, trends)
- [ ] Implement sensor health monitoring (battery, signal, connectivity)
- [ ] Design data validation and outlier detection
- [ ] Test sensor nodes in field conditions
- [ ] Document sensor deployment procedures

**Target Completion:** Week 20-24

---

## Phase 8 — Resilient Networking
**Goal:** Implement mesh networking, LoRa, and store-and-forward synchronization.

- [ ] Research and select mesh networking technology (Wi-Fi mesh, BATMAN, etc.)
- [ ] Implement multi-hop mesh routing
- [ ] Integrate LoRa for long-range low-bandwidth telemetry
- [ ] Build edge node/local server capability
- [ ] Implement store-and-forward event queue
  - [ ] Persistent local storage (SQLite)
  - [ ] Unique event IDs, timestamps, source identifiers
  - [ ] Conflict resolution and duplicate detection
- [ ] Implement authenticated synchronization protocol
- [ ] Test network partition and recovery scenarios
- [ ] Document resilient networking architecture

**Target Completion:** Week 25-30

---

## Phase 9 — Portable Infrastructure
**Goal:** Build deployable solar-powered communication nodes.

- [ ] Design portable node hardware architecture
  - [ ] Solar panel sizing and charge controller
  - [ ] Battery management system
  - [ ] Router/mesh radio integration
  - [ ] LoRa gateway integration
  - [ ] Weatherproof enclosure design
- [ ] Build node provisioning and configuration system
- [ ] Implement remote node monitoring (health, power, connectivity)
- [ ] Test node deployment at multiple sites
- [ ] Validate power autonomy (battery life, solar charging)
- [ ] Document deployment guide and bill of materials

**Target Completion:** Week 31-35

---

## Phase 10 — UAV Integration
**Goal:** Integrate drone-based situational awareness and communication relay.

- [ ] Select UAV platform and communication payload
- [ ] Implement UAV telemetry ingestion (GPS, attitude, battery)
- [ ] Build camera/video stream integration
- [ ] Implement UAV as communication relay node
- [ ] Create UAV mission planning interface
- [ ] Add UAV tracking to geospatial dashboard
- [ ] Test aerial relay between disconnected ground nodes
- [ ] Implement safety procedures (geofencing, return-to-home)
- [ ] Document UAV integration and regulatory compliance

**Target Completion:** Week 36-41

---

## Phase 11 — Satellite Backhaul
**Goal:** Integrate commercial satellite connectivity as optional backhaul.

- [ ] Research and select satellite terminal (Starlink, etc.)
- [ ] Implement gateway node with satellite failover
- [ ] Build connection health monitoring
- [ ] Implement traffic routing (local vs. satellite)
- [ ] Test satellite backhaul in field conditions
- [ ] Validate graceful degradation when satellite unavailable
- [ ] Document satellite integration architecture
- [ ] Create cost/benefit analysis for satellite backhaul

**Target Completion:** Week 42-45

---

## Phase 12 — Multi-Node Deployment
**Goal:** Large-scale field testing with ~20 communication nodes.

- [ ] Design 20-node deployment topology
- [ ] Procure and configure all hardware
- [ ] Deploy nodes at strategic locations
- [ ] Conduct end-to-end system testing
- [ ] Measure communication range, latency, reliability
- [ ] Test multi-node mesh routing
- [ ] Validate sensor network integration
- [ ] Test UAV relay in multi-node environment
- [ ] Document deployment procedures and topology

**Target Completion:** Week 46-52

---

## Phase 13 — Research & Validation
**Goal:** Analyze data, publish findings, and prepare for real-world deployment.

- [ ] Analyze performance data from all phases
- [ ] Conduct failure analysis and root cause investigation
- [ ] Write research paper(s) on key findings
- [ ] Prepare conference submissions
- [ ] Create project website and documentation
- [ ] Produce demonstration videos
- [ ] Compile deployment report
- [ ] Prepare presentation materials
- [ ] Define operational procedures for authorized disaster response
- [ ] Plan sustainability and handover strategy

**Target Completion:** Week 53-60

---

## Progress Summary

| Phase | Status | Target Weeks | Actual Completion |
|-------|--------|--------------|-------------------|
| Phase 0 — Foundation | [x] Completed | 1-2 | 2026-08-30 |
| Phase 1 — Core Prototype | [x] Completed | 3-4 | 2026-08-31 |
| Phase 2 — Emergency System | [x] Completed | 5-7 | 2026-10-20 |
| Phase 3 — Security | [ ] Not Started | 8-10 | - |
| Phase 4 — Measurement | [ ] Not Started | 11-12 | - |
| Phase 5 — First Real Pilot | [ ] Not Started | 13-15 | - |
| Phase 6 — Geospatial Layer | [ ] Not Started | 16-19 | - |
| Phase 7 — Sensor Network | [ ] Not Started | 20-24 | - |
| Phase 8 — Resilient Networking | [ ] Not Started | 25-30 | - |
| Phase 9 — Portable Infrastructure | [ ] Not Started | 31-35 | - |
| Phase 10 — UAV Integration | [ ] Not Started | 36-41 | - |
| Phase 11 — Satellite Backhaul | [ ] Not Started | 42-45 | - |
| Phase 12 — Multi-Node Deployment | [ ] Not Started | 46-52 | - |
| Phase 13 — Research & Validation | [ ] Not Started | 53-60 | - |

---

## Milestone Gates

Each phase must pass these gates before proceeding:

1. **Functional** — Core features work as specified
2. **Tested** — Automated and manual tests pass
3. **Documented** — Architecture, API, and deployment docs updated
4. **Reviewed** — Code review and security review completed
5. **Measured** — Performance benchmarks recorded

---

*Last Updated: 2026-10-20*
*Version: 1.0*