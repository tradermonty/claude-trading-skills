# Process and Data Analysis Methodologies

## Process Analysis Techniques

### 1. Process Mapping with BPMN

**Business Process Model and Notation (BPMN) 2.0** is the ISO standard for process modeling.

**Core Elements:**

**Events** (Circles):
- ○ Start Event: Where process begins
- ◎ Intermediate Event: Occurs during process
- ⊗ End Event: Where process ends

**Activities** (Rounded Rectangles):
- Task: Single unit of work
- Sub-Process: Collapsed process containing multiple tasks
- Call Activity: Reusable process

**Gateways** (Diamonds):
- ◇ Exclusive (XOR): One path chosen
- ◆ Parallel (AND): All paths taken simultaneously
- ◇+ Inclusive (OR): One or more paths taken
- ◇? Event-Based: Wait for event to determine path

**Flows**:
- →  Sequence Flow: Order of activities
- - → Message Flow: Between different participants
- ···→ Association: Link data/text to elements

**Swim Lanes**:
- Pools: Represent different organizations
- Lanes: Represent roles/departments within organization

**Example Process:**
```
[Customer] → (Submit Order) → ◇ [Valid?]
                                 ├─[Yes]→ (Process Payment) → (Ship Product) → ⊗
                                 └─[No]→ (Notify Customer) → ⊗
```

### 2. Swimlane Diagrams

**Purpose:** Show who does what and when handoffs occur.

**When to Use:**
- Cross-functional processes
- Identifying handoff points
- Clarifying roles and responsibilities
- Finding process bottlenecks

**Example Structure:**
```
┌────────────┬────────────────────────────────────────┐
│ Customer   │ Submit Order → Receive Confirmation    │
├────────────┼────────────────────────────────────────┤
│ Sales      │         Review Order → Approve Order   │
├────────────┼────────────────────────────────────────┤
│ Warehouse  │                     Pick Items → Ship  │
├────────────┼────────────────────────────────────────┤
│ Finance    │                              Invoice   │
└────────────┴────────────────────────────────────────┘
```

**Analysis Focus:**
- Handoffs between lanes = potential delays
- Many activities in one lane = potential bottleneck
- Back-and-forth between lanes = rework or poor design

### 3. Value Stream Mapping

**Purpose:** Identify waste and optimize flow.

**Seven Wastes (TIMWOOD):**
1. **Transportation**: Unnecessary movement of materials
2. **Inventory**: Excess stock or work-in-progress
3. **Motion**: Unnecessary movement of people
4. **Waiting**: Idle time waiting for next step
5. **Over-production**: Producing more than needed
6. **Over-processing**: Doing more than customer requires
7. **Defects**: Rework due to errors

**Value-Added vs. Non-Value-Added:**
- **Value-Added**: Customer willing to pay for it, transforms product/service
- **Non-Value-Added (Necessary)**: Required by regulation/policy but customer doesn't value
- **Non-Value-Added (Waste)**: Pure waste, should be eliminated

**Metrics to Track:**
- **Cycle Time**: Time from start to finish of one unit
- **Lead Time**: Time customer waits from request to delivery
- **Process Time**: Actual work time (value-added)
- **Wait Time**: Time spent waiting
- **% Complete & Accurate**: First-pass yield
- **Process Efficiency** = Process Time / Lead Time × 100%

**Example:**
```
Current State:
Step 1: 2 days (0.5 days work, 1.5 days wait)
Step 2: 3 days (1 day work, 2 days wait)
Step 3: 1 day (0.5 days work, 0.5 days wait)

Total Lead Time: 6 days
Total Process Time: 2 days
Process Efficiency: 2/6 = 33%

Target: Reduce lead time to 3 days (50% improvement)
```

### 4. Gap Analysis

**Purpose:** Identify differences between current and desired state.

**Framework:**

**Step 1: Define Current State**
- What capabilities exist today?
- What are current metrics?
- What processes are in place?

**Step 2: Define Future State**
- What capabilities are needed?
- What are target metrics?
- What processes should exist?

**Step 3: Identify Gaps**
- Capability gaps
- Performance gaps
- Process gaps
- Technology gaps
- People/skills gaps

**Step 4: Prioritize Gaps**
- Impact on business objectives (High/Medium/Low)
- Effort to close gap (High/Medium/Low)
- Dependencies

**Step 5: Develop Action Plan**
- Initiatives to close gaps
- Timeline and milestones
- Resource requirements
- Success metrics

**Gap Analysis Template:**
| Area | Current State | Future State | Gap | Impact | Effort | Priority | Action Plan |
|------|--------------|-------------|-----|--------|--------|----------|-------------|
| Order Processing | Manual, 10 min | Automated, 2 min | 80% time reduction | High | Medium | 1 | Implement order automation |
| Customer Data | Scattered across 3 systems | Single CRM | Data integration | High | High | 2 | CRM consolidation project |

### 5. Root Cause Analysis

**5 Whys Technique:**

**Example: Website downtime incident**
```
Problem: Website was down for 3 hours

Why? → Server crashed
Why? → Database overloaded
Why? → Too many concurrent queries
Why? → No query optimization
Why? → No performance testing before launch

Root Cause: Inadequate performance testing
Corrective Action: Implement mandatory performance testing in QA process
```

**Fishbone (Ishikawa) Diagram:**

**Structure:**
```
                    People          Process
                       ↓               ↓
                        \             /
                         \           /
                          \         /
                           \       /
                            \     /
                             \   /
                              \ /
                    Problem ←─────
                              / \
                             /   \
                            /     \
                           /       \
                          /         \
                         /           \
                        /             \
                       ↓               ↓
                  Technology         Data
```

**Six Categories (6M):**
1. **Manpower** (People): Skills, training, availability
2. **Methods** (Process): Procedures, workflows, standards
3. **Machines** (Technology): Systems, tools, equipment
4. **Materials** (Data): Inputs, quality, availability
5. **Measurement**: Metrics, monitoring, KPIs
6. **Mother Nature** (Environment): External factors, conditions

**Example: High customer churn**
```
People:
- Insufficient training on product
- Poor customer service responsiveness

Process:
- Complicated onboarding
- No proactive outreach

Technology:
- System reliability issues
- Poor user interface

Data:
- Inaccurate customer records
- No usage analytics

→ Root Causes: Complicated onboarding + System reliability issues
→ Solutions: Redesign onboarding flow + Infrastructure upgrade
```

### 6. Process Improvement Methodologies

**Six Sigma DMAIC:**

1. **Define**: Define problem and project goals
2. **Measure**: Measure current process performance
3. **Analyze**: Analyze data to identify root causes
4. **Improve**: Implement solutions
5. **Control**: Sustain improvements

**Lean Principles:**
- **Value**: Define value from customer perspective
- **Value Stream**: Map all steps in value stream
- **Flow**: Make value flow without interruptions
- **Pull**: Produce only what customer demands
- **Perfection**: Continuously improve

**Kaizen (Continuous Improvement):**
- Small, incremental changes
- Involve all employees
- Focus on eliminating waste
- Quick wins accumulate to major improvements

---

## Data Analysis Techniques

### 1. Data Quality Assessment

**Six Data Quality Dimensions:**

**Accuracy**: Data correctly represents reality
- Validation: Check against source system
- Metric: % of records that match source

**Completeness**: All required data present
- Validation: Check for null/missing values
- Metric: % of required fields populated

**Consistency**: Data agrees across systems
- Validation: Cross-system reconciliation
- Metric: % of records that match across systems

**Timeliness**: Data is current and available when needed
- Validation: Check last updated timestamp
- Metric: Average data age

**Validity**: Data conforms to business rules
- Validation: Format, range, reference checks
- Metric: % of records passing validation rules

**Uniqueness**: No unwanted duplicates
- Validation: Duplicate detection algorithms
- Metric: % of unique records

**Data Quality Scorecard:**
```
Dataset: Customer Master Data

Dimension     | Score | Issues                        | Impact
--------------|-------|-------------------------------|--------
Accuracy      | 92%   | 8% of emails invalid          | Medium
Completeness  | 78%   | 22% missing phone numbers     | High
Consistency   | 85%   | Address format inconsistent   | Medium
Timeliness    | 95%   | Updated nightly               | Low
Validity      | 88%   | Some zipcodes invalid         | Medium
Uniqueness    | 91%   | 9% duplicate records          | High

Overall Score: 88% → Target: 95%
Priority Actions:
1. Deduplicate customer records (addresses Uniqueness)
2. Implement phone number collection (addresses Completeness)
```

### 2. Data Profiling

**Purpose:** Understand data structure, content, and relationships.

**Profiling Activities:**

**Column Analysis:**
- Data type
- Length/precision
- Null count and %
- Distinct values count
- Min/Max values
- Pattern analysis

**Value Distribution:**
- Frequency distribution
- Identify outliers
- Check for skewness

**Example Profile:**
```
Column: customer_age

Data Type: Integer
Total Records: 100,000
Null Count: 2,500 (2.5%)
Distinct Values: 78
Min: 18
Max: 105 ← OUTLIER (investigate)
Mean: 42.3
Median: 39
Mode: 35

Distribution:
18-25: ████░░░░░░ 15,000 (15%)
26-35: ████████░░ 28,000 (28%)
36-45: ██████████ 30,000 (30%)
46-55: ██████░░░░ 18,000 (18%)
56-65: ███░░░░░░░  7,000 (7%)
66+:   █░░░░░░░░░  2,000 (2%)

Issues Identified:
- 2.5% missing values → Implement default or mandatory field
- Age 105 seems unlikely → Data validation rule needed
```

### 3. Data Flow Analysis

**Purpose:** Understand how data moves through systems.

**Data Flow Diagram (DFD) Levels:**

**Level 0 (Context Diagram):**
- Shows system boundaries
- External entities
- High-level data flows

**Level 1:**
- Major processes
- Data stores
- Key data flows

**Level 2:**
- Detailed sub-processes
- Specific data stores
- Detailed flows

**DFD Notation:**
- □ External Entity
- ⭕ Process
- ⟹ Data Flow
- ╱╱ Data Store

**Example:**
```
[Customer] →(Order)→ ⭕(Process Order) →(Confirmation)→ [Customer]
                          ↓
                    (Order Details)
                          ↓
                    ╱╱Order Database╱╱
```

### 4. Business Intelligence & Reporting Analysis

**Report Types:**

**Operational Reports:**
- Daily/real-time updates
- Detailed, transactional data
- Support day-to-day operations
- Example: Daily sales report

**Tactical Reports:**
- Weekly/monthly summaries
- Aggregated data
- Support management decisions
- Example: Monthly performance dashboard

**Strategic Reports:**
- Quarterly/annual analysis
- High-level trends
- Support executive decisions
- Example: Annual market analysis

**Key Performance Indicators (KPIs):**

**Leading Indicators** (Predictive):
- Sales pipeline value
- Website traffic
- New customer acquisition rate
- Employee engagement score

**Lagging Indicators** (Historical):
- Revenue
- Profit margin
- Customer satisfaction
- Market share

**KPI Characteristics (SMART):**
- **Specific**: Clearly defined
- **Measurable**: Quantifiable
- **Achievable**: Realistic target
- **Relevant**: Aligned with objectives
- **Time-bound**: Defined timeframe

**Example KPI Definition:**
```
KPI: Customer Satisfaction Score (CSAT)

Definition: Average rating from post-interaction survey (1-10 scale)
Measurement: Monthly survey results
Target: 8.5 / 10
Current: 7.8 / 10
Frequency: Measured monthly, reported quarterly
Owner: Customer Service Director
Action Plan: If <8.0, initiate improvement project
```

### 5. Trend and Pattern Analysis

**Time Series Analysis:**

**Components:**
- **Trend**: Long-term increase/decrease
- **Seasonality**: Regular, periodic fluctuations
- **Cyclical**: Longer-term ups and downs (not fixed period)
- **Random**: Irregular, unpredictable variations

**Moving Averages:**
- Simple Moving Average (SMA): Equal weights
- Weighted Moving Average (WMA): Recent data weighted more
- Exponential Moving Average (EMA): Exponentially decreasing weights

**Year-over-Year (YoY) Analysis:**
```
Metric: Monthly Sales

Jan 2024: ¥12,000,000
Jan 2025: ¥15,000,000

YoY Growth = (¥15M - ¥12M) / ¥12M × 100% = 25% ↑
```

**Variance Analysis:**
```
Budget vs. Actual:

Budget: ¥10,000,000
Actual: ¥11,500,000
Variance: ¥1,500,000 (15% over budget) ⚠

Favorable Variance: Actual < Budget (for costs)
Unfavorable Variance: Actual > Budget (for costs)
```

### 6. Segmentation Analysis

**Purpose:** Group similar items for targeted analysis or action.

**Customer Segmentation:**

**RFM Analysis:**
- **Recency**: How recently did customer purchase?
- **Frequency**: How often do they purchase?
- **Monetary**: How much do they spend?

**Segmentation Example:**
```
Champions: High R, F, M → VIP treatment
Loyal Customers: High F, M → Reward programs
At Risk: High F, M, Low R → Win-back campaigns
Lost: Low R, F, M → Minimal marketing

Action Plan by Segment:
Champions (5,000 customers, ¥50M annual):
- Personal account manager
- Exclusive product previews
- Premium support

At Risk (8,000 customers, ¥20M annual):
- Targeted re-engagement campaign
- Special offers
- Survey to understand issues
```

**ABC Analysis** (Inventory/Product):
- **A items**: 20% of items, 80% of value → Tight control
- **B items**: 30% of items, 15% of value → Moderate control
- **C items**: 50% of items, 5% of value → Loose control

### 7. Comparative Analysis

**Benchmarking:**
- Internal: Compare across departments/regions
- Competitive: Compare to competitors
- Functional: Compare to best practices in other industries
- Generic: Compare across industries

**Example:**
```
Metric: Order Processing Time

Our Company: 24 hours
Competitor A: 12 hours ← Best in class
Competitor B: 18 hours
Industry Average: 20 hours

Gap Analysis:
Current: 24 hours
Target (Best in Class): 12 hours
Gap: 12 hours (50% improvement needed)

Benchmarking Actions:
1. Study Competitor A's process
2. Identify automation opportunities
3. Implement process improvements
4. Re-measure quarterly
```

### 8. Decision Analysis

**Decision Matrix:**

**Weighted Scoring Model:**
```
Options: CRM System Selection

Criteria         Weight  Option A  Option B  Option C
Functionality    40%     9         7         8
Cost             30%     6         9         7
Ease of Use      20%     8         6         9
Vendor Support   10%     7         8         8

Weighted Scores:
Option A: (9×0.4)+(6×0.3)+(8×0.2)+(7×0.1) = 7.9
Option B: (7×0.4)+(9×0.3)+(6×0.2)+(8×0.1) = 7.7
Option C: (8×0.4)+(7×0.3)+(9×0.2)+(8×0.1) = 8.1 ← Best

Recommendation: Option C (highest weighted score)
```

**Cost-Benefit Analysis:**
```
Project: Implement Order Automation

Costs (One-time):
- Software License: ¥5,000,000
- Implementation: ¥3,000,000
- Training: ¥1,000,000
Total One-time: ¥9,000,000

Costs (Annual):
- Software Maintenance: ¥500,000
- Support: ¥300,000
Total Annual: ¥800,000

Benefits (Annual):
- Labor Savings: ¥3,000,000 (4 FTE × ¥750,000)
- Error Reduction: ¥1,200,000 (fewer refunds/corrections)
- Faster Processing: ¥800,000 (customer satisfaction → retention)
Total Annual Benefits: ¥5,000,000

Net Annual Benefit: ¥5,000,000 - ¥800,000 = ¥4,200,000

Payback Period: ¥9,000,000 / ¥4,200,000 = 2.14 years

NPV (3 years, 10% discount):
Year 0: -¥9,000,000
Year 1: +¥3,818,182 (¥4,200,000 / 1.1)
Year 2: +¥3,471,074 (¥4,200,000 / 1.1²)
Year 3: +¥3,155,522 (¥4,200,000 / 1.1³)
NPV = ¥1,444,778 ✓ Positive, recommend approval

ROI (3 years): ((¥4.2M×3) - ¥9M) / ¥9M × 100% = 40%
```

---

## Best Practices

### Process Analysis
✓ Start with high-level process map, then drill down
✓ Involve process participants (they know reality)
✓ Document both current state and future state
✓ Focus on end-to-end customer journey
✓ Identify pain points and bottlenecks
✓ Quantify process metrics (time, cost, quality)
✓ Look for automation opportunities
✓ Consider regulatory and compliance requirements

### Data Analysis
✓ Start with data quality assessment
✓ Understand data lineage and sources
✓ Document data definitions clearly
✓ Validate assumptions with data owners
✓ Use visualization to communicate insights
✓ Consider data security and privacy
✓ Establish data governance
✓ Automate recurring analysis where possible

### Business Analysis
✓ Understand business context before diving into data
✓ Ask "So what?" - always tie to business impact
✓ Use multiple analysis techniques to validate findings
✓ Present options, not just recommendations
✓ Quantify benefits and costs
✓ Consider implementation feasibility
✓ Plan for change management
✓ Define success metrics upfront

---

## Analysis Toolkit Selection Guide

| Need | Recommended Technique | Output |
|------|----------------------|---------|
| Understand current process | Process mapping (BPMN), Swimlane | Process model |
| Identify process waste | Value stream mapping | Current vs future state map |
| Find improvement opportunities | Gap analysis | Gap assessment matrix |
| Understand root cause | 5 Whys, Fishbone diagram | Root cause documentation |
| Assess data quality | Data profiling, quality scorecard | Data quality report |
| Understand data movement | Data flow diagram | DFD levels 0-2 |
| Track performance | KPI dashboard, trend analysis | Metrics dashboard |
| Segment customers | RFM analysis, clustering | Segmentation model |
| Compare options | Decision matrix, cost-benefit | Recommendation with scoring |
| Evaluate investment | NPV, ROI, payback period | Financial analysis |

---

*These methodologies combine Lean, Six Sigma, BABOK, and industry best practices for comprehensive process and data analysis.*
