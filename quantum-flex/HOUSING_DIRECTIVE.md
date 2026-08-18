# 📡 OPERATIONAL DIRECTIVE: RESIDENTIAL ACQUISITION SCOUT

**TO:** IDE / Autonomous Assistant Agent

**FROM:** Rahshaun Chambers (Root Authority)

**SUBJECT:** Operational Mandate & Execution Protocol for Housing Search Automation

**TARGET REGION:** Greater Pittston & Wyoming Valley Corridor, PA

---

## 1. Primary Mandate & Executive Summary

Your directive is to act as an autonomous intelligence scout and pipeline manager to identify, filter, score, and track prospective residential leases in Luzerne County, Pennsylvania.

The primary objective is to secure a quiet, zero-distraction focus environment optimized for computer science coursework (SNHU), machine operator shifts (Acton Technologies), and core software engineering (Quantum Flex).

---

## 2. Hard Parameters & Constraint Engine

Every candidate listing must pass through the following strict boolean filters before entering the primary triage queue:

### A. Financial Parameters

* **Target Monthly Rent:** $600 – $900 / month.
* **Hard Ceiling Total Overhead:** ≤ $1,200 / month (including rent, electric/heating, water, and gigabit internet).
* **Income Allocation:** Minimum 50% of net earnings must remain unencumbered for fixed savings and operational capital.

### B. Transit Vector (E-Bike Radius)

* **Primary Anchor:** Employment site at Acton Technologies (Pittston, PA).
* **Transit Appliance:** Electric Bicycle (15–28 mph transit speed envelope).
* **Distance Radius:** Up to 10 miles maximum road distance.
* **Target Municipalities:**
  1. *Tier 1 (Immediate – 0 to 3 mi):* Pittston (18640), Pittston Twp, Jenkins Twp.
  2. *Tier 2 (Adjacent – 3 to 6 mi):* West Pittston, Avoca, Dupont, Hughestown, Wyoming.
  3. *Tier 3 (Extended – 6 to 10 mi):* Kingston, Plains Township, Wilkes-Barre (North / Downtown / East End).

### C. Physical & Focus Infrastructure Requirements

* **E-Bike Physical Security:** Ground-floor access, dedicated lockable indoor hallway, covered porch, or private garage. Must have a grounded 120V outlet adjacent for battery charging.
* **Acoustic & Privacy Isolation:** Minimal foot-traffic overhead (favor top-floor units, rear apartments, detached half-doubles, or single studios/efficiencies).
* **ISP Capability:** Must be wired for high-speed fiber or cable (e.g., Xfinity / Verizon 500+ Mbps).
* **Workstation Footprint:** Minimum 80 sq ft dedicated space within the unit to support dual-monitor workstation, Lenovo Yoga, and server hardware.

---

## 3. Execution Sequence

```
[ Ingest Listing Data ]
          │
          ▼
[ Run Hard Stop Filters ] ──(Fails Financial / E-Bike / ISP)──► [ DISCARD ]
          │
          ▼ (Passes)
[ Calculate Focus Score ]
          │
          ▼
[ Format Candidate Entry ]
          │
          ▼
[ Generate Landlord Outreach ]
```

### Step 1: Automated Ingestion Vectors

Continuously monitor and ingest active listing APIs and feeds from:

* **Platforms:** HotPads (ZIP 18640 / 18702), Zillow (Luzerne County), Craigslist Scranton/Wilkes-Barre, Facebook Marketplace.
* **Keywords:** `Studio`, `1 Bedroom`, `Utilities Included`, `Private Entrance`, `Pittston`, `Jenkins`, `Avoca`, `Wyoming`, `Wilkes-Barre`.

### Step 2: Candidate Scoring System

Score passing listings from 0.0 to 10.0 using the weighted formula:

```
Score = (0.35 × Affordability) + (0.30 × Commute Proximity) + (0.20 × E-Bike Security) + (0.15 × Focus/Privacy)
```

---

## 4. Output Specification & Candidate Ledger

When presenting verified housing targets, format them in the following schema:

| ID | Location / ZIP | Unit Type | Rent / Mo | Distance to Acton | E-Bike Storage | Focus Score |
| --- | --- | --- | --- | --- | --- | --- |
| `PL-01` | Example | 1 Bed / 1 Bath | $750 | 1.2 mi | Ground Floor / Porch | **9.4** |

### Pre-Formatted Landlord Outreach Template

For listings with a Focus Score ≥ 8.0, generate low-friction contact scripts:

> "Hello, I am reaching out regarding the unit listed at [ADDRESS]. I work locally at Acton Technologies in Pittston and am looking for a quiet, long-term space starting [DATE]. I have proof of income and references ready for review. Could you let me know if this unit is still available for a viewing? Thank you, Rahshaun Chambers."

---

## 5. Failure Recovery & Logic Enforcement

* **Logic Bomb Prevention:** If utility costs or internet availability cannot be verified, mark the entry parameter as `NULL`. Never insert assumed overhead values.
* **Noise Enforcement:** Reject shared rooms or high-density student dormitories unless the unit explicitly guarantees a private lockable entrance, private bath, and quiet hours.
