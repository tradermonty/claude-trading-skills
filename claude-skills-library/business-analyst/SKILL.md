---
name: business-analyst
description: Professional business analysis skill aligned with BABOK® Guide v3 standards. Use this skill when you need to elicit and document requirements, analyze business processes, conduct stakeholder analysis, develop business cases, perform gap analysis, or create business requirements documents (BRD). Ideal for requirements gathering, process mapping (BPMN), financial analysis (ROI, NPV), stakeholder engagement, and solution evaluation. Triggers: "gather requirements", "create business case", "analyze process", "stakeholder analysis", "gap analysis", "BRD", "functional requirements", or requests involving business analysis tasks.
---

# Business Analyst

## Overview

This skill provides comprehensive business analysis capabilities aligned with the BABOK® (Business Analysis Body of Knowledge) Guide v3 from the International Institute of Business Analysis (IIBA®). It integrates proven methodologies, best practices, and templates to support business analysts in bridging the gap between business needs and technical solutions.

The skill is structured around BABOK's **6 Knowledge Areas**:

- **Business Analysis Planning and Monitoring**: Plan approach and monitor execution
- **Elicitation and Collaboration**: Gather information from stakeholders
- **Requirements Life Cycle Management**: Manage requirements from inception to retirement
- **Strategy Analysis**: Define business need and justify investment
- **Requirements Analysis and Design Definition**: Analyze and specify requirements
- **Solution Evaluation**: Assess solution performance and identify improvements

This skill is designed for both experienced business analysts seeking to standardize their approach and those new to formal business analysis who need structured guidance.

## When to Use This Skill

Use this skill when you need to:

- **Gather Requirements**: "Conduct stakeholder interviews to gather requirements for the new system"
- **Create Business Requirements Document**: "Generate a BRD for our CRM replacement project"
- **Develop Business Case**: "Create a business case for process automation initiative"
- **Analyze Processes**: "Map the current order-to-cash process and identify inefficiencies"
- **Stakeholder Analysis**: "Identify and analyze stakeholders for this digital transformation"
- **Gap Analysis**: "Compare current capabilities with future state requirements"
- **Financial Analysis**: "Calculate ROI and NPV for this investment"
- **Solution Evaluation**: "Assess whether the implemented solution meets business objectives"

### Example Requests:

1. "I need to gather requirements from multiple stakeholders for a new customer portal. Help me plan the approach."
2. "Create a business case for automating our invoice processing. Initial investment is ¥10M, expected savings ¥3M per year."
3. "Map our current customer onboarding process using BPMN notation and identify bottlenecks."
4. "Perform a stakeholder analysis for our digital transformation project."
5. "Compare three vendor options using weighted scoring - functionality 40%, cost 30%, ease of use 20%, support 10%."

## Business Analysis Framework

### BABOK 6 Knowledge Areas

1. **Business Analysis Planning and Monitoring**
   - Planning BA approach
   - Stakeholder engagement planning
   - Governance and information management

2. **Elicitation and Collaboration**
   - Interviews, workshops, observation
   - Document analysis, surveys, prototyping
   - Confirming and communicating results

3. **Requirements Life Cycle Management**
   - Tracing and maintaining requirements
   - Prioritizing (MoSCoW, Value vs. Complexity)
   - Assessing changes and approving

4. **Strategy Analysis**
   - Current and future state analysis
   - SWOT, PESTLE, Value Chain Analysis
   - Risk assessment and change strategy

5. **Requirements Analysis and Design Definition**
   - Specifying and modeling requirements
   - Verifying and validating
   - Defining design options and recommending solutions

6. **Solution Evaluation**
   - Measuring solution performance
   - Analyzing performance measures
   - Recommending actions to increase value

---

## Core Workflow 1: Requirements Elicitation

Use this workflow when gathering requirements from stakeholders.

### Step 1: Plan Elicitation Approach

**Determine Elicitation Techniques Based on Context:**

**Use Interviews When:**
- Need deep understanding from specific individuals
- Exploring sensitive topics
- Gathering expert knowledge
- One-on-one or small group (2-3 people)

**Use Workshops When:**
- Need consensus from multiple stakeholders
- Collaborative requirements definition
- Cross-functional process mapping
- 6-15 participants with facilitation

**Use Surveys When:**
- Large user base (50+)
- Quantitative data needed
- Prioritization input from many people
- Geographic distribution

**Use Observation When:**
- Current process poorly documented
- Tacit knowledge (users can't articulate)
- Identifying pain points in workflow
- Understanding context and environment

**Use Document Analysis When:**
- Existing documentation available
- System replacement project
- Compliance-driven requirements
- Understanding current state

**Use Prototyping When:**
- Requirements unclear or abstract
- User interface design
- Validating concepts
- Iterative refinement needed

### Step 2: Prepare for Elicitation

**Create Elicitation Plan:**
```
Objective: [What you want to learn]

Participants:
- [Name/Role] - [Why they're important]
- [Name/Role] - [Why they're important]

Technique: [Interview/Workshop/etc.]
Duration: [Time needed]
Date/Time: [When]
Location: [Where/virtual link]

Agenda:
1. [Topic 1] - [Time allocation]
2. [Topic 2] - [Time allocation]
3. [Topic 3] - [Time allocation]

Questions/Topics:
- [Question 1]
- [Question 2]
- [Question 3]
```

**Interview Question Types:**

**Open-Ended**: "Walk me through your current process for..."
- Encourages detailed responses
- Good for exploration

**Probing**: "Can you tell me more about...?" "Why is that important?"
- Digs deeper
- Uncovers root causes

**Closed**: "How many orders do you process per day?"
- Specific, quantifiable answers
- Good for facts and metrics

**Hypothetical**: "If you could change one thing about this process, what would it be?"
- Elicits desires and pain points
- Uncovers improvement opportunities

### Step 3: Conduct Elicitation

**Active Listening Techniques:**
- **Paraphrase**: "So what you're saying is..." (confirm understanding)
- **Summarize**: "To recap the key points..." (synthesize)
- **Clarify**: "Can you explain what you mean by..." (remove ambiguity)
- **Probe**: "Tell me more about..." (go deeper)
- **Acknowledge**: "I understand that's frustrating..." (build rapport)

**Document As You Go:**
- Capture verbatim for important statements
- Note questions for follow-up
- Record decisions and agreements
- Identify areas needing more exploration

### Step 4: Analyze and Organize Requirements

**Requirements Categories:**

**Business Requirements** (WHY):
- High-level business objectives
- Strategic goals
- Business capabilities needed
- Example: "Reduce order processing time by 50%"

**Stakeholder Requirements** (WHO needs WHAT):
- Needs of specific stakeholder groups
- User experience expectations
- Operational constraints
- Example: "Sales reps need mobile access to customer data"

**Functional Requirements** (WHAT the solution does):
- Specific system behaviors
- Business rules
- Calculations and processes
- Example: "System shall validate credit limit before accepting order"

**Non-Functional Requirements** (HOW WELL):
- Performance: Response time, throughput
- Security: Authentication, authorization, encryption
- Usability: Ease of use, accessibility
- Reliability: Uptime, error handling
- Example: "System shall respond within 2 seconds for 95% of transactions"

### Step 5: Validate and Confirm

**Validation Checklist:**
- ✓ Clear and unambiguous
- ✓ Complete (all necessary information)
- ✓ Consistent (no conflicts)
- ✓ Testable (can verify implementation)
- ✓ Traceable (linked to business need)
- ✓ Feasible (technically and financially possible)
- ✓ Necessary (supports business objective)

**Confirmation Methods:**
- Present back to stakeholders
- Create prototypes/mockups
- Write scenarios and examples
- Conduct formal review meetings

### Step 6: Document Requirements

**Use Business Requirements Document Template** from `assets/business_requirements_document_template.md`

**Key Sections:**
1. Executive Summary
2. Business Problem/Opportunity
3. Business Objectives and Success Metrics
4. Scope (In/Out)
5. Stakeholder Analysis
6. Current State Analysis
7. Future State Vision
8. Requirements Detail (with IDs)
9. Business Rules
10. Acceptance Criteria

---

## Core Workflow 2: Business Process Analysis

Use this workflow to analyze and improve business processes.

### Step 1: Understand Current Process (As-Is)

**Information Gathering:**
- Interview process participants
- Observe process execution
- Review process documentation
- Collect process metrics

**Key Questions:**
- What triggers this process?
- Who performs each step?
- What inputs are needed?
- What outputs are produced?
- What systems/tools are used?
- What are the handoff points?
- Where do delays occur?
- What are common problems?

### Step 2: Map Current Process

**Use BPMN (Business Process Model and Notation):**

**Core Elements:**
- ○ Events: Start, intermediate, end
- ▭ Activities: Tasks, sub-processes
- ◇ Gateways: Exclusive (XOR), parallel (AND), inclusive (OR)
- → Sequence flows
- 📊 Data objects

**Create Swimlane Diagram:**
```
┌─────────────┬──────────────────────────────────┐
│ Customer    │ ○ → Submit Order → Wait         │
├─────────────┼──────────────────────────────────┤
│ Sales       │      ← Review → ◇ Approve?      │
│             │                  ├─[Yes]→        │
│             │                  └─[No]→ Reject  │
├─────────────┼──────────────────────────────────┤
│ Warehouse   │              ← Pick → Ship → ●  │
└─────────────┴──────────────────────────────────┘
```

**Document Process Metrics:**
- Cycle Time: Time from start to finish
- Wait Time: Time spent waiting
- Process Time: Actual work time
- Error Rate: Frequency of errors
- Cost per Transaction: Resource cost

### Step 3: Analyze for Issues

**Value Stream Mapping - Identify Waste (TIMWOOD):**
- **T**ransportation: Unnecessary movement of materials
- **I**nventory: Excess work-in-progress
- **M**otion: Unnecessary movement of people
- **W**aiting: Idle time
- **O**ver-production: Producing too early/much
- **O**ver-processing: Extra steps not valued
- **D**efects: Rework and errors

**Process Efficiency Calculation:**
```
Process Efficiency = (Value-Added Time / Total Lead Time) × 100%

Example:
Total Lead Time: 6 days
Value-Added Work: 2 days
Process Efficiency: 2/6 = 33%

Target: Improve to 60%+ efficiency
```

**Common Problem Patterns:**
- Multiple handoffs between roles/systems
- Manual data entry (error-prone)
- Approvals creating bottlenecks
- Rework loops
- Lack of automation
- Poor system integration

### Step 4: Root Cause Analysis

**5 Whys Technique:**
```
Problem: High order error rate (15%)

Why? → Data entry mistakes
Why? → Manual entry from paper forms
Why? → No digital order system
Why? → Budget not approved for system
Why? → ROI not demonstrated

Root Cause: Lack of business case
Solution: Develop compelling business case
```

**Fishbone Diagram Categories:**
- People: Skills, training, motivation
- Process: Procedures, workflow, controls
- Technology: Systems, tools, infrastructure
- Data: Quality, availability, accuracy
- Environment: Physical space, culture
- Measurement: Metrics, monitoring

### Step 5: Design Future Process (To-Be)

**Improvement Strategies:**

**Eliminate**: Remove non-value-added steps
- Example: Remove unnecessary approval steps

**Automate**: Use technology to replace manual work
- Example: Auto-populate customer data from CRM

**Simplify**: Reduce complexity
- Example: Combine multiple forms into one

**Integrate**: Connect disparate systems
- Example: Integrate order system with inventory

**Standardize**: Create consistent approach
- Example: Standard templates and procedures

**Future State Design Principles:**
- Minimize handoffs
- Automate repeatable tasks
- Integrate systems end-to-end
- Enable self-service where possible
- Build in quality checks
- Provide real-time visibility

### Step 6: Quantify Benefits

**Process Improvement Metrics:**
```
Current State → Future State:

Cycle Time:     6 days → 2 days (67% reduction)
Error Rate:     15% → 2% (87% reduction)
Cost/Trans:     ¥500 → ¥150 (70% reduction)
Capacity:       500/day → 1,200/day (140% increase)

Annual Benefit Calculation:
- Labor savings: [X] FTE × ¥750,000 = ¥[Amount]
- Error reduction: [X] fewer errors × ¥[Cost] = ¥[Amount]
- Capacity increase: [X] additional revenue = ¥[Amount]
Total Annual Benefit: ¥[Amount]
```

---

## Core Workflow 3: Stakeholder Analysis and Engagement

Use this workflow to identify, analyze, and engage stakeholders effectively.

### Step 1: Identify Stakeholders

**Brainstorm All Possible Stakeholders:**

**By Category:**
- **Decision Makers**: Who approves/rejects?
- **Funders**: Who provides budget?
- **Users**: Who will use the solution?
- **Impacted**: Whose work will change?
- **Supporters**: Who provides resources?
- **Experts**: Who has specialized knowledge?
- **Implementers**: Who builds/delivers?
- **Regulators**: Who enforces compliance?

**Don't Forget:**
- Internal customers
- External customers
- Vendors/partners
- Regulatory bodies
- Executive leadership
- IT/operations teams
- End users at all levels
- Union representatives (if applicable)

### Step 2: Analyze Stakeholders

**Use Stakeholder Analysis Template** from `assets/stakeholder_analysis_template.md`

**Power/Interest Matrix:**
```
           High Interest
                │
    Keep        │        Manage
    Informed    │        Closely
                │
Low ────────────┼────────────── High
Power           │            Power
                │
    Monitor     │         Keep
                │        Satisfied
                │
            Low Interest
```

**Classify Each Stakeholder:**
- **High Power, High Interest**: Key Players - manage closely
- **High Power, Low Interest**: Keep Satisfied - regular updates
- **Low Power, High Interest**: Keep Informed - detailed communication
- **Low Power, Low Interest**: Monitor - minimal effort

**Attitude Assessment:**
- **Champion**: Actively promotes project
- **Supporter**: Positive but not vocal
- **Neutral**: Uncommitted
- **Skeptic**: Doubtful but not opposed
- **Blocker**: Actively opposed

### Step 3: Develop Engagement Strategy

**Tailor Strategy by Stakeholder Type:**

**For Champions:**
- Leverage to influence others
- Ask them to advocate
- Keep them enthusiastic
- Give them visibility

**For Skeptics:**
- Understand root causes of doubt
- Address concerns with data/evidence
- Involve in solution design
- Show quick wins

**For Blockers:**
- Understand their true objections
- Find common ground
- Isolate if cannot convert
- Escalate if blocking progress

**Communication Planning:**

| Stakeholder | Purpose | Format | Frequency | Message Focus |
|-------------|---------|--------|-----------|---------------|
| Executive | Decision-making | 1-pager | Monthly | ROI, strategic alignment, risks |
| Project Team | Coordination | Stand-up | Daily | Tasks, blockers, dependencies |
| End Users | Buy-in | Demo | Bi-weekly | WIIFM, ease of use, support |
| IT Ops | Technical alignment | Technical review | Weekly | Architecture, integration, support |

### Step 4: Build and Maintain Relationships

**Relationship-Building Techniques:**
- **Active Listening**: Understand their perspective
- **Empathy**: Acknowledge their concerns
- **Transparency**: Share information openly
- **Reliability**: Follow through on commitments
- **Collaboration**: Involve them appropriately
- **Recognition**: Credit their contributions

**RACI Matrix:**
Create clear accountability:
- **R**esponsible: Does the work
- **A**ccountable: Has final authority
- **C**onsulted: Provides input
- **I**nformed: Kept updated

---

## Core Workflow 4: Business Case Development

Use this workflow to justify investments and secure funding.

### Step 1: Define the Problem/Opportunity

**Problem Statement Template:**
```
[Stakeholder group] is facing [problem] which results in [negative impact].
This is caused by [root cause].
If not addressed, [consequence].
```

**Example:**
"The sales team is facing delays in order processing (average 10 minutes per order) which results in customer dissatisfaction and lost revenue. This is caused by manual data entry into disconnected systems. If not addressed, we will be unable to scale beyond 500 orders/day as business grows."

**Quantify Current State:**
- Costs: ¥[Amount] per year
- Lost revenue: ¥[Amount] per year
- Time wasted: [X] hours per week
- Error rate: [X]%
- Customer impact: [X]% dissatisfaction

### Step 2: Identify Solution Options

**Generate 3-5 Options:**

**Option 1: Do Nothing (Baseline)**
- Current state continues
- Opportunity cost quantified

**Option 2-4: Alternative Solutions**
- Different approaches
- Varying cost/benefit profiles
- Different risk levels

**Example Options:**
1. Do Nothing
2. Hire additional staff (¥15M/year)
3. Implement low-code automation (¥8M initial, ¥1M/year)
4. Buy enterprise system (¥25M initial, ¥3M/year)

### Step 3: Analyze Each Option

**For Each Option, Calculate:**

**Costs:**
- Initial investment (one-time)
- Annual operating costs
- Implementation costs
- Training costs
- Total Cost of Ownership (TCO)

**Benefits:**
- Cost savings (labor, efficiency)
- Revenue impact (capacity, quality)
- Risk reduction
- Strategic value

**Financial Metrics:**
- ROI = (Net Benefit / Total Cost) × 100%
- Payback Period = Investment / Annual Cash Flow
- NPV = Discounted cash flows
- IRR = Internal rate of return

**Use business_analysis.py script:**
```bash
python scripts/business_analysis.py financial \
  --investment 10000000 \
  --annual-benefit 3000000 \
  --annual-cost 500000 \
  --years 3 \
  --sensitivity
```

### Step 4: Compare Options

**Weighted Scoring Model:**
```json
{
  "options": {
    "Option A": {"financial": 9, "risk": 6, "strategic_fit": 8, "time": 7},
    "Option B": {"financial": 7, "risk": 8, "strategic_fit": 7, "time": 9},
    "Option C": {"financial": 5, "risk": 9, "strategic_fit": 6, "time": 8}
  },
  "weights": {
    "financial": 0.4,
    "risk": 0.2,
    "strategic_fit": 0.3,
    "time": 0.1
  }
}
```

**Run comparison:**
```bash
python scripts/business_analysis.py compare options.json
```

### Step 5: Make Recommendation

**Business Case Structure:**

Use **Business Case Template** from `assets/business_case_template.md`

**Executive Summary (1 page):**
- Problem statement
- Recommended solution
- Investment required
- Expected return
- Recommendation (Approve/Reject)

**Key Sections:**
1. Business Problem/Opportunity
2. Strategic Alignment
3. Solution Options Analysis
4. Recommended Solution Detail
5. Financial Analysis (ROI, NPV, Payback)
6. Risk Assessment
7. Implementation Approach
8. Success Metrics

**Financial Summary:**
```
Investment:          ¥10,000,000
Annual Benefit:      ¥3,500,000
Annual Cost:         ¥500,000
Net Annual Benefit:  ¥3,000,000

Payback Period:      3.3 years
ROI (5 years):       50%
NPV (5 years, 10%):  ¥1,350,000

Recommendation: APPROVE
```

---

## Core Workflow 5: Gap Analysis

Use this workflow to identify differences between current and desired state.

### Step 1: Define Current State

**Assess Current Capabilities:**
- What processes exist today?
- What systems are in place?
- What capabilities do we have?
- What are current metrics?

**Example:**
```
Current State: Customer Onboarding

Process:      Manual, paper-based, 15 steps
Systems:      Excel spreadsheets, email
Capabilities: Can process 20 customers/week
Metrics:      10-day average onboarding time
              25% error rate
              Customer satisfaction: 6.5/10
```

### Step 2: Define Future State

**Describe Desired State:**
- What should processes look like?
- What capabilities are needed?
- What are target metrics?
- What systems should exist?

**Example:**
```
Future State: Customer Onboarding

Process:      Automated workflow, 7 steps
Systems:      Integrated CRM with digital forms
Capabilities: Can process 100 customers/week
Metrics:      2-day average onboarding time
              <5% error rate
              Customer satisfaction: 9.0/10
```

### Step 3: Identify Gaps

**Gap Categories:**

**Process Gaps:**
- Steps that need to change
- New processes needed
- Processes to eliminate

**Technology Gaps:**
- Systems to implement
- Integrations needed
- Tools to acquire

**People/Skills Gaps:**
- New skills required
- Training needed
- Roles to create

**Data Gaps:**
- Data quality issues
- Missing data elements
- Integration requirements

**Policy/Governance Gaps:**
- Policies to update
- Governance to establish
- Compliance requirements

### Step 4: Prioritize Gaps

**Impact vs. Effort Matrix:**
```
High Impact,  Low Effort  → Quick Wins (do first)
High Impact,  High Effort → Strategic Projects (plan carefully)
Low Impact,   Low Effort  → Fill-Ins (do if time permits)
Low Impact,   High Effort → Time Wasters (avoid or defer)
```

**Gap Prioritization:**
| Gap | Impact | Effort | Priority | Dependencies |
|-----|--------|--------|----------|--------------|
| Implement CRM | High | High | 1 | None |
| Digital forms | High | Medium | 2 | CRM integration |
| Training program | Medium | Low | 3 | After CRM go-live |

### Step 5: Develop Action Plan

**For Each High-Priority Gap:**
```
Gap: [Description]

Current State: [What exists today]
Future State:  [What's needed]

Actions to Close Gap:
1. [Action 1] - Owner: [Name] - By: [Date] - Cost: ¥[Amount]
2. [Action 2] - Owner: [Name] - By: [Date] - Cost: ¥[Amount]
3. [Action 3] - Owner: [Name] - By: [Date] - Cost: ¥[Amount]

Success Criteria: [How to measure gap is closed]
Timeline: [Start] to [End]
Total Cost: ¥[Amount]
```

---

## Advanced Topics

### Requirements Traceability

**Traceability Matrix:**
```
Business Need → Business Req → Functional Req → Design → Test Case → Deployment

Example:
Business Need: "Improve customer service"
└─ BR-001: "Reduce response time"
   └─ FR-015: "Auto-route tickets by category"
      └─ Design-03: "Routing rules engine"
         └─ TC-087: "Verify routing accuracy"
            └─ Release 2.1: "Deployed 2025-03-15"
```

**Benefits:**
- Impact analysis (what changes if requirement changes)
- Coverage analysis (all requirements tested)
- Compliance proof (tracing to regulations)

### Agile Business Analysis

**User Stories Format:**
```
As a [role],
I want [capability],
So that [benefit].

Acceptance Criteria:
- Given [precondition]
- When [action]
- Then [expected result]
```

**Example:**
```
As a sales representative,
I want to access customer order history from my mobile device,
So that I can answer customer questions during site visits.

Acceptance Criteria:
- Given I'm logged in on mobile app
- When I search for a customer
- Then I see their complete order history within 2 seconds
- And I can filter by date range
- And I can view order details
```

**Story Mapping:**
- Horizontal: User journey (activities)
- Vertical: Priority (releases)
- Creates shared understanding of scope

### Data Analysis for Business Insights

**Use business_analysis.py for data profiling:**
```bash
python scripts/business_analysis.py profile sales_data.csv --output profile_report.json
```

**Analysis Techniques:**

**Trend Analysis:**
- Time series patterns
- Year-over-year growth
- Seasonal trends
- Moving averages

**Segmentation:**
- Customer segments (RFM analysis)
- Product categories (ABC analysis)
- Geographic regions
- Behavioral patterns

**Comparative Analysis:**
- Benchmark to industry
- Compare to targets
- Before/after analysis
- Variance analysis

---

## Quick Reference: Common Scenarios

### Scenario 1: "Stakeholders Can't Agree on Requirements"

**Resolution Process:**

1. **Facilitate Requirements Workshop**
   - Bring conflicting parties together
   - Use neutral facilitation
   - Document all perspectives

2. **Apply MoSCoW Prioritization**
   - Force ranking: "If you must choose..."
   - Make trade-offs explicit
   - "Feature X means cutting Feature Y"

3. **Escalate to Decision Maker**
   - Present options with pros/cons
   - Show impact analysis
   - Let sponsor decide strategically

4. **Implement Change Control**
   - Baseline agreed requirements
   - Changes go through formal process
   - Impact assessed before approval

5. **Use Prototypes**
   - Build mockups to make concrete
   - Visual designs resolve abstract debates
   - Iterate based on feedback

### Scenario 2: "Need to Build Business Case Quickly"

**Fast-Track Approach:**

1. **Problem Statement** (30 min)
   - What's the problem?
   - What's the impact? (quantify)
   - What happens if we don't act?

2. **Solution Options** (1 hour)
   - Identify 2-3 realistic options
   - Rough cost estimates
   - High-level benefits

3. **Financial Analysis** (30 min)
   - Use business_analysis.py script
   - Calculate ROI, Payback, NPV
   - Quick sensitivity analysis

4. **Risk Assessment** (30 min)
   - Top 5 risks only
   - Probability and impact
   - Basic mitigation strategies

5. **Recommendation** (30 min)
   - Write 2-page executive summary
   - Clear recommendation
   - Next steps

**Total Time: 3 hours for initial business case**

### Scenario 3: "Process is Broken - Where to Start?"

**Systematic Approach:**

1. **Map Current Process** (As-Is)
   - Observe and interview participants
   - Document actual process (not policy)
   - Create BPMN or swimlane diagram

2. **Collect Metrics**
   - Cycle time per step
   - Wait times
   - Error rates
   - Cost per transaction

3. **Identify Pain Points**
   - Where are delays?
   - Where do errors occur?
   - What do users complain about?
   - Where is rework happening?

4. **Root Cause Analysis**
   - Use 5 Whys or Fishbone
   - Get to underlying causes
   - Don't treat symptoms

5. **Design Future State**
   - Apply improvement strategies (eliminate, automate, simplify)
   - Map To-Be process
   - Calculate expected improvements

### Scenario 4: "How to Prioritize Requirements?"

**Prioritization Frameworks:**

**MoSCoW:**
- Must Have: 40% of requirements
- Should Have: 30% of requirements
- Could Have: 20% of requirements
- Won't Have: 10% of requirements

**Value vs. Complexity:**
```
High Value + Low Complexity = Do First
High Value + High Complexity = Phase 2 (plan carefully)
Low Value + Low Complexity = Nice to have
Low Value + High Complexity = Don't do
```

**Kano Model:**
- Basic Needs: Must have (dissatisfiers if absent)
- Performance Needs: More is better
- Excitement Needs: Unexpected delighters

**Forced Ranking:**
- "If you could only have 10 features, which ones?"
- Forces real prioritization decisions

---

## Resources

### references/

**babok_framework.md**
Comprehensive guide to BABOK® Guide v3 with all 6 knowledge areas. Covers business analysis planning, elicitation techniques, requirements management, strategy analysis, requirements analysis, and solution evaluation. Use this as your primary BA methodology reference.

**process_data_analysis.md**
Detailed guide to process analysis techniques (BPMN, value stream mapping, gap analysis, root cause analysis) and data analysis methods (data profiling, data quality, BI reporting, segmentation). Use this for process improvement and data-driven analysis.

### assets/

**business_requirements_document_template.md**
Comprehensive BRD template following industry standards. Includes business problem, objectives, scope, stakeholder analysis, current/future state, requirements detail, business rules, and acceptance criteria. Use this for documenting requirements.

**business_case_template.md**
Professional business case template with financial analysis, risk assessment, options comparison, and recommendation sections. Includes ROI, NPV, payback period calculations. Use this to justify investments and secure funding.

**stakeholder_analysis_template.md**
Complete stakeholder analysis framework with power/interest matrix, engagement strategies, communication planning, and RACI matrix. Use this for identifying and managing stakeholders throughout project lifecycle.

### scripts/

**business_analysis.py**
Python toolkit for business analysis tasks:
- Financial analysis (ROI, NPV, Payback, IRR, sensitivity analysis)
- Business metrics calculation (CSAT, NPS, churn, CLTV)
- Data profiling and quality assessment
- Options comparison with weighted scoring

**Usage Examples:**
```bash
# Financial analysis with sensitivity
python scripts/business_analysis.py financial \
  --investment 10000000 \
  --annual-benefit 3000000 \
  --years 3 \
  --sensitivity

# Profile dataset
python scripts/business_analysis.py profile sales_data.csv --output report.json

# Compare options
python scripts/business_analysis.py compare options.json
```

---

## Best Practices Summary

### Requirements Elicitation
✓ Use multiple elicitation techniques
✓ Involve diverse stakeholders
✓ Ask open-ended questions
✓ Listen actively without bias
✓ Confirm understanding continuously
✓ Document requirements immediately
✓ Distinguish needs from solutions

### Requirements Documentation
✓ Write clear, unambiguous requirements
✓ Make requirements testable
✓ Maintain traceability
✓ Use consistent templates
✓ Version control all documents
✓ Get formal sign-off
✓ Keep requirements up to date

### Stakeholder Management
✓ Identify stakeholders early and comprehensively
✓ Understand motivations and concerns
✓ Communicate proactively
✓ Tailor communication style
✓ Build trust through transparency
✓ Manage expectations realistically
✓ Document commitments

### Process Analysis
✓ Map current state first (as-is)
✓ Involve process participants
✓ Quantify current metrics
✓ Identify root causes, not symptoms
✓ Design future state with stakeholders
✓ Quantify expected benefits
✓ Plan for change management

### Business Case Development
✓ Quantify problem impact
✓ Develop multiple options
✓ Calculate financial metrics (ROI, NPV, Payback)
✓ Assess risks and mitigation
✓ Include sensitivity analysis
✓ Present clear recommendation
✓ Define success metrics

### Analysis and Modeling
✓ Use standard notations (BPMN, UML)
✓ Keep models simple and focused
✓ Validate models with stakeholders
✓ Use appropriate level of detail
✓ Update models as requirements evolve

---

## Troubleshooting

### "Requirements Keep Changing"

**Root Causes:**
- Unclear business objectives
- Stakeholders not aligned
- Inadequate elicitation
- No change control process

**Solutions:**
1. Re-establish business objectives
2. Get executive sponsor engaged
3. Implement formal change control
4. Assess impact before accepting changes
5. Consider Agile approach if requirements truly volatile

### "Stakeholders Won't Participate"

**Root Causes:**
- Don't see value
- Too busy
- Afraid of change
- Unclear role/expectations

**Solutions:**
1. Get executive sponsor to mandate participation
2. Make participation easy (short sessions, convenient times)
3. Show "WIIFM" (What's In It For Me)
4. Build relationships first
5. Start with champions, build momentum

### "Can't Quantify Benefits"

**Root Causes:**
- Lack of baseline metrics
- Soft benefits (intangible)
- Complex attribution

**Solutions:**
1. Establish baseline measurements now
2. Use proxy metrics
3. Quantify range (conservative to optimistic)
4. Focus on relative improvement
5. Include qualitative benefits with quantitative

### "Business Case Rejected"

**Common Reasons:**
- ROI too low or payback too long
- Risks too high
- Not strategically aligned
- Poor presentation/communication

**Recovery Actions:**
1. Understand specific objections
2. Can you improve financial case? (reduce cost, increase benefit)
3. Can you reduce risk? (pilot, phased approach)
4. Can you strengthen strategic alignment?
5. Consider smaller scope for Phase 1

---

## Examples

### Example 1: E-Commerce Platform Requirements

**Project Context:**
- Build new B2C e-commerce platform
- Replace 10-year-old legacy system
- Target: 50,000 daily visitors, 5,000 daily orders
- Budget: ¥80M, Timeline: 12 months

**How This Skill Helps:**

1. **Requirements Elicitation (Workflow 1)**
   - Conducted interviews with: Marketing Director, Sales Managers (3), Customer Service Lead, IT Director
   - Held requirements workshops with: E-commerce team (8 people), Customer service reps (12 people)
   - Analyzed existing system documentation and customer feedback
   - Created prototypes for key user journeys
   - Result: 287 requirements documented (165 Must Have, 82 Should Have, 40 Could Have)

2. **Stakeholder Analysis (Workflow 3)**
   - Identified 25 key stakeholders across 6 departments
   - Power/Interest analysis: 8 high-power/high-interest (manage closely)
   - Created tailored communication plan for each stakeholder group
   - RACI matrix for all major decisions
   - Result: 95% stakeholder engagement in workshops, zero major conflicts

3. **Business Case (Workflow 4)**
   - Problem: Limited capacity (500 orders/day), poor mobile experience (70% mobile traffic, 3% conversion)
   - Solution: Modern e-commerce platform with mobile-first design
   - Investment: ¥80M (software ¥40M, implementation ¥25M, training ¥5M, contingency ¥10M)
   - Benefits: ¥25M/year (increased conversion +1.5%, increased capacity, reduced support costs)
   - Financial Metrics: ROI 94% (3 years), NPV ¥8.2M, Payback 3.2 years
   - Result: APPROVED by board

4. **Outcome:**
   - Launched on time and 5% under budget
   - Mobile conversion increased from 3% to 5.2% (73% improvement)
   - Order capacity increased to 8,000/day (60% above target)
   - Customer satisfaction increased from 7.8 to 9.1
   - ROI target achieved in 2.8 years (ahead of projection)

### Example 2: Order Processing Automation

**Project Context:**
- Manual order processing taking 10 min per order
- 15% error rate causing customer complaints
- Need to scale from 500 to 1,000 orders/day
- Small company (50 employees)

**How This Skill Helps:**

1. **Process Analysis (Workflow 2)**
   - Observed 20 order processing sessions
   - Mapped current process with swimlane diagram
   - Identified bottlenecks:
     - Manual data entry from email/phone (5 min, 20% of errors)
     - Credit check in separate system (2 min wait)
     - Inventory check manual lookup (2 min, 5% of errors)
     - Order confirmation email manual (1 min)
   - Process efficiency: 3 min value-add / 10 min total = 30%

2. **Gap Analysis (Workflow 5)**
   - Current: Manual, disconnected systems, 10 min per order
   - Future: Automated workflow, integrated systems, 2 min per order
   - Gaps:
     - Need online order form (eliminate manual entry)
     - Need CRM integration (auto credit check)
     - Need ERP integration (auto inventory check)
     - Need automated email templates

3. **Business Case (Workflow 4)**
   - Investment: ¥10M (software ¥5M, integration ¥3M, training ¥1M, contingency ¥1M)
   - Benefits:
     - Labor savings: 2 FTE × ¥750K = ¥1.5M/year
     - Error reduction: Fewer refunds/rework = ¥1.2M/year
     - Capacity increase: Can handle 2x volume = ¥2M/year revenue
     - Total annual benefit: ¥4.7M/year
   - ROI: 141% (3 years), NPV: ¥1.8M, Payback: 2.1 years
   - Result: APPROVED

4. **Outcome:**
   - Implemented in 6 months
   - Processing time reduced to 2.5 min (75% improvement, slightly above target)
   - Error rate reduced to 1.5% (90% improvement)
   - Customer satisfaction increased from 7.2 to 8.7
   - Actual ROI exceeded projection due to additional efficiency gains

---

## Conclusion

This Business Analyst skill provides comprehensive capabilities aligned with BABOK® Guide v3 standards. By following structured workflows for requirements elicitation, process analysis, stakeholder management, business case development, and gap analysis, you can deliver high-quality business analysis that bridges the gap between business needs and technical solutions.

**Key Takeaways:**
- Use multiple elicitation techniques to gather comprehensive requirements
- Map and analyze processes systematically to identify improvements
- Engage stakeholders proactively throughout the project lifecycle
- Develop compelling business cases with quantified benefits
- Maintain requirements traceability from business need to implementation
- Apply industry-standard tools and techniques (BPMN, MoSCoW, RACI, etc.)
- Document thoroughly using professional templates

**Next Steps:**
1. Review the BABOK framework reference for deeper methodology understanding
2. Use the templates to create professional business analysis deliverables
3. Run business_analysis.py to perform financial and data analysis
4. Apply workflows to your current projects incrementally

Remember: **"The value of business analysis isn't in creating perfect documents, but in facilitating shared understanding and enabling informed decisions."**

Business analysis is fundamentally about communication, collaboration, and clarity - helping organizations make better decisions through structured thinking and stakeholder engagement.
