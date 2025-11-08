# BABOK Framework Reference

## Business Analysis Body of Knowledge (BABOK®) Guide

This reference is aligned with BABOK® Guide v3 from the International Institute of Business Analysis (IIBA®).

---

## Overview

Business Analysis is the practice of enabling change in an enterprise by defining needs and recommending solutions that deliver value to stakeholders.

**Core Concept:** Business analysts identify business needs, determine solutions, and bridge the gap between business problems and technology solutions.

---

## 6 BABOK Knowledge Areas

### 1. Business Analysis Planning and Monitoring

**Purpose:** Plan the approach to business analysis work and monitor its execution.

**Key Activities:**

#### 1.1 Plan Business Analysis Approach
- Define BA approach for the initiative
- Select methodologies (Agile, Waterfall, Hybrid)
- Define deliverables and activities
- Establish timing and sequence

**Decision Framework:**
```
Project Characteristics → BA Approach

Predictive (Waterfall):
- Stable requirements
- Fixed scope/budget/timeline
- Regulated environment
- Large, complex systems

Adaptive (Agile):
- Evolving requirements
- Flexible scope
- Rapid delivery cycles
- Customer collaboration

Hybrid:
- Mix of stable and evolving requirements
- Phased delivery
- Some regulatory constraints
```

#### 1.2 Plan Stakeholder Engagement
- Identify all stakeholders
- Analyze stakeholder characteristics
- Define collaboration approach
- Plan communication strategy

**Stakeholder Analysis Matrix:**
| Stakeholder | Interest | Influence | Attitude | Engagement Strategy |
|-------------|----------|-----------|----------|---------------------|
| Executive Sponsor | High | High | Supportive | Keep satisfied, monthly briefings |
| End Users | High | Medium | Neutral | Involve in workshops, frequent demos |
| IT Team | Medium | High | Resistant | Collaborate, address concerns |

#### 1.3 Plan Business Analysis Governance
- Define decision-making process
- Establish change control process
- Define prioritization approach
- Set approval authorities

#### 1.4 Plan Business Analysis Information Management
- Define how BA information will be stored
- Establish traceability approach
- Define reuse strategy
- Plan for information access and security

#### 1.5 Identify Business Analysis Performance Improvements
- Assess current BA practices
- Identify improvement opportunities
- Recommend and implement changes
- Measure effectiveness

---

### 2. Elicitation and Collaboration

**Purpose:** Obtain information from stakeholders and confirm results.

**Key Techniques:**

#### 2.1 Prepare for Elicitation
- Understand scope of elicitation
- Select elicitation techniques
- Identify sources of information
- Logistical arrangements

#### 2.2 Conduct Elicitation

**Primary Techniques:**

**Brainstorming**
- Generate many ideas quickly
- No criticism during idea generation
- Encourage wild ideas
- Build on others' ideas
- **When to use:** New product features, problem-solving, innovation

**Document Analysis**
- Review existing documentation
- Identify reusable requirements
- Understand current state
- **When to use:** System replacement, process improvement, compliance

**Focus Groups**
- Facilitated discussion with pre-qualified participants
- Gather attitudes, opinions, preferences
- 6-12 participants typical
- **When to use:** Product design, user experience, market research

**Interviews**
- One-on-one or small group discussions
- Structured, semi-structured, or unstructured
- Follow-up on specific topics
- **When to use:** Expert knowledge, sensitive topics, detailed exploration

**Observation**
- Watch users perform their work
- Identify unspoken needs and pain points
- Understand context
- **When to use:** Process improvement, usability, tacit knowledge

**Prototyping**
- Create mock-up or working model
- Obtain feedback on tangible designs
- Clarify requirements iteratively
- **When to use:** User interfaces, new concepts, unclear requirements

**Survey/Questionnaire**
- Collect information from large groups
- Quantitative data collection
- Statistical analysis
- **When to use:** Large user base, trend analysis, prioritization

**Workshops**
- Facilitated, focused session
- Achieve specific objectives
- Collaborative decision-making
- **When to use:** Requirements gathering, consensus building, planning

#### 2.3 Confirm Elicitation Results
- Compare information from multiple sources
- Resolve inconsistencies
- Gain consensus
- Document and communicate

#### 2.4 Communicate Business Analysis Information
- Determine format and presentation
- Communicate to stakeholders
- Store for future reference
- Maintain traceability

#### 2.5 Manage Stakeholder Collaboration
- Engage stakeholders throughout
- Manage conflicts
- Build consensus
- Maintain trust and credibility

---

### 3. Requirements Life Cycle Management

**Purpose:** Manage and maintain requirements from inception to retirement.

#### 3.1 Trace Requirements
- Establish relationships between requirements
- Link requirements to business objectives
- Link requirements to solution components
- Enable impact analysis

**Traceability Matrix Example:**
| Business Need | Business Requirement | Functional Requirement | Solution Component | Test Case |
|---------------|---------------------|------------------------|-------------------|-----------|
| Improve customer satisfaction | Reduce order processing time | Auto-populate customer data | CRM integration | TC-045 |

#### 3.2 Maintain Requirements
- Track requirement status
- Update as changes occur
- Maintain attributes (priority, status, owner, etc.)
- Version control

**Requirement Attributes:**
- **ID**: Unique identifier
- **Title**: Short description
- **Description**: Detailed explanation
- **Rationale**: Why it's needed
- **Priority**: Must Have / Should Have / Could Have / Won't Have
- **Status**: Proposed / Approved / Implemented / Verified
- **Owner**: Responsible stakeholder
- **Source**: Where it came from
- **Complexity**: High / Medium / Low
- **Risk**: Associated risks

#### 3.3 Prioritize Requirements

**Prioritization Techniques:**

**MoSCoW:**
- **Must Have**: Non-negotiable, project fails without it
- **Should Have**: Important but not critical
- **Could Have**: Desirable but can be deferred
- **Won't Have**: Out of scope for this release

**Value vs. Complexity Matrix:**
```
High Value, Low Complexity → Quick Wins (do first)
High Value, High Complexity → Strategic Projects (plan carefully)
Low Value, Low Complexity → Fill-Ins (do if time permits)
Low Value, High Complexity → Time Wasters (avoid or defer)
```

**Kano Model:**
- **Basic Needs**: Expected features (dissatisfiers if absent)
- **Performance Needs**: More is better (satisfaction increases linearly)
- **Excitement Needs**: Unexpected delighters (high satisfaction if present)

#### 3.4 Assess Requirements Changes
- Evaluate proposed changes
- Analyze impact (scope, schedule, cost, risk)
- Recommend approve/reject/defer
- Update affected requirements

**Change Impact Assessment Template:**
```
Change Request: [ID and description]

Impact Analysis:
- Scope: [What changes in deliverables]
- Schedule: [X weeks delay or acceleration]
- Cost: ¥[Additional or saved cost]
- Quality: [Impact on quality attributes]
- Risk: [New risks or risk mitigation]

Recommendation: Approve / Reject / Defer
Rationale: [Justification]
```

#### 3.5 Approve Requirements
- Formal approval process
- Signoff from appropriate stakeholders
- Baseline requirements
- Communicate approved baseline

---

### 4. Strategy Analysis

**Purpose:** Define business need, identify solutions, and justify investment.

#### 4.1 Analyze Current State
- Understand business environment
- Assess internal and external factors
- Identify problems and opportunities
- Document current state

**Current State Analysis Techniques:**

**SWOT Analysis:**
- **Strengths**: Internal positive factors
- **Weaknesses**: Internal negative factors
- **Opportunities**: External positive factors
- **Threats**: External negative factors

**PESTLE Analysis:**
- **Political**: Government policies, regulations
- **Economic**: Market conditions, economic trends
- **Social**: Demographics, cultural trends
- **Technological**: Technology advancements
- **Legal**: Laws, regulations, compliance
- **Environmental**: Sustainability, climate

**Value Chain Analysis:**
- Primary activities: Inbound logistics, operations, outbound logistics, marketing/sales, service
- Support activities: Firm infrastructure, HR, technology, procurement
- Identify where value is created and where inefficiencies exist

#### 4.2 Define Future State
- Describe desired future state
- Identify capabilities needed
- Define business objectives
- Articulate vision

**Future State Definition:**
```
Vision Statement: [Compelling picture of future]

Success Metrics:
- KPI 1: [Specific, measurable metric]
- KPI 2: [Specific, measurable metric]
- KPI 3: [Specific, measurable metric]

Capabilities Required:
- Capability 1: [What the organization must be able to do]
- Capability 2: [What the organization must be able to do]

Timeframe: [When will this be achieved]
```

#### 4.3 Assess Risks
- Identify potential risks
- Analyze probability and impact
- Develop risk responses
- Monitor and control

**Business Risk Categories:**
- **Strategic Risks**: Market changes, competitive threats
- **Operational Risks**: Process failures, resource constraints
- **Financial Risks**: Budget overruns, funding issues
- **Compliance Risks**: Regulatory non-compliance
- **Reputational Risks**: Brand damage, customer dissatisfaction

#### 4.4 Define Change Strategy
- Determine approach to transition
- Assess organizational readiness
- Plan stakeholder engagement
- Define communication approach

**Change Readiness Assessment:**
```
Readiness Factors:
1. Sponsorship: [Executive support level]
2. Organizational Culture: [Receptiveness to change]
3. Resource Availability: [People, budget, time]
4. Previous Change Experience: [Success or failure history]
5. Urgency: [Compelling reason to change]

Readiness Score: [High / Medium / Low]
Change Approach: [Big bang / Phased / Pilot]
```

---

### 5. Requirements Analysis and Design Definition

**Purpose:** Analyze requirements and define designs that meet stakeholder needs.

#### 5.1 Specify and Model Requirements

**Requirement Types:**

**Business Requirements:**
- High-level business objectives
- Strategic goals
- Business capabilities needed

**Stakeholder Requirements:**
- Needs of specific stakeholder groups
- User experience expectations
- Operational constraints

**Solution Requirements:**
- **Functional Requirements**: What the solution must do
- **Non-Functional Requirements**: Quality attributes (performance, security, usability)

**Data Requirements:**
- Data entities and attributes
- Data quality requirements
- Data lifecycle

**Transition Requirements:**
- Temporary capabilities needed for transition
- Training requirements
- Data migration requirements

**Modeling Techniques:**

**Process Models:**
- **Flowcharts**: Simple process flows
- **BPMN** (Business Process Model and Notation): Standard process modeling
- **Swimlane Diagrams**: Show roles and handoffs
- **Value Stream Maps**: Identify waste and optimization opportunities

**Data Models:**
- **Entity-Relationship Diagrams** (ERD): Data structure and relationships
- **Data Flow Diagrams** (DFD): How data moves through system
- **Data Dictionary**: Detailed data element definitions

**Use Case Models:**
- **Use Case Diagrams**: Actors and their interactions
- **Use Case Descriptions**: Detailed interaction flows
- **User Stories**: Agile-style requirements (As a [role], I want [capability], so that [benefit])

#### 5.2 Verify Requirements
- Check requirements for quality
- Ensure completeness, correctness, consistency
- Validate traceability
- Assess feasibility

**Requirements Quality Checklist:**
- ✓ **Clear**: Unambiguous, single interpretation
- ✓ **Concise**: Succinct, no unnecessary information
- ✓ **Complete**: All necessary information provided
- ✓ **Consistent**: No conflicts with other requirements
- ✓ **Testable**: Can verify implementation
- ✓ **Traceable**: Linked to business need and solution
- ✓ **Feasible**: Technically and financially possible
- ✓ **Atomic**: Describes single feature/function

#### 5.3 Validate Requirements
- Ensure requirements deliver value
- Confirm stakeholder needs are met
- Check alignment with business goals
- Obtain stakeholder agreement

#### 5.4 Define Requirements Architecture
- Structure and organize requirements
- Define relationships between requirements
- Establish reusable requirements
- Define allocation to releases

**Requirements Organization:**
```
Business Requirements (WHY)
└── Stakeholder Requirements (WHO needs WHAT)
    └── Solution Requirements (HOW)
        ├── Functional Requirements
        ├── Non-Functional Requirements
        ├── Data Requirements
        └── Transition Requirements
```

#### 5.5 Define Design Options
- Identify potential solutions
- Analyze design options
- Recommend preferred option
- Document design decisions

**Solution Evaluation Criteria:**
- **Feasibility**: Technical, operational, financial
- **Risk**: Implementation and operational risks
- **Alignment**: Strategic fit
- **Cost**: Total cost of ownership
- **Benefit**: Value delivered
- **ROI**: Return on investment

#### 5.6 Analyze Potential Value and Recommend Solution
- Assess each option's potential value
- Compare costs and benefits
- Consider risks and assumptions
- Recommend solution

**Financial Analysis Techniques:**

**Return on Investment (ROI):**
```
ROI = (Net Benefit / Total Cost) × 100%

Example:
Investment: ¥50,000,000
Annual Benefit: ¥15,000,000
Annual Cost: ¥3,000,000
Net Annual Benefit: ¥12,000,000

Payback Period = ¥50M / ¥12M = 4.2 years
ROI (Year 1) = (¥12M - ¥50M) / ¥50M = -76% (negative first year)
ROI (5 years) = ((¥12M × 5) - ¥50M) / ¥50M = 120%
```

**Net Present Value (NPV):**
```
NPV = Σ [Cash Flow / (1 + r)^t] - Initial Investment

Where:
r = discount rate (e.g., 10%)
t = time period (years)

Interpretation:
NPV > 0 → Project adds value, should be accepted
NPV = 0 → Break even
NPV < 0 → Project destroys value, should be rejected
```

**Payback Period:**
```
Payback Period = Initial Investment / Annual Cash Flow

Shorter payback = Less risk, faster return
```

---

### 6. Solution Evaluation

**Purpose:** Assess solution performance and identify improvements.

#### 6.1 Measure Solution Performance
- Define performance metrics
- Collect performance data
- Analyze actual vs. expected performance
- Report findings

**Performance Metrics Framework:**

**Leading Indicators** (Predictive):
- User adoption rate
- Training completion rate
- System utilization
- Process adherence

**Lagging Indicators** (Results):
- Customer satisfaction (CSAT, NPS)
- Process cycle time
- Error rates
- Cost savings
- Revenue impact

**Example Metrics:**
```
Business Objective: Improve customer service

Metrics:
- First Call Resolution: Target 85%, Actual 78% ❌
- Average Handle Time: Target 5 min, Actual 4.5 min ✓
- Customer Satisfaction: Target 8.5/10, Actual 8.2/10 ⚠
- Abandonment Rate: Target <5%, Actual 3% ✓

Overall Status: 🟡 At Risk
Recommendation: Focus on improving first call resolution
```

#### 6.2 Analyze Performance Measures
- Interpret measurement results
- Identify root causes of variances
- Identify improvement opportunities
- Recommend actions

**Root Cause Analysis Techniques:**

**5 Whys:**
```
Problem: Customer complaints increased 30%

Why? → Order errors increased
Why? → Data entry mistakes increased
Why? → New system has poor user interface
Why? → Insufficient user testing before launch
Why? → Tight timeline didn't allow for testing

Root Cause: Inadequate testing due to schedule pressure
Solution: Implement proper UAT process for future releases
```

**Fishbone (Ishikawa) Diagram:**
```
Categories of causes:
- People: Skills, training, motivation
- Process: Procedures, workflow, controls
- Technology: Systems, tools, infrastructure
- Data: Quality, availability, accuracy
- Environment: Physical workspace, culture
```

#### 6.3 Assess Solution Limitations
- Identify constraints and issues
- Evaluate impact of limitations
- Recommend corrective actions
- Assess need for new capabilities

#### 6.4 Assess Enterprise Limitations
- Identify organizational constraints
- Evaluate organizational readiness
- Identify capability gaps
- Recommend organizational improvements

#### 6.5 Recommend Actions to Increase Solution Value
- Identify enhancement opportunities
- Prioritize recommendations
- Develop business case for changes
- Present recommendations to stakeholders

**Enhancement Evaluation:**
```
Enhancement: Add mobile app capability

Business Value:
- Increase user accessibility
- Improve customer satisfaction
- Competitive advantage

Cost: ¥8,000,000 (development) + ¥1,000,000/year (support)
Benefit: ¥3,500,000/year (productivity + revenue)
NPV (3 years, 10% discount): ¥500,000
Payback: 2.7 years

Recommendation: Approve for Phase 2
Priority: Should Have
```

---

## Business Analysis Competencies

### Analytical Thinking and Problem Solving
- Break down complex problems
- Identify root causes
- Think critically and objectively
- Apply creative solutions

### Behavioral Characteristics
- Ethics and trustworthiness
- Personal accountability
- Teamwork and collaboration
- Negotiation and conflict resolution

### Business Knowledge
- Industry knowledge
- Organizational knowledge
- Solution knowledge
- Methodology knowledge

### Communication Skills
- Verbal communication
- Written communication
- Listening skills
- Facilitation skills

### Interaction Skills
- Stakeholder engagement
- Negotiation
- Conflict management
- Leadership and influencing

### Tools and Technology
- Business analysis tools
- Office productivity tools
- Communication tools
- Modeling tools

---

## Key Deliverables

### Strategic Level
1. **Business Case**: Justification for investment
2. **Vision Statement**: Compelling future state
3. **Strategy Document**: Approach to achieve objectives
4. **Feasibility Study**: Technical, operational, financial viability

### Tactical Level
1. **Business Requirements Document** (BRD): Business objectives and requirements
2. **Functional Requirements Document** (FRD): Detailed functional specifications
3. **Use Cases**: Detailed interaction scenarios
4. **Process Models**: Current and future state processes
5. **Data Models**: Data structure and relationships

### Operational Level
1. **User Stories**: Agile requirements format
2. **Acceptance Criteria**: Definition of done
3. **Test Cases**: Verification scenarios
4. **Training Materials**: User documentation
5. **Transition Plan**: Cutover approach

---

## Best Practices

### Requirements Elicitation
✓ Use multiple elicitation techniques
✓ Involve the right stakeholders
✓ Distinguish needs from wants
✓ Listen actively without bias
✓ Confirm understanding continuously

### Requirements Documentation
✓ Use consistent templates
✓ Write clear, concise, testable requirements
✓ Maintain traceability
✓ Version control all documents
✓ Review and validate with stakeholders

### Stakeholder Management
✓ Identify all stakeholders early
✓ Understand their needs and concerns
✓ Communicate proactively and frequently
✓ Build trust and credibility
✓ Manage expectations realistically

### Analysis and Modeling
✓ Select appropriate modeling techniques
✓ Keep models simple and focused
✓ Use standard notations (BPMN, UML, etc.)
✓ Validate models with stakeholders
✓ Update models as requirements evolve

### Change Management
✓ Anticipate and manage resistance
✓ Communicate the "why" behind changes
✓ Involve users early and often
✓ Provide adequate training and support
✓ Celebrate successes and learn from failures

---

## Common Pitfalls to Avoid

✗ **Gold plating**: Adding unnecessary features
✗ **Scope creep**: Uncontrolled requirement additions
✗ **Analysis paralysis**: Over-analyzing, under-delivering
✗ **Assumption without validation**: Assuming stakeholder needs
✗ **Poor communication**: Inadequate stakeholder engagement
✗ **Lack of traceability**: Can't track requirements to business needs
✗ **Ignoring non-functional requirements**: Focus only on features
✗ **No change control**: Accepting all changes without impact analysis
✗ **Skipping validation**: Not confirming requirements meet needs
✗ **Technical bias**: Jumping to solution before understanding problem

---

## Quick Reference: When to Use What

**Understanding Business Problem:**
→ Use: Current state analysis, SWOT, root cause analysis, 5 Whys

**Defining Solution Scope:**
→ Use: Scope modeling, context diagrams, MoSCoW prioritization

**Gathering Requirements:**
→ Use: Interviews, workshops, observation, prototyping, surveys

**Documenting Requirements:**
→ Use: BRD, FRD, use cases, user stories, acceptance criteria

**Analyzing Processes:**
→ Use: Process modeling (BPMN), swimlane diagrams, value stream mapping

**Analyzing Data:**
→ Use: ERD, data flow diagrams, data dictionary

**Assessing Feasibility:**
→ Use: Cost-benefit analysis, ROI, NPV, risk assessment

**Managing Changes:**
→ Use: Change impact assessment, traceability matrix, version control

**Measuring Success:**
→ Use: KPIs, metrics dashboard, performance analysis, gap analysis

---

*This framework follows BABOK® Guide v3 from the International Institute of Business Analysis (IIBA®). BABOK® and IIBA® are registered trademarks owned by International Institute of Business Analysis.*
