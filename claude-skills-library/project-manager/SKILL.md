---
name: project-manager
description: Professional project management skill aligned with PMBOK® 6th/7th Edition standards. Use this skill when you need to define requirements (ISO/IEC/IEEE 29148), review project plans, generate progress reports with Earned Value Management (EVM), conduct risk analysis, estimate costs, or provide project health assessments. Ideal for creating comprehensive project documentation, analyzing project performance metrics (SPI, CPI, EAC), managing risks across 14 categories, and ensuring stakeholder alignment. Triggers: "create project plan", "analyze project health", "calculate EVM", "risk assessment", "requirements definition", "progress report", "cost estimation", or requests involving PMBOK knowledge areas.
---

# Project Manager

## Overview

This skill provides comprehensive project management capabilities aligned with PMBOK® (Project Management Body of Knowledge) 6th and 7th Edition standards. It integrates proven methodologies, best practices, and templates to support project managers in delivering successful projects on time, within budget, and meeting quality expectations.

The skill is structured around PMBOK's **10 Knowledge Areas** and **5 Process Groups**, with particular emphasis on:

- **Requirements Engineering** (ISO/IEC/IEEE 29148 compliant)
- **Earned Value Management (EVM)** for objective progress tracking
- **Risk Management** using three-phase structured approach
- **Stakeholder Management** and communication planning
- **Cost Estimation and Control** with forecasting
- **Quality Management** with metrics and continuous improvement

This skill is designed for both experienced project managers seeking to standardize their approach and those new to formal project management who need structured guidance.

## When to Use This Skill

Use this skill when you need to:

- **Define Requirements**: "Create a requirements definition document for our CRM implementation project"
- **Review Project Plans**: "Review this project plan and identify risks and missing elements"
- **Generate Progress Reports**: "Create a monthly progress report with EVM analysis"
- **Conduct Risk Analysis**: "Perform a comprehensive risk assessment for this project"
- **Estimate Costs**: "Estimate project costs using bottom-up estimation approach"
- **Assess Project Health**: "Analyze current project health based on these metrics"
- **Create Project Documentation**: "Generate a project charter for this initiative"
- **Stakeholder Management**: "Develop a stakeholder engagement plan"
- **Schedule Management**: "Analyze the critical path and schedule performance"

### Example Requests:

1. "I'm starting a new enterprise software implementation. Help me define comprehensive requirements."
2. "Our project is showing SPI of 0.85. Generate a progress report and recommend recovery actions."
3. "Conduct a risk assessment for this legacy system migration project."
4. "Review our project plan and check if we're following PMBOK best practices."
5. "Calculate EAC, ETC, and TCPI based on our current EVM data."

## Project Management Framework

### PMBOK 10 Knowledge Areas

This skill integrates all 10 PMBOK knowledge areas:

1. **Integration Management**: Coordinating all project aspects
2. **Scope Management**: Defining and controlling what's included/excluded
3. **Schedule Management**: Planning, monitoring, and controlling timeline
4. **Cost Management**: Estimating, budgeting, and controlling costs
5. **Quality Management**: Ensuring deliverables meet requirements
6. **Resource Management**: Planning and managing team and resources
7. **Communications Management**: Ensuring timely and appropriate information flow
8. **Risk Management**: Identifying, analyzing, and responding to risks
9. **Procurement Management**: Managing vendor relationships and contracts
10. **Stakeholder Management**: Identifying and engaging stakeholders

### PMBOK 5 Process Groups

The skill supports workflows across all 5 process groups:

1. **Initiating**: Project charter, stakeholder identification
2. **Planning**: Requirements, schedule, budget, risk planning
3. **Executing**: Deliverable creation, team management
4. **Monitoring & Controlling**: Progress tracking, EVM, change control
5. **Closing**: Lessons learned, documentation, formal acceptance

---

## Core Workflow 1: Requirements Definition

Use this workflow when starting a new project or phase requiring detailed requirements documentation.

### Step 1: Understand Project Context

**Ask these questions:**
1. What business problem are we solving?
2. Who are the key stakeholders?
3. What are the business goals and success criteria?
4. What are the constraints (budget, timeline, resources)?
5. Are there regulatory or compliance requirements?

### Step 2: Gather Requirements

**Information Gathering Methods:**
- **Interviews**: One-on-one with stakeholders
- **Workshops**: Facilitated group sessions
- **Surveys**: Structured questionnaires
- **Document Analysis**: Review existing documentation
- **Observation**: Watch current processes
- **Prototyping**: Show mockups to elicit feedback

**Use the Requirements Definition Template** from `assets/requirements_definition_template.md`

### Step 3: Document Requirements

**Functional Requirements (FR):**
```
FR-001: User Login
- Priority: Must Have
- User Story: As a customer, I want to log in securely so that I can access my account
- Acceptance Criteria:
  - Given valid credentials
  - When user submits login form
  - Then system authenticates within 2 seconds
  - And logs the event
```

**Non-Functional Requirements (NFR):**
```
NFR-PERF-001: Response Time
- Category: Performance
- Requirement: 95% of page loads < 2 seconds
- Measurement: APM tool monitoring
```

### Step 4: Prioritize with MoSCoW

- **Must Have**: Critical for project success, non-negotiable
- **Should Have**: Important but not critical, can be deferred
- **Could Have**: Nice to have, easily postponed
- **Won't Have**: Out of scope for current release

### Step 5: Create Traceability Matrix

Link each requirement to:
- Business objective
- Design element
- Test case ID
- Responsible party

**Example:**
| Req ID | Business Objective | Design Element | Test Case | Status |
|--------|-------------------|----------------|-----------|--------|
| FR-001 | Improve security | Auth Module | TC-001, TC-002 | Approved |

### Step 6: Establish Change Control

**Change Request Process:**
1. Stakeholder submits change request
2. PM assesses impact (scope, schedule, cost, risk)
3. Change Control Board (CCB) reviews
4. Decision: Approve / Reject / Defer
5. Update baseline if approved
6. Communicate decision

### Output

Generate a comprehensive Requirements Definition Document that includes:
- Project overview and business goals
- Stakeholder analysis and communication plan
- Functional requirements with acceptance criteria
- Non-functional requirements (performance, security, usability, etc.)
- Interface specifications and data requirements
- Requirements traceability matrix
- Change control process
- Approval signatures

---

## Core Workflow 2: Project Plan Review

Use this workflow to review and validate a project plan against PMBOK best practices.

### Step 1: Review Across 10 Knowledge Areas

**Integration Management:**
- ✓ Is there a project charter with clear authority?
- ✓ Is there an integrated project management plan?
- ✓ Is there a change control process?

**Scope Management:**
- ✓ Is the scope clearly defined (in-scope and out-of-scope)?
- ✓ Is there a Work Breakdown Structure (WBS)?
- ✓ Are acceptance criteria defined?

**Schedule Management:**
- ✓ Are all activities identified and sequenced?
- ✓ Is the critical path identified?
- ✓ Is there schedule contingency/buffer?
- ✓ Are dependencies documented?

**Cost Management:**
- ✓ Is there a detailed cost estimate with basis?
- ✓ Is there a cost baseline?
- ✓ Is there contingency reserve (typically 10-20%)?
- ✓ Is there a cost tracking mechanism?

**Quality Management:**
- ✓ Are quality standards defined?
- ✓ Is there a quality assurance plan?
- ✓ Are acceptance criteria clear and measurable?
- ✓ Is testing time adequate (typically 20-30% of schedule)?

**Resource Management:**
- ✓ Are all roles and responsibilities defined (RACI matrix)?
- ✓ Is resource availability confirmed?
- ✓ Are there skill gaps that need addressing?
- ✓ Is there a team development plan?

**Communications Management:**
- ✓ Is there a communication plan with frequency and format?
- ✓ Are reporting mechanisms defined?
- ✓ Is there a stakeholder engagement plan?

**Risk Management:**
- ✓ Is there a risk register with identified risks?
- ✓ Are risks prioritized (probability × impact)?
- ✓ Are risk response strategies defined?
- ✓ Is there a risk monitoring plan?

**Procurement Management:**
- ✓ Are vendor requirements identified?
- ✓ Is contract type appropriate (Fixed-price, T&M, Cost-plus)?
- ✓ Are SLAs defined?
- ✓ Is there a vendor management plan?

**Stakeholder Management:**
- ✓ Are all stakeholders identified?
- ✓ Is stakeholder interest and influence assessed?
- ✓ Are engagement strategies defined?

### Step 2: Review from 5 Stakeholder Perspectives

**Executive Sponsor View:**
- Business value and ROI clearly articulated?
- Strategic alignment evident?
- Decision points and escalation paths defined?

**Project Team View:**
- Roles and responsibilities clear?
- Realistic workload and timeline?
- Adequate resources and tools?

**End User View:**
- User needs and pain points addressed?
- Change management and training planned?
- User acceptance testing included?

**IT Operations View:**
- Support model defined?
- Infrastructure and environment requirements clear?
- Transition and cutover planned?

**PMO View:**
- Consistent with organizational standards?
- Appropriate governance structure?
- Adequate documentation and controls?

### Step 3: Identify Gaps and Risks

**Common Gaps:**
- Requirements not signed off
- No contingency reserve
- Testing time inadequate (<20% of schedule)
- Vendor SLAs not defined
- No risk register
- Unrealistic schedule (no buffer)
- Change control process missing

**Red Flags:**
- Timeline < 6 months for complex project
- No executive sponsor or weak sponsor
- Fixed-price contract with unclear scope
- Team unfamiliar with technology
- Multiple external dependencies on critical path
- Regulatory requirements not addressed

### Step 4: Generate Review Report

**Review Report Structure:**
```
# Project Plan Review Report

## Executive Summary
[Overall assessment: Green/Yellow/Red]

## Strengths
- [What's done well]

## Gaps Identified
1. [Gap] - Severity: Critical/High/Medium/Low
   - Impact: [Description]
   - Recommendation: [Action]

## Risks Identified
1. [Risk] - Probability: [%] - Impact: [Cost/Schedule]
   - Mitigation: [Strategy]

## Recommendations
1. [Recommendation] - Priority: [Level]
   - Rationale: [Why]
   - Expected Benefit: [Outcome]

## Approval Recommendation
☐ Approve as is
☐ Approve with conditions
☐ Revise and resubmit
```

---

## Core Workflow 3: Progress Reporting with Earned Value Management

Use this workflow to generate objective, data-driven progress reports using EVM.

### Step 1: Collect EVM Data

**Required Metrics:**
- **BAC (Budget at Completion)**: Total project budget = ¥50,000,000
- **PV (Planned Value)**: Value of work scheduled to be completed = ¥30,000,000
- **EV (Earned Value)**: Value of work actually completed = ¥25,000,000
- **AC (Actual Cost)**: Actual cost incurred = ¥28,000,000

### Step 2: Calculate Performance Indices

**Schedule Performance:**
```
SV (Schedule Variance) = EV - PV
= ¥25M - ¥30M = -¥5M (behind schedule)

SPI (Schedule Performance Index) = EV / PV
= ¥25M / ¥30M = 0.83

Interpretation: Project is 17% behind schedule
```

**Cost Performance:**
```
CV (Cost Variance) = EV - AC
= ¥25M - ¥28M = -¥3M (over budget)

CPI (Cost Performance Index) = EV / AC
= ¥25M / ¥28M = 0.89

Interpretation: For every ¥1 spent, we're getting ¥0.89 of value
```

**Combined Performance:**
- SPI < 1.0 AND CPI < 1.0 = **Critical**: Behind schedule AND over budget
- SPI < 1.0 AND CPI ≥ 1.0 = **At Risk**: Behind schedule but within budget
- SPI ≥ 1.0 AND CPI < 1.0 = **At Risk**: On schedule but over budget
- SPI ≥ 1.0 AND CPI ≥ 1.0 = **Healthy**: On/ahead of schedule and within/under budget

### Step 3: Forecast Completion

**EAC (Estimate at Completion):**
```
Method 1: Atypical variance (current performance not indicative of future)
EAC = AC + (BAC - EV)
= ¥28M + (¥50M - ¥25M) = ¥53M

Method 2: Typical cost variance (expect similar performance)
EAC = BAC / CPI
= ¥50M / 0.89 = ¥56.2M (more pessimistic)

Method 3: Consider both schedule and cost performance
EAC = AC + ((BAC - EV) / (CPI × SPI))
= ¥28M + ((¥50M - ¥25M) / (0.89 × 0.83)) = ¥61.9M (most pessimistic)
```

**ETC (Estimate to Complete):**
```
ETC = EAC - AC
= ¥56.2M - ¥28M = ¥28.2M remaining
```

**VAC (Variance at Completion):**
```
VAC = BAC - EAC
= ¥50M - ¥56.2M = -¥6.2M (projected overrun)
```

**TCPI (To-Complete Performance Index):**
```
TCPI = (BAC - EV) / (BAC - AC)
= (¥50M - ¥25M) / (¥50M - ¥28M) = 1.14

Interpretation: Need 14% improvement in efficiency to complete on budget
```

### Step 4: Generate Progress Report

**Use the Progress Report Template** from `assets/progress_report_template.md`

**Key Sections:**
1. Executive Summary with overall health indicator
2. EVM analysis with SPI, CPI, forecasts
3. Milestone status
4. Budget summary
5. Quality metrics
6. Risk register summary
7. Accomplishments and upcoming activities
8. Recommendations and actions

### Step 5: Recommend Recovery Actions

**If SPI < 1.0 (Behind Schedule):**
- Fast-track: Perform activities in parallel
- Crash: Add resources to critical path
- Reduce scope: Descope "Should Have" or "Could Have" items
- Extend deadline: Negotiate with stakeholder

**If CPI < 1.0 (Over Budget):**
- Value engineering: Find less expensive solutions
- Reduce scope: Cut features to save cost
- Negotiate better vendor rates
- Increase budget: Request additional funding
- Improve efficiency: Reduce waste, improve processes

**If Both < 1.0 (Critical Situation):**
- Immediate escalation to sponsor
- Consider project viability
- Major corrective actions required
- May need scope reduction or budget increase

---

## Core Workflow 4: Risk Management

Use this workflow to systematically identify, analyze, and respond to project risks.

### Step 1: Information Gathering (14 Categories)

**Use the Risk Analysis Template** from `assets/risk_analysis_template.md`

Gather information across these categories:

1. **Project Overview**: Purpose, strategic importance, legacy system age, pain points
2. **Scope and Complexity**: Functional scope, integrations, data migration, requirements maturity
3. **Stakeholders**: Sponsor level, decision-making structure, alignment
4. **Team and Resources**: Size, roles filled, availability, skill gaps
5. **Vendors**: Prime contractor, subcontractors, contract type, SLAs
6. **Schedule**: Timeline, go-live date, external deadlines, buffer
7. **Budget**: Total budget, estimation method, contingency, funding status
8. **Requirements**: Completeness, sign-off status, change velocity, NFRs
9. **Technology**: Stack, maturity, team familiarity, architecture complexity
10. **Change Management**: Users impacted, process changes, change plan, training
11. **Quality & Testing**: Testing time, test environment, acceptance criteria
12. **Dependencies**: External dependencies, project dependencies, constraints
13. **Compliance**: Regulatory environment, standards, compliance review
14. **Success Metrics**: KPIs defined, measurement plan, expected ROI

### Step 2: Risk Identification (9 Categories)

**1. Scope and Requirements Risks**
- Requirements volatility/scope creep
- Unclear acceptance criteria
- Competing stakeholder interests

**Indicators:**
- ⚠ Requirements <70% complete
- ⚠ No formal sign-off process
- ⚠ Frequent changes (>5% per week)

**2. Schedule Risks**
- Aggressive timeline
- Hard external deadlines
- Critical path dependencies

**Indicators:**
- ⚠ Timeline <6 months for complex project
- ⚠ No schedule contingency
- ⚠ External dependencies on critical path

**3. Cost Risks**
- Budget underestimation
- Exchange rate exposure
- Cost tracking gaps

**Indicators:**
- ⚠ Parametric estimate without validation
- ⚠ No contingency reserve (<10%)
- ⚠ Fixed-price with unclear scope

**4. Quality Risks**
- Critical defects in production
- Insufficient testing
- Limited QA resources

**Indicators:**
- ⚠ Testing time <20% of schedule
- ⚠ Test environment not representative
- ⚠ No test automation

**5. Resource and Personnel Risks**
- Key person departure
- Critical skill gaps
- High turnover

**Indicators:**
- ⚠ Single point of failure
- ⚠ >50% part-time resources
- ⚠ Competing project priorities

**6. Stakeholder Risks**
- Stakeholder misalignment
- Low engagement
- Conflicting priorities

**Indicators:**
- ⚠ Sponsor not C-level
- ⚠ Multiple approval committees
- ⚠ Poor communication history

**7. Technology Risks**
- Technology immaturity
- Team unfamiliarity
- Complex architecture

**Indicators:**
- ⚠ Bleeding-edge technology
- ⚠ Many integration points (>5)
- ⚠ Performance requirements uncertain

**8. Vendor Risks**
- Vendor performance issues
- Weak SLAs
- Financial instability

**Indicators:**
- ⚠ New/unproven vendor
- ⚠ No SLAs or weak SLAs
- ⚠ Fixed-price with unclear scope

**9. External Dependency Risks**
- External delays impacting critical path
- No control over timeline
- Limited visibility

**Indicators:**
- ⚠ Critical path dependent on external party
- ⚠ No contractual commitments

### Step 3: Risk Analysis and Scoring

**Risk Score Calculation:**
```
Risk Score = Probability × Impact

Probability Scale:
- Very Low: 10%
- Low: 30%
- Medium: 50%
- High: 70%
- Very High: 90%

Impact Scale (Cost):
- Very Low: <¥500K (<2% of budget)
- Low: ¥500K-¥2M (2-5%)
- Medium: ¥2M-¥5M (5-10%)
- High: ¥5M-¥10M (10-20%)
- Very High: >¥10M (>20%)

Example:
Risk: Requirements volatility
Probability: 70% (High)
Impact: ¥3M (Medium = 7.5% of budget)
Risk Score = 0.70 × 0.075 = 0.0525 (Medium priority)
```

**Risk Priority Classification:**
- **Critical**: Score >0.25 → Immediate action, escalate to sponsor
- **High**: Score 0.15-0.25 → Active mitigation required
- **Medium**: Score 0.08-0.15 → Monitor closely, plan mitigation
- **Low**: Score <0.08 → Monitor, accept or plan contingency

### Step 4: Risk Response Planning

**Four Response Strategies:**

**1. Avoid** (Eliminate the risk)
- Change project plan to eliminate risk
- Example: Use proven technology instead of bleeding-edge

**2. Mitigate** (Reduce probability or impact)
- Take action to reduce likelihood or consequences
- Example: Add buffer time, hire expert consultant, conduct POC

**3. Transfer** (Shift risk to third party)
- Insurance, warranties, fixed-price contracts
- Example: Fixed-price contract transfers cost overrun risk to vendor

**4. Accept** (Acknowledge and monitor)
- Active: Set aside contingency reserve
- Passive: Do nothing, deal with it if it occurs

**Response Plan Components:**

```
Risk ID: R-SCH-001
Risk: Aggressive timeline causing schedule overrun
Probability: 70% (High) | Impact: 8 weeks delay | Score: 0.196 (High)

Response Strategy: Mitigate

Preventive Actions (Reduce Probability):
1. Add 15% schedule buffer to critical path - Owner: PM - By: 2025-02-15
2. Secure full-time resources (not part-time) - Owner: Sponsor - By: 2025-02-20
3. Conduct weekly schedule reviews - Owner: PM - Ongoing

Detective Actions (Early Warning):
1. Trigger: Any critical path task >2 days late
   Monitoring: Daily stand-up + MS Project tracking
   Threshold: Cumulative delays >5 days = escalate

2. Metric: SPI (Schedule Performance Index)
   Current Value: 1.0 (baseline)
   Alert Threshold: <0.95
   Critical Threshold: <0.85

Contingency Plan (If Risk Occurs):
1. Immediate Response: Fast-track parallel activities on critical path
2. Escalation: Notify sponsor if recovery plan adds >10% cost
3. Workaround: Descope "Should Have" features
4. Fallback Plan: Negotiate deadline extension with stakeholder

Resource Allocation:
- Budget Reserve: ¥1,000,000 from contingency (for fast-tracking)
- Schedule Reserve: 3 weeks buffer
- Resource Reserve: 1 additional developer available if needed

Review Schedule: Weekly in project status meeting
```

### Step 5: Risk Monitoring

**Risk Metrics Dashboard:**
```
Risk Status:
● Critical: 2    Trend: ↘ (improving)
● High: 5        Trend: → (stable)
● Medium: 8      Trend: ↗ (worsening)
● Low: 12        Trend: → (stable)

Mitigation Effectiveness: 85% on track

Risk Exposure:
Cost: ¥8,500,000 (17% of budget)
Schedule: 6 weeks

New Risks (last 30 days): 3
Closed Risks (last 30 days): 2
```

**Escalation Triggers:**
- ☑ New critical risk identified (score >0.25)
- ☑ Existing risk escalates to critical
- ☑ Mitigation budget exceeded by >10%
- ☑ Multiple high risks threaten viability
- ☑ Risk requires baseline change

**Monitoring Frequency:**
- Critical risks: Weekly review with sponsor
- High risks: Weekly review with PM
- Medium risks: Bi-weekly review
- Low risks: Monthly review

---

## Core Workflow 5: Cost Estimation

Use this workflow to estimate project costs using industry-standard methods.

### Step 1: Choose Estimation Method

**1. Analogous (Top-Down) Estimation**
- **When**: Early in project, limited detail available
- **Method**: Use historical data from similar projects
- **Accuracy**: ±25-75% (rough order of magnitude)
- **Example**: "Last CRM implementation was ¥50M, this one is 20% larger, so estimate ¥60M"

**2. Parametric Estimation**
- **When**: Have historical data and quantifiable parameters
- **Method**: Use statistical relationships (cost per unit)
- **Accuracy**: ±10-25%
- **Example**: "Cost per user story point = ¥50,000. Project has 400 story points = ¥20M"

**3. Bottom-Up Estimation**
- **When**: Detailed WBS available
- **Method**: Estimate each work package and roll up
- **Accuracy**: ±5-10% (most accurate)
- **Example**: Estimate each task individually and sum

**4. Three-Point Estimation**
- **When**: High uncertainty
- **Method**: Calculate optimistic, most likely, pessimistic estimates
- **Formula**: (Optimistic + 4×Most Likely + Pessimistic) / 6
- **Example**: O=¥40M, ML=¥50M, P=¥80M → (40 + 4×50 + 80) / 6 = ¥53.3M

### Step 2: Identify Cost Components

**Labor Costs:**
- Internal team: Role × Rate × Hours
- External contractors: Contract value
- Overtime and premium rates

**Equipment and Infrastructure:**
- Hardware: Servers, workstations, network equipment
- Software licenses: Development tools, production licenses
- Cloud services: Computing, storage, bandwidth

**Materials and Supplies:**
- Office supplies
- Training materials
- Documentation

**Vendor and Consultant Costs:**
- Professional services
- Subject matter experts
- Training providers

**Travel and Facilities:**
- Travel expenses for team
- Meeting room rentals
- Off-site workshops

**Contingency and Management Reserve:**
- Contingency: 10-20% for known risks
- Management reserve: 5-10% for unknown unknowns

### Step 3: Bottom-Up Estimation Example

```
Project: CRM Implementation

1. Project Management (10% of project)
   PM (50% × 8 months × ¥1,000,000/month) = ¥4,000,000

2. Requirements and Design (15%)
   Business Analyst (1 FTE × 2 months × ¥800,000) = ¥1,600,000
   Solution Architect (0.5 FTE × 2 months × ¥1,200,000) = ¥1,200,000
   Workshops and travel = ¥400,000
   Subtotal = ¥3,200,000

3. Development (40%)
   Tech Lead (1 FTE × 6 months × ¥1,000,000) = ¥6,000,000
   Developers (3 FTE × 6 months × ¥800,000) = ¥14,400,000
   Subtotal = ¥20,400,000

4. Testing (15%)
   QA Lead (1 FTE × 2 months × ¥900,000) = ¥1,800,000
   QA Engineers (2 FTE × 2 months × ¥700,000) = ¥2,800,000
   Test environment = ¥600,000
   Subtotal = ¥5,200,000

5. Training and Change Management (10%)
   Training materials development = ¥1,000,000
   Trainer (20 days × ¥100,000) = ¥2,000,000
   Subtotal = ¥3,000,000

6. Infrastructure (5%)
   Cloud hosting (8 months × ¥200,000) = ¥1,600,000
   Licenses = ¥800,000
   Subtotal = ¥2,400,000

7. Vendor/Consulting (5%)
   CRM platform license = ¥2,000,000

Base Estimate = ¥40,000,000

Contingency Reserve (15%) = ¥6,000,000
Management Reserve (10%) = ¥4,600,000

Total Project Budget = ¥50,600,000
```

### Step 4: Validate Estimate

**Sanity Checks:**
1. **Compare to industry benchmarks**
   - CRM implementations: ¥5,000-¥15,000 per user
   - This project: 500 users → ¥50.6M / 500 = ¥101,200/user ✓ Reasonable

2. **Compare to historical projects**
   - Last similar project: ¥45M for 450 users
   - This estimate: ¥50.6M for 500 users ✓ Proportional

3. **Check resource assumptions**
   - 3 developers × 6 months = 18 person-months
   - Industry average: 0.03-0.05 person-months per story point
   - 400 story points → 12-20 person-months ✓ Within range

4. **Verify contingency adequacy**
   - Risk exposure: ¥8.5M (from risk analysis)
   - Contingency reserve: ¥6.0M
   - Gap: ¥2.5M → May need to increase contingency or mitigate high risks

### Step 5: Present Estimate with Confidence Range

**Presentation Format:**
```
Cost Estimate Summary

Base Estimate: ¥40,000,000
Contingency (15%): ¥6,000,000
Management Reserve (10%): ¥4,600,000
──────────────────────────
Total Budget: ¥50,600,000

Confidence Range:
- Optimistic (P10): ¥45,000,000 (10% chance of being under)
- Most Likely (P50): ¥50,600,000 (median estimate)
- Pessimistic (P90): ¥62,000,000 (90% chance of being under)

Basis of Estimate:
- Method: Bottom-up estimation with parametric validation
- Assumptions: [List key assumptions]
- Exclusions: [What's not included]
- Risks: [Key cost risks and how contingency addresses them]

Estimate Accuracy: ±10% (Definitive estimate per AACE guidelines)
```

---

## Advanced Topics

### Agile Project Management with PMBOK

While PMBOK is traditionally associated with predictive (waterfall) approaches, it can be adapted for Agile:

**Agile + PMBOK Integration:**
- **Scope**: Product backlog (dynamic) + Definition of Done
- **Schedule**: Sprint planning + Release planning
- **Cost**: Story point estimation + Velocity tracking
- **Quality**: Acceptance criteria + Continuous integration
- **Risk**: Sprint retrospectives identify risks early
- **Stakeholder**: Product Owner represents stakeholders

**EVM for Agile:**
```
Planned Value (PV) = Planned story points × Story point value
Earned Value (EV) = Completed story points × Story point value
Actual Cost (AC) = Actual labor cost incurred

Example:
Sprint 5, planned 40 points, completed 35 points
Story point value = Total budget / Total story points = ¥50M / 500 = ¥100,000

PV = 40 × ¥100,000 = ¥4,000,000
EV = 35 × ¥100,000 = ¥3,500,000
AC = ¥3,800,000

SPI = 3.5M / 4.0M = 0.875 (behind planned velocity)
CPI = 3.5M / 3.8M = 0.921 (over budget)
```

### Portfolio Management

When managing multiple projects:

**Portfolio Health Scorecard:**
| Project | Budget | SPI | CPI | Risk | Overall |
|---------|--------|-----|-----|------|---------|
| Project A | ¥50M | 0.95 | 1.05 | 🟡 | 🟢 |
| Project B | ¥30M | 0.78 | 0.88 | 🔴 | 🔴 |
| Project C | ¥40M | 1.10 | 1.03 | 🟢 | 🟢 |

**Portfolio-Level Decisions:**
- Resource reallocation between projects
- Project prioritization based on strategic value
- Risk aggregation across portfolio
- Dependency management between projects

### Program Management

For large, interconnected initiatives:

**Program Components:**
- Multiple related projects
- Shared benefits realization
- Coordinated governance
- Integrated change management

**Program-Level Activities:**
- Benefits management and tracking
- Inter-project dependency management
- Consolidated reporting to executives
- Stakeholder engagement across projects

### Predictive Analytics for Project Management

**Use project_health_check.py to:**
```bash
python scripts/project_health_check.py metrics.json --output report/
```

**Input metrics.json:**
```json
{
  "schedule": {"planned_value": 30000000, "earned_value": 25000000},
  "cost": {"actual_cost": 28000000},
  "quality": {
    "defects": {"critical": 2, "high": 8, "medium": 15, "low": 25},
    "test_coverage": 75
  },
  "risks": {
    "critical": 2, "high": 5, "medium": 8, "low": 12
  }
}
```

**Output: Project Health Score (0-100)**
- 85-100: Healthy (🟢)
- 70-84: At Risk (🟡)
- <70: Critical (🔴)

---

## Quick Reference: Common Scenarios

### Scenario 1: "Project is Behind Schedule"

**Diagnosis:**
```bash
python scripts/project_health_check.py metrics.json
```

**Check SPI:**
- SPI < 0.95: Investigate causes
- Common causes: Resource constraints, scope creep, dependencies

**Recovery Actions:**
1. **Fast-Track**: Overlap activities that are normally sequential
   - Risk: May increase rework
   - Best for: Low-risk activities with clear interfaces

2. **Crash**: Add resources to critical path
   - Risk: Brooks's Law (adding people may slow things down initially)
   - Best for: Tasks that can be parallelized

3. **Descope**: Remove low-priority features
   - Use MoSCoW: Cut "Could Have" and some "Should Have" items
   - Requires stakeholder approval

4. **Extend Timeline**: Negotiate deadline extension
   - May have business impact (missed market window, regulatory deadline)

### Scenario 2: "Need to Cut Budget by 20%"

**Approach:**
1. **Value Engineering**: Find less expensive solutions
   - Use open-source instead of commercial software
   - Cloud vs on-premise cost comparison
   - Onshore vs offshore resource mix

2. **Scope Reduction**: Apply MoSCoW ruthlessly
   - Must Have only for MVP
   - Defer Should Have and Could Have to Phase 2

3. **Resource Optimization**:
   - Replace senior resources with mid-level where appropriate
   - Reduce contractor usage, use more internal resources
   - Negotiate better vendor rates (volume discounts, multi-year contracts)

4. **Schedule Extension**: Reduce burn rate
   - Extend timeline, reduce monthly spending
   - Trade-off: Delay benefits realization

**Impact Analysis:**
```
Original Budget: ¥50M
Target Budget: ¥40M (-20%)

Option 1: Scope Reduction
- Remove 30% of features (Should Have + Could Have)
- Savings: ¥10M
- Impact: Reduced functionality, may need Phase 2

Option 2: Resource Mix
- Replace 2 senior developers (¥1M/month) with mid-level (¥700k/month)
- Use offshore developers (¥400k/month vs ¥800k/month onshore)
- Savings: ¥8M over 6 months
- Impact: May increase coordination overhead, potential quality risk

Option 3: Extend Timeline
- Extend from 8 months to 10 months
- Reduce team size from 10 to 8 FTE
- Savings: ¥10M
- Impact: 2-month delay in benefits realization
```

### Scenario 3: "Stakeholders Can't Agree on Requirements"

**Resolution Process:**

**Step 1: Facilitate Requirements Workshop**
- Bring all stakeholders together
- Use facilitation techniques to surface conflicts
- Document all perspectives

**Step 2: Prioritize Using MoSCoW**
- Force prioritization: "If you must choose..."
- Make trade-offs explicit: "Feature X means cutting Feature Y"

**Step 3: Escalate to Executive Sponsor**
- Present options with pros/cons
- Let sponsor make strategic decision
- Document decision and rationale

**Step 4: Implement Change Control**
- Baseline agreed requirements
- All changes must go through CCB
- Assess impact before approval

**Step 5: Use Prototypes**
- Build low-fidelity mockups
- Get feedback on tangible designs
- Often resolves abstract disagreements

### Scenario 4: "Vendor is Underperforming"

**Escalation Path:**

**Level 1: Work with Vendor PM**
- Document specific issues and SLA breaches
- Request corrective action plan
- Set clear expectations and deadlines

**Level 2: Escalate to Vendor Management**
- Formal escalation letter
- Invoke contract clauses (penalties, service credits)
- Request senior resources or management attention

**Level 3: Invoke Contract Remedies**
- Service level credits
- Penalty clauses
- Right to terminate for cause

**Level 4: Contingency Plan**
- Have backup vendor identified
- Document knowledge transfer requirements
- Prepare transition plan

**Proactive Prevention:**
- Weekly status meetings with vendor
- Clear acceptance criteria and Definition of Done
- Regular performance reviews against SLAs
- Escalation triggers defined in advance

---

## Resources

### references/

**pmbok_knowledge_areas.md**
Comprehensive guide to PMBOK's 10 Knowledge Areas with detailed processes, tools, and best practices. Use this to understand the full scope of project management activities and ensure comprehensive coverage.

**risk_management_guide.md**
Three-phase risk management framework with 14 information gathering categories, 9 risk types, and detailed response planning. Use this for comprehensive risk assessments.

### assets/

**requirements_definition_template.md**
ISO/IEC/IEEE 29148-compliant requirements document template with functional/non-functional requirements, traceability matrix, and acceptance criteria. Use this to create professional requirements documents.

**progress_report_template.md**
Comprehensive progress report template with EVM calculations, status dashboards, and stakeholder-appropriate formatting. Use this for regular project reporting.

**risk_analysis_template.md**
Detailed risk analysis template with probability/impact assessment, risk register, heat map, and response planning. Use this for formal risk assessments.

### scripts/

**project_health_check.py**
Automated project health assessment based on EVM metrics, quality indicators, risk profile, and team health. Generates overall health score and identifies issues.

**Usage:**
```bash
python scripts/project_health_check.py metrics.json --output report/

# metrics.json format:
{
  "schedule": {"planned_value": 30000000, "earned_value": 25000000},
  "cost": {"budget_at_completion": 50000000, "actual_cost": 28000000},
  "quality": {
    "defects": {"critical": 2, "high": 8, "medium": 15, "low": 25},
    "test_coverage": 75
  },
  "risks": {"critical": 2, "high": 5, "medium": 8, "low": 12},
  "stakeholder_satisfaction": 7.5,
  "team_health": {"morale": 8, "turnover_rate": 5}
}
```

---

## Best Practices Summary

### Requirements Management
✓ Get formal sign-off on requirements before design
✓ Use MoSCoW prioritization rigorously
✓ Maintain traceability from requirement to test case
✓ Establish change control process early
✓ Write clear acceptance criteria for each requirement

### Schedule Management
✓ Include 15-20% schedule buffer/contingency
✓ Identify critical path and monitor closely
✓ Account for holidays, vacations, part-time resources
✓ Track SPI weekly and take corrective action if <0.95
✓ Document and manage dependencies rigorously

### Cost Management
✓ Use bottom-up estimation for accuracy
✓ Include 10-20% contingency reserve
✓ Track CPI weekly and forecast EAC
✓ Separate contingency (known risks) from management reserve (unknowns)
✓ Document basis of estimate and assumptions

### Risk Management
✓ Update risk register weekly
✓ Focus on top 5-10 risks, don't track everything
✓ Assign risk owners with accountability
✓ Link risk mitigation actions to project schedule
✓ Escalate critical risks (score >0.25) immediately

### Quality Management
✓ Allocate 20-30% of schedule for testing
✓ Define acceptance criteria before development
✓ Implement continuous integration and automated testing
✓ Track defect trends, not just counts
✓ Conduct regular code reviews and quality audits

### Stakeholder Management
✓ Map stakeholder influence and interest early
✓ Tailor communication to stakeholder needs
✓ Engage resistant stakeholders proactively
✓ Secure executive sponsor at C-level
✓ Document decisions and communicate broadly

### Communications
✓ Establish regular reporting cadence
✓ Use status colors (🟢🟡🔴) consistently
✓ Highlight decisions needed, not just information
✓ Keep executive updates to 1 page
✓ Use data (EVM, metrics) to build credibility

---

## Troubleshooting

### "My EVM calculations don't make sense"

**Check:**
1. **Time-phasing**: Are you comparing same time periods for PV, EV, AC?
2. **Baseline**: Is your baseline (BAC, PV) frozen or changing?
3. **Earned Value methodology**: Are you using 0/100, 50/50, or % complete?
4. **Cumulative vs. Period**: Are you calculating cumulative or period-specific?

**Common Issues:**
- PV = EV = AC = Low confidence in estimates
- CPI improving but SPI degrading = Spending less but delivering even less value
- Both indices volatile = Poor baseline or measurement approach

### "Stakeholders won't make decisions"

**Techniques:**
1. **Forced Ranking**: "If you must choose between A and B, which?"
2. **Impact Analysis**: "Not deciding means we'll implement A by default, which costs..."
3. **Time Box**: "We need a decision by Friday or we'll be delayed 2 weeks"
4. **Escalation**: "I'll escalate to sponsor for decision if we don't resolve by..."
5. **Prototype**: Show, don't tell – build quick mockup to drive concrete feedback

### "Risk register is overwhelming"

**Simplify:**
1. **Focus on Top 10**: Track only critical and high risks actively
2. **Archive Low Risks**: Move low risks to watch list
3. **Combine Related Risks**: Consolidate similar risks
4. **Use Categories**: Group risks by type for patterns
5. **Dashboard View**: Create one-page risk heat map for executives

### "Team is resisting processes"

**Balance:**
1. **Right-size formality**: Don't over-process small projects
2. **Show value**: Explain WHY (risk mitigation, clarity) not just WHAT
3. **Automate**: Use scripts (like project_health_check.py) to reduce manual work
4. **Templates**: Provide fill-in-the-blank templates to make it easy
5. **Lead by example**: PM should use processes consistently

---

## Examples

### Example 1: Enterprise CRM Implementation

**Project Context:**
- Replace 15-year-old legacy CRM with modern cloud solution
- 500 users across 3 business units
- 12-month timeline, ¥50M budget
- Multiple integrations (ERP, marketing automation, customer portal)

**Key Challenges:**
- Requirements gathering from 3 business units with different needs
- Data migration from legacy system (quality issues)
- Change management for users resistant to change
- Tight integration requirements with existing systems

**How This Skill Helps:**

1. **Requirements Definition (Workflow 1)**
   - Use requirements template to structure gathering
   - Apply MoSCoW to prioritize conflicting requirements
   - Create traceability matrix linking requirements to test cases
   - Result: 247 requirements documented, 180 Must Have, 45 Should Have, 22 Could Have

2. **Risk Management (Workflow 4)**
   - Identified 27 risks across 9 categories
   - Top risks:
     - R-001: Data quality issues in migration (P=70%, I=High, Score=0.28) 🔴
     - R-002: User resistance to change (P=50%, I=Medium, Score=0.10) 🟡
     - R-003: Integration delays from ERP team (P=50%, I=High, Score=0.20) 🟡
   - Created detailed mitigation plans for each
   - Allocated ¥8M of ¥10M contingency to top 5 risks

3. **Progress Tracking (Workflow 3)**
   - Month 6 status:
     - SPI = 0.92 (8% behind schedule due to integration delays)
     - CPI = 1.05 (5% under budget due to efficient development)
     - EAC = ¥47.6M (forecast to finish under budget)
     - TCPI = 0.94 (can afford slight inefficiency and still finish on budget)
   - Generated monthly progress reports with EVM analysis
   - Identified need to fast-track testing phase to recover schedule

4. **Outcome:**
   - Delivered 92% of Must Have requirements on time
   - Finished 5% under budget at ¥47.5M
   - Successfully migrated 485,000 customer records with 99.7% accuracy
   - User satisfaction (CSAT) increased from 7.2 to 8.9 within 3 months of go-live

### Example 2: Legacy System Migration

**Project Context:**
- Migrate 20-year-old mainframe application to modern microservices architecture
- Mission-critical system (24/7 uptime requirement)
- 200,000 transactions per day
- 18-month timeline, ¥80M budget
- Zero-downtime cutover required

**Key Challenges:**
- No documentation for legacy system (tribal knowledge)
- Complex business logic embedded in COBOL code
- Zero-downtime migration strategy required
- Regulatory compliance (financial industry)
- Skeptical stakeholders (multiple failed attempts in past)

**How This Skill Helps:**

1. **Project Plan Review (Workflow 2)**
   - Reviewed initial plan against 10 PMBOK knowledge areas
   - Identified gaps:
     - ❌ No knowledge transfer plan (tribal knowledge risk)
     - ❌ Testing time only 10% of schedule (should be 25-30% for mission-critical)
     - ❌ No rollback plan for cutover
     - ❌ Insufficient contingency (5% vs recommended 20% for high-risk project)
   - Revised plan increased budget to ¥95M and timeline to 20 months
   - Result: More realistic plan with executive buy-in

2. **Risk Management (Workflow 4)**
   - Comprehensive risk assessment identified 34 risks
   - Critical risks:
     - R-001: Unknown business rules in legacy code (P=90%, I=Very High, Score=0.45) 🔴
     - R-002: Cutover failure causing system outage (P=30%, I=Very High, Score=0.15) 🟡
     - R-003: Regulatory compliance issues (P=50%, I=High, Score=0.20) 🟡
   - Mitigation strategies:
     - R-001: Hired 2 retired developers who built original system as consultants
     - R-002: Implemented blue-green deployment with instant rollback capability
     - R-003: Engaged compliance team in design reviews from Month 1

3. **Cost Estimation (Workflow 5)**
   - Used three-point estimation for high uncertainty areas
   - Reverse engineering legacy code: O=3 months, ML=6 months, P=12 months
   - Expected value = (3 + 4×6 + 12) / 6 = 6.5 months
   - Bottom-up estimate with risk-adjusted durations
   - Final budget ¥95M with ¥15M contingency (16%)

4. **Progress Tracking (Workflow 3)**
   - Month 12 status:
     - SPI = 0.88 (12% behind schedule – reverse engineering taking longer)
     - CPI = 0.96 (4% over budget – consultant costs higher than expected)
     - EAC = ¥99M (forecast ¥4M overrun)
     - TCPI = 1.15 (need 15% efficiency improvement to stay on budget)
   - Triggered recovery plan: added 2 developers to critical path, descoped 15% of nice-to-have features
   - Result: Recovered to SPI=0.95 by Month 15

5. **Outcome:**
   - Successful zero-downtime cutover
   - All regulatory compliance requirements met
   - Delivered 2 months late (Month 22) but within revised budget at ¥94.8M
   - System performance exceeded targets: 250,000 TPS vs 200,000 target
   - Stakeholder satisfaction: 9.2/10 (compared to 3.5/10 for previous failed attempt)

---

## Conclusion

This Project Manager skill provides comprehensive, PMBOK-aligned project management capabilities. By following the structured workflows for requirements definition, progress tracking with EVM, risk management, and cost estimation, you can increase project success rates and deliver value consistently.

**Key Takeaways:**
- Use EVM (SPI, CPI) for objective progress measurement
- Manage risks proactively with three-phase approach
- Document requirements with traceability to tests
- Allocate adequate contingency (10-20%)
- Engage stakeholders systematically
- Generate data-driven status reports
- Follow PMBOK best practices adapted to your context

**Next Steps:**
1. Review the reference materials for deeper dives into each knowledge area
2. Use the templates to create project artifacts
3. Run project_health_check.py to assess current project status
4. Apply workflows incrementally – start with highest-value areas

Remember: **"Plans are worthless, but planning is everything."** - Dwight D. Eisenhower

The value of project management isn't in creating perfect plans, but in the structured thinking, risk awareness, and stakeholder alignment that comes from the planning process.
