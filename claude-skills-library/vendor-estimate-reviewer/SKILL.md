---
name: vendor-estimate-reviewer
description: This skill should be used when reviewing vendor estimates for software development projects. Use this skill when you need to evaluate whether a vendor's cost estimate, timeline, and approach are reasonable and whether the project is likely to succeed. This skill helps identify gaps, risks, overestimates, underestimates, and unfavorable contract terms. It generates comprehensive Markdown review reports with actionable recommendations to optimize costs while ensuring project success.
---

# Vendor Estimate Reviewer

## Overview

This skill provides comprehensive evaluation of vendor estimates for software development projects, from the client's perspective. Use this skill when you receive an estimate from a vendor (development company, contractor, or agency) and need to determine if it's reasonable, complete, and likely to lead to project success.

The skill evaluates:
- **Scope completeness**: Are all requirements covered? What's missing?
- **Cost reasonableness**: Are rates and effort estimates aligned with market standards?
- **Risk identification**: What could go wrong? What are the red flags?
- **Project feasibility**: Is the timeline realistic? Is the team appropriate?
- **Contract terms**: Are terms fair and protective of client interests?

The skill generates detailed Markdown reports with findings, risk assessments, and actionable recommendations.

## When to Use This Skill

Use this skill when:
- You've received a vendor estimate/quotation for software development
- You need to compare multiple vendor estimates
- You want to validate if an estimate is reasonable before contract signing
- You need to prepare negotiation points with a vendor
- You want to identify potential project risks early
- You need documentation for stakeholder approval

**Supported estimate formats**: Excel (.xlsx, .xls), CSV, PDF, or structured text descriptions

## Core Capabilities

This skill provides five integrated workflows:

1. **Initial Review and Triage**: Quick assessment to identify obvious red flags and determine review depth needed
2. **Detailed Analysis and Assessment**: Comprehensive evaluation across 12 dimensions with reference to industry standards
3. **Vendor Clarification Preparation**: Generate specific questions and clarification requests for vendor
4. **Final Review and Recommendation**: Synthesize findings into executive summary with go/no-go recommendation
5. **Decision Support**: Provide structured framework for stakeholder decision-making

---

## Workflow 1: Initial Review and Triage

Use this workflow when you first receive a vendor estimate and need to quickly assess its quality and identify any immediate concerns.

### Step 1: Gather Context

Collect key information about the estimate:
- Vendor name and background
- Project name and high-level scope
- Your budget (if available)
- Any specific concerns or focus areas
- Estimate format (Excel, PDF, etc.)

### Step 2: Quick Automated Analysis (Optional)

If the estimate is in Excel or CSV format, run the automated analysis script:

```bash
python scripts/analyze_estimate.py vendor_estimate.xlsx \
  --vendor "Acme Development" \
  --project "CRM System Modernization" \
  --budget 500000 \
  --output initial_review.md \
  --verbose
```

The script will:
- Parse the estimate file
- Calculate summary metrics
- Check phase distribution against industry norms
- Identify round numbers and estimation quality issues
- Flag obvious red flags
- Generate preliminary Markdown report

**Note**: The automated analysis provides a good starting point but should be supplemented with manual review.

### Step 3: Red Flag Check

Review the estimate against critical warning signs (from `references/risk_factors.md` Section 10):

**Critical red flags** (any of these require immediate attention):
- Estimate is 30%+ lower than competitors without clear justification
- Vague task descriptions like "Development" or "Testing" without details
- Missing critical phases (no requirements analysis, design, or testing)
- All team members allocated at 100% (unrealistic)
- Zero contingency buffer
- No documented assumptions
- Testing is <10% of total effort
- Large upfront payment (>30%) with minimal deliverables
- Missing non-functional requirements (security, performance, scalability)

If 3+ red flags are present, recommend immediate vendor clarification before proceeding with detailed review.

### Step 4: Determine Review Depth

Based on red flags and project criticality:

- **Quick Review** (2-4 hours): Low-value project (<$100K), low red flags (0-1), experienced vendor
- **Standard Review** (1 day): Medium project ($100K-$500K), some red flags (2-4), new vendor
- **Comprehensive Review** (2-3 days): High-value project (>$500K), multiple red flags (5+), critical system

### Step 5: Generate Initial Findings Summary

Create a brief summary (can use `assets/checklist_template.md` Section 10 for structure):
- Total cost and comparison to budget
- Red flags count and severity
- Immediate concerns requiring clarification
- Recommended next steps
- Recommended review depth

**Output**: Initial triage report (1-2 pages) with go/no-go for detailed review

---

## Workflow 2: Detailed Analysis and Assessment

Use this workflow to conduct comprehensive evaluation of the estimate across all dimensions.

### Step 1: Prepare Reference Materials

Load the three comprehensive reference documents into context as needed:

1. **`references/review_checklist.md`**: Systematic 12-section checklist covering all review dimensions
   - Use Sections 1-9 for detailed analysis
   - Use Section 10 for red flag validation
   - Use Section 12 for final recommendation criteria

2. **`references/cost_estimation_standards.md`**: Industry benchmarks and standards
   - Section 1: Labor rate benchmarks by role and region
   - Section 2: Effort estimation standards (phase distribution, team composition)
   - Section 3: Project size benchmarks by type
   - Section 4-5: Overhead costs and validation formulas
   - Section 7: Red flags in cost estimation

3. **`references/risk_factors.md`**: 10 risk categories with mitigation strategies
   - Sections 1-6: Primary risk areas (scope, estimation, resources, technical, process, PM)
   - Sections 7-9: Contract, organizational, and domain risks
   - Section 10: Risk scoring framework

**Strategy**: Don't load all references at once. Load specific sections as needed during analysis.

### Step 2: Scope and Requirements Analysis

Evaluate scope completeness using `references/review_checklist.md` Section 1:

**Questions to answer**:
- Are all functional requirements included?
- Are non-functional requirements (NFRs) addressed?
  - Performance (response time, throughput)
  - Security (authentication, authorization, encryption)
  - Scalability (user growth, data volume)
  - Availability (uptime requirements)
- Is data migration scope defined?
- Are integrations with existing systems specified?
- Is documentation and training included?

**Common missing items** (check against checklist):
- Environment setup (dev, staging, production)
- CI/CD pipeline setup
- Third-party service integrations (payment, email, SMS)
- Security testing and penetration testing
- Performance testing and optimization
- UAT support
- Post-launch support/warranty period
- Knowledge transfer sessions

**Look for** in `references/risk_factors.md` Section 1:
- Incomplete requirements (Risk 1.1)
- Gold plating / over-engineering (Risk 1.2)
- Scope ambiguity (Risk 1.3)

**Document findings**:
- Missing items list
- Ambiguous areas requiring clarification
- Over-engineered components
- Scope risk score (low/medium/high)

### Step 3: Work Breakdown Structure (WBS) Analysis

Evaluate task organization using `references/review_checklist.md` Section 2:

**Check WBS quality**:
- Completeness: All phases present (requirements → design → development → testing → deployment)
- Granularity: Tasks broken down to 8-80 hour units
- Clarity: Each task has clear description and deliverable
- Dependencies: Logical sequencing and parallel work opportunities

**Validate phase distribution** using `references/cost_estimation_standards.md` Section 2.1:

Calculate percentage of total effort for each phase:

| Phase | Expected Range | Red Flag If... |
|-------|---------------|---------------|
| Requirements | 10-15% | <5% or >20% |
| Design | 15-20% | <10% or >25% |
| Development | 40-50% | <30% or >60% |
| Testing | 15-25% | <10% or >30% |
| Deployment | 5-10% | <2% or >15% |
| PM/Overhead | 10-15% | <5% or >20% |

**Warning**: If testing is <15%, this is a critical risk (see `references/risk_factors.md` Section 5.1).

**Document findings**:
- Phase distribution table with actual vs. expected
- Missing phases
- Poorly defined tasks (too large or too vague)
- WBS risk score

### Step 4: Effort and Cost Analysis

Validate effort estimates and costs using multiple references:

#### 4a. Labor Rate Validation

Compare vendor rates against market standards (`references/cost_estimation_standards.md` Section 1.1):

For each role in the estimate:
1. Identify role and seniority level
2. Look up market rate range for the appropriate region
3. Calculate variance: (Vendor Rate - Market Average) / Market Average × 100%

**Acceptance thresholds**:
- Within ±20% of market range: Acceptable
- 20-40% variance: Requires justification
- >40% variance: High concern (see `references/cost_estimation_standards.md` Section 7 for red flags)

**Consider rate adjustment factors** (Section 1.3):
- Major city premium: 1.2-1.5×
- Remote discount: 0.8-0.9×
- Specialized technology: 1.1-1.3×
- Long-term engagement: 0.9-0.95×

#### 4b. Team Composition Validation

Check team seniority mix (`references/cost_estimation_standards.md` Section 2.3):

**Recommended ratios**:
- Senior: 20-30%
- Mid-level: 40-50%
- Junior: 20-30%

**Red flags** (see `references/risk_factors.md` Section 3.2):
- >60% junior resources (high quality risk)
- <10% senior resources (insufficient oversight)
- All senior resources (cost inefficient, unsustainable)

#### 4c. Project Size Benchmarking

Compare total cost against project type benchmarks (`references/cost_estimation_standards.md` Section 3.2):

Example for Web Application:
- Simple (5-10 pages, basic CRUD): $30K-$80K
- Medium (15-30 pages, auth, API): $80K-$300K
- Complex (30+ pages, integrations, real-time): $300K-$1M+

If variance is >50% from benchmark, investigate:
- Is complexity correctly assessed?
- Are there specialized requirements?
- Is there gold-plating?

**Document findings**:
- Rate comparison table (role, vendor rate, market range, variance)
- Team composition assessment
- Cost validation against benchmarks
- Cost risk score and specific concerns

### Step 5: Resource and Timeline Analysis

Evaluate resource allocation and schedule using `references/review_checklist.md` Sections 5 & 9:

**Resource analysis**:
- Are key roles named or TBD?
- Are resources allocated realistically (<100% per person)?
- Is there backup coverage for key resources?
- Is resource turnover risk addressed?

Check `references/risk_factors.md` Section 3 for:
- Unavailable resources (Risk 3.1)
- Multitasking issues (Risk 3.3)
- Offshore communication risks (Risk 3.4)

**Timeline analysis**:
- Does duration align with total effort and team size?
  - Formula: Duration ≈ Total Hours / (Team Size × Utilization × Work Hours per Month)
  - Utilization should be 70-80% (not 100%)
- Are milestones achievable?
- Is buffer time included (10-15% recommended)?
- Are dependencies managed?

Check `references/risk_factors.md` Section 6.2 for unrealistic timeline risks.

**Document findings**:
- Resource availability concerns
- Resource allocation issues
- Timeline reasonableness assessment
- Critical path and dependency risks

### Step 6: Quality Assurance Evaluation

Assess testing and QA approach using `references/review_checklist.md` Section 7:

**Testing strategy checklist**:
- [ ] Unit testing (by developers)
- [ ] Integration testing
- [ ] System testing
- [ ] User acceptance testing (UAT)
- [ ] Performance testing
- [ ] Security testing
- [ ] Regression testing

**Validate QA effort** (`references/cost_estimation_standards.md` Section 4.2):
- Basic: 15-20% of development effort
- Standard: 25-35% of development effort
- Comprehensive: 40-60% of development effort

**Critical warning** (`references/risk_factors.md` Section 5.1):
If total testing effort is <15% of project effort, this is a **high-risk** item. Production will likely have high defect rates.

**Document findings**:
- Testing coverage assessment
- QA effort adequacy
- Missing test types
- Quality risk score

### Step 7: Risk and Contingency Assessment

Evaluate risk management using `references/risk_factors.md`:

**Identify applicable risks** across all 10 categories:
1. Scope-related risks (Section 1)
2. Estimation methodology risks (Section 2)
3. Resource and team risks (Section 3)
4. Technical risks (Section 4)
5. Process and methodology risks (Section 5)
6. Project management risks (Section 6)
7. Contractual and commercial risks (Section 7)
8. Organizational and cultural risks (Section 8)
9. Domain-specific risks (Section 9)

For each identified risk, use the Risk Assessment Framework (Section 10):
- **Probability**: Low (10%), Medium (50%), High (80%)
- **Impact**: Low, Medium, High
- **Risk Score**: Probability × Impact

Prioritize top 5-10 risks for active management.

**Validate contingency** (`references/cost_estimation_standards.md` Section 4.4):
- Low risk project: 5-10% contingency
- Medium risk: 10-15%
- High risk: 15-25%
- Very high risk: 25-40%

**Critical check**: Is contingency buffer included and adequate? Missing contingency is a medium-risk item (`references/risk_factors.md` Section 2.1).

**Document findings**:
- Top 5-10 risks with probability, impact, mitigation
- Contingency adequacy assessment
- Overall risk profile (low/medium/high)

### Step 8: Contract Terms Review

Evaluate contract terms using `references/review_checklist.md` Section 8:

**Key contract elements**:
- **IP Ownership**: Ensure all deliverables and IP transfer to client
- **Payment Terms**:
  - Limit upfront to 10-20%
  - Tie payments to deliverable acceptance
  - Retain 10-15% until warranty ends
- **Warranties**: Minimum 3-6 month warranty period
- **Change Management**: Clear change request process with impact assessment
- **Acceptance Criteria**: Specific, measurable criteria for each deliverable
- **Liability**: Reasonable caps, mutual penalties

**Red flags** (`references/risk_factors.md` Section 7):
- Large upfront payment (>30%)
- Weak acceptance criteria
- Unclear IP ownership
- Inadequate warranty (<3 months)

**Document findings**:
- Contract terms assessment by category
- Unfavorable terms requiring negotiation
- Contract risk score

### Step 9: Synthesize Findings

Compile all findings from Steps 2-8:

**Create findings summary**:
- Critical issues (must fix before proceeding)
- Important concerns (should address)
- Minor items (nice to clarify)

**Quantify overall assessment**:
- Use scoring from `references/review_checklist.md` Section 12
- Calculate risk scores by category
- Determine overall risk level (low/medium/high)

**Output**: Comprehensive findings document (use `assets/report_template.md` as structure)

---

## Workflow 3: Vendor Clarification Preparation

Use this workflow to prepare specific questions and clarification requests for the vendor based on your analysis.

### Step 1: Prioritize Findings

Group findings by severity:

**Critical Issues** (blockers - must resolve before acceptance):
- Missing essential scope items
- Inadequate testing effort (<15%)
- Unrealistic timeline
- Unfair contract terms
- High-impact technical risks without mitigation

**Important Concerns** (should address):
- Phase distribution anomalies
- Resource availability questions
- Rate justifications needed
- Missing contingency
- Medium-impact risks

**Minor Items** (nice to clarify):
- Task definition improvements
- Documentation details
- Assumption validations

### Step 2: Frame Questions Constructively

For each finding, formulate specific, actionable questions:

**Poor question**: "Your testing seems low."

**Better question**: "We note that testing effort is 8% of the total project effort. Industry standards recommend 15-25% for quality assurance. Can you provide details on your testing approach and rationale for the allocated effort? Specifically:
- What test levels are included (unit, integration, system, UAT)?
- What is your expected test coverage percentage?
- How will performance and security testing be addressed?
- Is there additional testing effort embedded in development tasks?"

**Question template**:
1. Observation: "We note that [specific finding]"
2. Context: "Industry standards / best practices suggest [benchmark]"
3. Request: "Can you clarify [specific question]?"
4. Specifics: Bullet points for detailed information needed

### Step 3: Organize Clarification Request

Structure your clarification request document:

```markdown
# Clarification Request: [PROJECT NAME]
**Vendor**: [VENDOR]
**Date**: [DATE]

## Overview
Thank you for your detailed estimate. To ensure we have a complete understanding before proceeding, we'd like to clarify several items:

## 1. Critical Items (Response Required for Proceeding)

### 1.1 [Category - e.g., Testing Strategy]
[Detailed question following template above]

[Repeat for each critical item]

## 2. Important Clarifications

### 2.1 [Category]
[Question]

[Repeat]

## 3. Additional Information Requests

### 3.1 [Category]
[Question]

[Repeat]

## Next Steps
Please provide responses by [DATE]. We're happy to schedule a call to discuss any complex items.
```

### Step 4: Prepare for Negotiation

Identify negotiation opportunities using `references/cost_estimation_standards.md` Section 8:

**Cost reduction strategies**:
- Reduce scope (MVP approach): 20-40% savings, low risk
- Extend timeline: 10-15% savings, low risk
- Adjust team seniority mix: 15-25% savings, medium risk
- Fixed price instead of T&M: 10-20% savings, medium-high risk

**Value-add negotiations** (non-cost):
- Extended warranty period
- Additional knowledge transfer sessions
- Source code ownership clarification
- More frequent deliveries/demos
- Dedicated resources for critical roles
- Performance guarantees

Prepare 3-5 specific negotiation scenarios with expected outcomes.

**Output**: Clarification request document + negotiation strategy memo

---

## Workflow 4: Final Review and Recommendation

Use this workflow after receiving vendor responses to clarifications, or if proceeding without clarifications, to create the final recommendation.

### Step 1: Incorporate Vendor Responses

If vendor provided clarifications:
- Update findings based on responses
- Note which issues were resolved vs. still outstanding
- Identify any new concerns raised by responses
- Re-assess risk levels for addressed items

### Step 2: Apply Decision Framework

Use `references/review_checklist.md` Section 12 for structured decision-making:

**Go/No-Go Criteria Scoring**:

| Criterion | Weight | Score (1-10) | Weighted Score |
|-----------|--------|--------------|----------------|
| Scope completeness | HIGH | X | X |
| Cost reasonableness | HIGH | X | X |
| Vendor capability | HIGH | X | X |
| Risk profile | HIGH | X | X |
| Contract terms | MEDIUM | X | X |
| Timeline feasibility | MEDIUM | X | X |
| QA approach | MEDIUM | X | X |

**Scoring guidance**:
- 9-10: Excellent, exceeds expectations
- 7-8: Good, meets requirements
- 5-6: Acceptable with minor concerns
- 3-4: Below acceptable, significant concerns
- 1-2: Poor, major problems

**High weight**: ×3, **Medium weight**: ×2, **Low weight**: ×1

**Total Score Interpretation**:
- 80-100: Strong approval candidate
- 60-79: Acceptable with conditions
- 40-59: Requires significant revision
- <40: Reject or major rework needed

### Step 3: Formulate Recommendation

Based on total score and red flag count:

**ACCEPT** - Proceed with contract execution
- Conditions: Score >80, Red Flags ≤2, All critical issues resolved
- Rationale: Estimate is comprehensive, reasonable, and low-risk

**CONDITIONAL ACCEPT** - Proceed after addressing specific items
- Conditions: Score 60-80, Red Flags 3-5, Most critical issues resolved
- Rationale: Estimate is generally acceptable but requires specific improvements before final approval
- Specify: List exact conditions that must be met

**REQUEST REVISION** - Significant changes needed before acceptance
- Conditions: Score 40-60, Red Flags 6-9, Multiple critical issues remain
- Rationale: Estimate has significant gaps or concerns requiring substantial revision
- Specify: List required changes with rationale

**REJECT** - Do not proceed with this vendor
- Conditions: Score <40, Red Flags ≥10, Fundamental issues unresolved
- Rationale: Estimate demonstrates insufficient understanding, capability, or alignment
- Alternatives: Suggest alternatives (re-bid, different vendor, different approach)

### Step 4: Create Executive Summary

Generate concise executive summary (1-2 pages) for decision-makers:

**Summary template**:
```markdown
# Executive Summary: [PROJECT] Vendor Estimate Review

**Recommendation**: [ACCEPT/CONDITIONAL/REVISE/REJECT]
**Overall Risk**: [LOW/MEDIUM/HIGH]
**Confidence**: [HIGH/MEDIUM/LOW]

## Key Metrics
- Total Cost: $[X] ([+/-]% vs. budget)
- Duration: [X] months
- Team Size: [X] resources

## Assessment Highlights

✅ **Strengths**:
1. [Key strength]
2. [Key strength]
3. [Key strength]

⚠️ **Concerns**:
1. [Key concern]
2. [Key concern]
3. [Key concern]

🚨 **Critical Issues**:
1. [Critical issue] - [Impact]
2. [Critical issue] - [Impact]

## Recommendation Details
[Specific recommendation with conditions if applicable]

## Financial Impact
- Base estimate: $[X]
- Recommended contingency: $[X] ([%])
- Total recommended budget: $[X]
- Potential savings opportunities: $[X]

## Next Steps
1. [Action item with owner]
2. [Action item with owner]
3. [Action item with owner]

**Decision Required By**: [DATE]
```

### Step 5: Generate Comprehensive Report

Create full review report using `assets/report_template.md`:

Fill in all sections:
1. Executive Summary
2. Scope Review
3. WBS Analysis
4. Effort Estimation Analysis
5. Cost Analysis
6. Resource and Team Analysis
7. Schedule and Timeline Analysis
8. Quality Assurance Review
9. Risk Assessment
10. Contract Terms Review
11. Comparison Analysis (if multiple vendors)
12. Findings Summary
13. Recommendations
14. Decision Framework
15. Next Steps
16. Appendix

**Output**:
- Executive summary (2 pages)
- Comprehensive review report (15-25 pages Markdown file)

---

## Workflow 5: Decision Support and Follow-Up

Use this workflow to support stakeholder decision-making and track action items post-review.

### Step 1: Prepare for Stakeholder Presentation

Create presentation materials from your report:

**Slide deck structure** (if needed):
1. Executive Summary (1 slide)
2. Key Metrics Dashboard (1 slide)
3. Assessment Highlights - Strengths (1 slide)
4. Assessment Highlights - Concerns (1 slide)
5. Risk Matrix (1 slide)
6. Cost Breakdown (1 slide)
7. Recommendation (1 slide)
8. Next Steps (1 slide)

**Anticipate questions**:
- "Why is this estimate high/low compared to our budget?"
- "What are the top 3 risks?"
- "Can we negotiate the price down?"
- "What happens if we proceed despite the red flags?"
- "How does this compare to other vendors?" (if applicable)

Prepare data-driven answers referencing specific sections of your analysis.

### Step 2: Conduct Decision Meeting

Present your findings and recommendation:

**Meeting agenda**:
1. Context and scope (5 min)
2. Key findings (10 min)
3. Risk assessment (10 min)
4. Recommendation and rationale (10 min)
5. Q&A and discussion (15 min)
6. Decision (10 min)

**Facilitate decision**:
- Present recommendation clearly
- Provide supporting data
- Address concerns objectively
- Document decision and rationale
- Capture action items with owners and deadlines

### Step 3: Document Decision

Record decision outcome:

```markdown
# Decision Record: [PROJECT] Vendor Estimate

**Date**: [DATE]
**Decision Makers**: [Names and roles]
**Decision**: [APPROVED/APPROVED WITH CONDITIONS/REJECTED/DEFERRED]

## Rationale
[Why this decision was made, key factors considered]

## Conditions (if conditional approval)
1. [Condition with completion criteria]
2. [Condition with completion criteria]

## Action Items
| Item | Owner | Due Date | Status |
|------|-------|----------|--------|
| [Action] | [Name] | [Date] | Pending |

## Next Review
**Date**: [DATE]
**Purpose**: [e.g., Review vendor responses to clarifications]
```

### Step 4: Track Action Items

If proceeding with vendor:
- Track resolution of critical issues
- Monitor vendor responses to clarifications
- Verify conditions are met before contract signature
- Update risk register

If rejecting or revising:
- Communicate decision to vendor professionally
- Document lessons learned
- Plan alternative approach (re-bid, scope reduction, phased approach)

### Step 5: Post-Contract Monitoring Setup (if proceeding)

If estimate is accepted and contract signed:

**Set up monitoring framework**:
- Baseline metrics (cost, schedule, scope)
- KPIs for tracking (burn rate, milestone completion, budget variance)
- Reporting frequency (weekly, bi-weekly)
- Escalation thresholds (cost variance >10%, schedule slip >1 week)

**Reference back to estimate**:
- Use estimate as baseline for earned value management (EVM)
- Track actuals vs. estimates to validate future vendor estimates
- Document variances and root causes

**Output**: Decision record + action item tracker + monitoring framework (if proceeding)

---

## Resources

This skill includes three types of bundled resources to support comprehensive vendor estimate review:

### scripts/

**`analyze_estimate.py`**: Automated estimate analysis tool

**Purpose**: Parse estimate files (Excel, CSV, PDF) and generate preliminary analysis with metrics, warnings, and findings.

**Usage**:
```bash
# Basic usage
python scripts/analyze_estimate.py estimate.xlsx -o report.md

# Full options
python scripts/analyze_estimate.py estimate.xlsx \
  --output review_report.md \
  --vendor "Acme Corp" \
  --project "CRM System" \
  --budget 500000 \
  --template detailed \
  --rates-file custom_rates.json \
  --verbose
```

**What it does**:
- Parses estimate data from Excel/CSV/PDF
- Calculates total cost, hours, average rates
- Analyzes phase distribution against industry norms
- Identifies estimation quality issues (round numbers, large tasks)
- Flags obvious red flags automatically
- Generates Markdown report with findings and recommendations

**Dependencies**:
- Python 3.7+
- Optional: pandas, openpyxl (for Excel), PyPDF2 (for PDF)
- Install with: `pip install pandas openpyxl PyPDF2`

**Note**: The script provides a starting point. Always supplement with manual review using the full checklist.

### references/

Three comprehensive reference documents for detailed analysis:

#### 1. `review_checklist.md`

**Purpose**: Systematic 12-section checklist for comprehensive estimate review

**When to use**: During Workflow 2 (Detailed Analysis) to ensure complete coverage of all review dimensions

**Key sections**:
- Section 1: Project Scope Review (requirements, deliverables, missing items)
- Section 2: Work Breakdown Structure Analysis
- Section 3: Effort Estimation Review
- Section 4: Cost Analysis
- Section 5: Timeline and Schedule Review
- Section 6: Risk Assessment
- Section 7: Quality Assurance
- Section 8: Contract Terms Review
- Section 9: Vendor Capability Assessment
- Section 10: Red Flags to Watch For (14 critical warning signs)
- Section 11: Comparison and Benchmarking
- Section 12: Final Recommendation Criteria

**How to use**:
- Reference specific sections as needed during analysis
- Use Section 10 for quick red flag identification
- Use Section 12 for structured decision-making

**Size**: ~200 checklist items across 12 sections

#### 2. `cost_estimation_standards.md`

**Purpose**: Industry benchmarks and standards for validating costs and effort

**When to use**: During cost and effort analysis (Workflow 2, Steps 4-5)

**Key sections**:
- Section 1: Labor Rate Benchmarks (by role, region, seniority)
  - North America, Europe, Asia Pacific rates
  - Rate adjustment factors
- Section 2: Effort Estimation Standards
  - Phase distribution percentages
  - Team composition standards
  - Productivity metrics (LoC, function points, story points)
- Section 3: Project Size Benchmarks
  - By project size (micro to enterprise)
  - By project type (web app, mobile, e-commerce, ERP, API, data migration)
- Section 4: Overhead and Additional Costs
  - PM overhead, QA overhead, infrastructure, contingency
- Section 5: Cost Validation Formulas
- Section 6: ROI Thresholds
- Section 7: Red Flags in Cost Estimation
- Section 8: Negotiation Leverage Points

**How to use**:
- Look up market rates for role validation (Section 1.1)
- Compare phase distribution to standards (Section 2.1)
- Validate project size against benchmarks (Section 3)
- Check for cost red flags (Section 7)

**Size**: ~11 sections with extensive data tables

#### 3. `risk_factors.md`

**Purpose**: Comprehensive risk identification and mitigation guide

**When to use**: Throughout analysis, especially Workflow 2, Step 7 (Risk Assessment)

**Key sections**:
- Section 1: Scope-Related Risks (incomplete requirements, gold plating, ambiguity)
- Section 2: Estimation Methodology Risks (gut-feel, optimistic bias, anchor bias)
- Section 3: Resource and Team Risks (unavailable resources, junior heavy, multitasking)
- Section 4: Technical Risks (immature technology, integration complexity, performance, legacy)
- Section 5: Process and Methodology Risks (insufficient testing, wrong methodology, no change management)
- Section 6: Project Management Risks (inadequate PM, unrealistic timeline, dependencies)
- Section 7: Contractual and Commercial Risks (payment terms, acceptance criteria, IP, warranties)
- Section 8: Organizational and Cultural Risks (misaligned incentives, communication barriers, vendor instability)
- Section 9: Domain-Specific Risks (regulatory compliance, security)
- Section 10: Risk Scoring and Prioritization (framework and matrix)

**How to use**:
- Identify applicable risks across all categories (Sections 1-9)
- For each risk, note probability, impact, and mitigation strategies
- Use Section 10 framework to score and prioritize risks
- Focus on top 5-10 risks for active management

**Size**: ~60 risk factors with detailed descriptions and mitigations

### assets/

Two Markdown templates for generating review outputs:

#### 1. `report_template.md`

**Purpose**: Comprehensive review report template with all sections

**When to use**: Workflow 4, Step 5 (Generate Comprehensive Report)

**Structure**: 15 sections covering all review dimensions with tables, assessment criteria, and decision framework

**How to use**:
- Copy template and fill in each section based on your analysis
- Replace [PLACEHOLDERS] with actual data
- Use assessment indicators (🔴/🟡/🟢) for visual status
- Complete all sections for thorough documentation

#### 2. `checklist_template.md`

**Purpose**: Interactive checklist format for structured review process

**When to use**: Alternative format for systematic review, good for team collaboration

**Structure**: 10-section checklist with scoring, checkboxes, and approval workflow

**How to use**:
- Print or use digitally to check off items as you review
- Score each section (0-100%)
- Calculate overall score to determine recommendation
- Use for sign-off and approval process

---

## Best Practices

### 1. Adapt Depth to Project Value and Risk

Not every estimate requires comprehensive multi-day review:
- **Small projects (<$50K)**: Focus on red flags (Workflow 1) and spot-check key areas
- **Medium projects ($50K-$500K)**: Standard detailed analysis (Workflows 1-2)
- **Large projects (>$500K)**: Full comprehensive review (all workflows)

### 2. Be Objective but Constructive

- Focus on facts and data, not subjective opinions
- Compare to industry standards, not personal preferences
- Frame concerns as questions, not accusations
- Acknowledge vendor strengths, not just problems
- Provide specific, actionable feedback

### 3. Consider Total Cost of Ownership (TCO)

Don't optimize only for lowest cost:
- Lower cost may mean higher risk
- Cheaper resources may need more time
- Missing scope items will cost more later
- Consider post-launch support and maintenance

### 4. Document Everything

- Record all findings, assumptions, decisions
- Keep audit trail for future reference
- Document vendor responses to clarifications
- Save for lessons learned on future projects

### 5. Involve Subject Matter Experts

For complex projects, consult:
- Technical architects for architecture review
- Security specialists for security requirements
- QA managers for testing approach
- Legal for contract terms
- Finance for payment terms and budgeting

### 6. Build Vendor Relationships

Use reviews to strengthen partnerships:
- Share industry benchmarks transparently
- Explain rationale for concerns
- Collaborate on risk mitigation
- Build mutual understanding of quality standards

### 7. Track Actuals vs. Estimates

After project completion:
- Compare actual costs, effort, and duration to estimates
- Analyze variances and root causes
- Use data to improve future estimate reviews
- Build organizational knowledge base

---

## Limitations and Considerations

### What This Skill Does Well

- Systematic evaluation across 12 dimensions
- Identification of red flags and risks
- Comparison to industry benchmarks
- Structured documentation and reporting
- Decision support framework

### What This Skill Doesn't Cover

- **Technical architecture deep-dive**: Requires domain-specific expertise
- **Legal contract review**: Requires legal counsel for binding agreements
- **Vendor background checks**: Requires separate due diligence process
- **Market research**: Assumes you're evaluating a specific estimate, not finding vendors
- **Project execution monitoring**: This is pre-contract review only

### When to Get Additional Expertise

- **Complex/regulated industries**: Healthcare, finance, government
- **High-value projects**: >$1M projects should have expert review
- **New technology domains**: Blockchain, AI/ML, IoT may need specialists
- **International vendors**: Cross-border legal and tax implications
- **Critical systems**: Life-safety, financial, high-availability systems

---

## Terminology

- **Estimate**: Vendor's proposed cost, effort, and timeline for delivering a project
- **RFP/RFQ**: Request for Proposal/Quote - client's request for vendor estimates
- **SOW**: Statement of Work - detailed project scope and deliverables
- **T&M**: Time and Materials - pricing model based on actual hours worked
- **Fixed Price**: Pricing model with set cost regardless of actual effort
- **Contingency**: Buffer budget for unexpected issues (typically 10-20%)
- **Red Flag**: Warning sign indicating potential problem or risk
- **WBS**: Work Breakdown Structure - hierarchical decomposition of project into tasks
- **NFR**: Non-Functional Requirements - performance, security, scalability, etc.
- **UAT**: User Acceptance Testing - testing by end users to validate requirements
- **IP**: Intellectual Property - ownership of code, designs, deliverables
- **SLA**: Service Level Agreement - commitments for response times, availability
- **EVM**: Earned Value Management - technique for measuring project performance

---

## Quick Reference

### Common Review Patterns

**Pattern 1: Quick Initial Review → Full Analysis → Vendor Clarification → Final Decision**
Use for: New vendors, complex projects, high-value projects

**Pattern 2: Automated Analysis → Manual Supplement → Direct to Final Report**
Use for: Repeat vendors, straightforward projects, time constraints

**Pattern 3: Multi-Vendor Comparison → Shortlist → Deep Dive on Top 2 → Selection**
Use for: Competitive bidding, RFP responses

### Key Benchmarks to Remember

- Testing should be 15-25% of total effort
- Contingency should be 10-20% for typical projects
- PM overhead should be 10-15% of total effort
- Team should be <30% junior, >20% senior
- Upfront payment should be <20%
- Retention should be 10-15% until warranty ends

### Most Common Red Flags

1. Testing <10% of effort
2. No contingency buffer
3. All resources at 100% allocation
4. Vague task descriptions
5. Missing phases (especially testing)
6. Rates 30%+ below market
7. No assumptions documented
8. Large upfront payment (>30%)
9. >60% junior resources
10. No change management process

---

## Examples

### Example 1: Initial Review of E-commerce Platform Estimate

**Context**:
- Vendor: New vendor (no prior relationship)
- Project: E-commerce platform development
- Estimate: $450,000, 12 months
- Budget: $500,000

**Workflow Used**: Workflow 1 (Initial Review and Triage)

**Process**:
1. Ran automated analysis: `python scripts/analyze_estimate.py ecommerce_estimate.xlsx --vendor "ShopTech Solutions" --project "E-commerce Platform" --budget 500000`
2. Review automated report: Identified 4 red flags
3. Manual red flag check: Found 2 additional critical issues
4. Total 6 red flags found

**Red flags identified**:
- Testing only 8% of total effort (critical)
- No security testing mentioned (critical)
- Payment terms: 40% upfront (concern)
- No documented assumptions (concern)
- Integration effort seems low (concern)
- No performance testing (concern)

**Decision**: Proceed to detailed review (Workflow 2) given high red flag count. Before detailed review, request clarification on testing approach.

**Outcome**: Generated 2-page initial findings report. Recommended stakeholder approval before investing time in detailed review. Estimated 2 days for comprehensive review.

### Example 2: Detailed Cost Analysis for CRM Migration

**Context**:
- Vendor: Established partner
- Project: Legacy CRM migration to Salesforce
- Estimate: $320,000, 8 months
- Budget: $350,000

**Workflow Used**: Workflow 2 (Detailed Analysis), Step 4 (Cost Analysis)

**Process**:
1. Extracted all labor rates by role
2. Compared against `references/cost_estimation_standards.md` Section 1.1 (North America rates)
3. Calculated variances

**Findings**:

| Role | Level | Vendor Rate | Market Range | Variance | Status |
|------|-------|-------------|--------------|----------|--------|
| Salesforce Developer | Senior | $165/hr | $130-190 | +7% | ✅ |
| Salesforce Architect | Expert | $240/hr | $220-320 | -9% | ✅ |
| Business Analyst | Mid | $105/hr | $80-120 | +6% | ✅ |
| QA Engineer | Mid | $85/hr | $70-100 | +7% | ✅ |
| Project Manager | Senior | $155/hr | $140-200 | -3% | ✅ |

**Team composition**:
- Senior: 40% (2 of 5 team members)
- Mid: 40% (2 of 5)
- Expert: 20% (1 of 5)

**Assessment**: Rates are within market range. Team composition is strong with good senior presence. Cost is reasonable for Salesforce migration complexity.

**Outcome**: No cost concerns. Proceed with timeline and risk analysis.

### Example 3: Risk Assessment for Mobile App Development

**Context**:
- Vendor: Offshore development company
- Project: iOS & Android mobile app
- Estimate: $180,000, 6 months
- Budget: $200,000

**Workflow Used**: Workflow 2 (Detailed Analysis), Step 7 (Risk Assessment)

**Process**:
1. Reviewed `references/risk_factors.md` across all 10 categories
2. Identified 12 applicable risks
3. Scored each risk for probability and impact
4. Prioritized top 5 risks

**Top 5 Risks Identified**:

1. **Resource 3.4: Offshore Communication** (High Probability, Medium Impact)
   - Team in India, 12-hour time zone difference
   - Only 2 hours overlap per day
   - Mitigation: Require 4-hour daily overlap, daily standups, weekly video demos

2. **Technical 4.3: Performance Underestimated** (Medium Probability, High Impact)
   - No performance testing in estimate
   - No performance requirements defined
   - Mitigation: Add performance testing (5% of effort), define performance SLAs

3. **Quality 5.1: Insufficient Testing** (High Probability, High Impact)
   - Testing is 12% of effort (below 15% minimum)
   - No device testing matrix provided
   - Mitigation: Increase testing to 20%, require device compatibility matrix

4. **PM 6.2: Aggressive Timeline** (Medium Probability, Medium Impact)
   - Building for both iOS and Android simultaneously
   - No buffer in schedule
   - Mitigation: Add 15% schedule buffer, consider phased delivery (iOS first)

5. **Contract 7.4: Inadequate Warranty** (Low Probability, High Impact)
   - Only 1-month warranty
   - No post-launch support
   - Mitigation: Negotiate 3-month warranty + 3-month support period

**Risk Score**: Medium-High

**Contingency**: Recommend 20% (given offshore + new vendor + multiple high-impact risks)

**Outcome**: Generated risk mitigation plan with specific actions. Added $36K contingency to budget. Prepared vendor clarification questions focused on top 5 risks.

### Example 4: Multi-Vendor Comparison

**Context**:
- RFP for enterprise reporting dashboard
- Budget: $400,000
- Received 3 vendor estimates

**Workflow Used**: Workflow 2 + Workflow 4 (Comparison + Final Recommendation)

**Process**:
1. Ran detailed analysis on all 3 estimates
2. Normalized for scope differences
3. Compared across key dimensions
4. Applied decision framework

**Comparison Summary**:

| Dimension | Vendor A | Vendor B | Vendor C |
|-----------|----------|----------|----------|
| Total Cost | $385K | $420K | $325K |
| Duration | 10 months | 9 months | 8 months |
| Testing % | 22% ✅ | 18% ✅ | 9% 🚨 |
| Contingency | 15% ✅ | 10% ⚠️ | 0% 🚨 |
| Red Flags | 2 | 3 | 7 |
| Overall Score | 72/100 | 78/100 | 48/100 |
| Risk Level | Medium | Medium | High |

**Key Findings**:
- **Vendor A**: Good price, adequate testing, some resource concerns
- **Vendor B**: Premium price but most complete, best testing approach, strong team (RECOMMENDED)
- **Vendor C**: Low price but major quality concerns, inadequate testing, too good to be true

**Recommendation**: Vendor B despite 5% higher cost
- Rationale: Superior testing approach reduces risk of production issues
- Vendor C's low price indicates missing scope or low quality
- Vendor A is acceptable alternative if budget is constrained

**Outcome**: Selected Vendor B. Negotiated 3% cost reduction by extending timeline 2 weeks. Final cost: $408K.

---

## Version History

- **v1.0** (2025-01-07): Initial release
  - 5 comprehensive workflows
  - 3 reference documents (350+ pages equivalent)
  - Automated analysis script
  - 2 report templates
  - 10+ examples and best practices

---

## Support

For questions or issues with this skill:
1. Review the relevant workflow section
2. Consult the appropriate reference document
3. Check examples for similar scenarios
4. Refer to Best Practices section

**Remember**: This skill provides systematic guidance and benchmarks. Always apply professional judgment considering your specific context, industry, and organizational standards.
