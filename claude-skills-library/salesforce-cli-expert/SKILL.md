---
name: salesforce-cli-expert
description: This skill should be used when generating Salesforce CLI commands for tasks like authenticating to orgs, querying data with SOQL, retrieving metadata (profiles, permission sets, security settings), deploying configuration changes, or automating security audits. Use when the user describes what they want to accomplish with Salesforce and needs the specific CLI command syntax.
---

# Salesforce CLI Expert

## Overview

This skill enables Claude to act as a Salesforce CLI expert, translating user requirements into precise `sf` CLI commands. It covers authentication, SOQL queries, metadata retrieval/deployment, and automation patterns specifically for security configuration management and org auditing.

## When to Use This Skill

Invoke this skill when the user:
- Asks how to perform a Salesforce operation via CLI
- Needs to retrieve security configurations (profiles, permission sets, org settings, sharing rules)
- Wants to query user data, roles, or permission assignments
- Needs to deploy security updates or configuration changes
- Asks for automation patterns (JSON output, bulk operations, CI/CD integration)
- Requests examples of specific `sf` or legacy `sfdx` commands

**Example triggers:**
- "How do I get all user profiles using Salesforce CLI?"
- "Show me the command to retrieve SecuritySettings metadata"
- "I need to query users with their MFA status"
- "How do I deploy a permission set to production?"
- "What's the CLI command to authenticate headlessly for CI/CD?"

## Core CLI Operations

### 1. Authentication

**Interactive web login (development):**
```bash
sf org login web --alias <OrgAlias> --set-default
```

**Headless JWT authentication (CI/automation):**
```bash
sf org login jwt --username <user@example.com> \
  --jwt-key-file <path/to/server.key> \
  --client-id <OAuthClientId> \
  --alias <Alias> \
  --set-default
```

**Auth URL authentication (pre-stored credentials):**
```bash
sf org login sfdx-url --sfdx-url-file <authFile.json> \
  --alias <Alias> --set-default
```

**List authenticated orgs:**
```bash
sf org list
```

**Display default org details:**
```bash
sf org display
```

### 2. Querying Data (SOQL)

**Basic query with table output:**
```bash
sf data query --query "SELECT Id, Name, Profile.Name FROM User LIMIT 10"
```

**JSON output (recommended for automation):**
```bash
sf data query --query "SELECT Id, Username, Email FROM User" --json
```

**CSV output (for reports):**
```bash
sf data query --query "SELECT Id, Username, Profile.Name FROM User" --result-format csv
```

**Target specific org:**
```bash
sf data query --query "SELECT Name FROM Account" --target-org <OrgAlias>
```

**Bulk API for large datasets (>10,000 records):**
```bash
sf data query --query "SELECT Id, Name FROM Contact" --bulk
```

**Common security-related queries:**
```bash
# Users with their profiles and roles
sf data query --query "SELECT Id, Username, Email, Profile.Name, UserRole.Name, IsActive FROM User"

# Permission set assignments
sf data query --query "SELECT Assignee.Username, PermissionSet.Name FROM PermissionSetAssignment"

# Users without MFA enabled (if field exists)
sf data query --query "SELECT Username, Email FROM User WHERE MfaEnabled__c = false"

# System Administrator users
sf data query --query "SELECT Username, Email FROM User WHERE Profile.Name = 'System Administrator' AND IsActive = true"
```

### 3. Retrieving Metadata

**Generate manifest for all metadata in org:**
```bash
sf project generate manifest \
  --output-dir manifest \
  --name allMetadata \
  --from-org <OrgAlias>
```

**Retrieve specific metadata types:**
```bash
# Single type
sf project retrieve start --metadata Profile

# Multiple types
sf project retrieve start --metadata Profile,PermissionSet,Role

# Specific named components
sf project retrieve start --metadata Profile:Admin,PermissionSet:SecurityAuditor
```

**Retrieve security-related metadata:**
```bash
# Security settings and sharing rules
sf project retrieve start --metadata SecuritySettings,SharingRules

# All security configurations
sf project retrieve start --metadata SecuritySettings,SharingRules,Profile,PermissionSet,Role
```

**Retrieve using manifest file:**
```bash
sf project retrieve start --manifest manifest/package.xml
```

**Legacy Metadata API retrieve (ZIP output):**
```bash
sfdx force:mdapi:retrieve -r ./output-dir -u <alias> -k package.xml
```

### 4. Deploying Changes

**Deploy specific metadata types:**
```bash
sf project deploy start --metadata SecuritySettings,SharingRules
```

**Validation-only deployment (check without applying):**
```bash
sf project deploy start --metadata Profile:Admin --check-only
```

**Deploy with manifest:**
```bash
sf project deploy start --manifest manifest/package.xml
```

**Deploy with test level control:**
```bash
sf project deploy start --metadata PermissionSet:CustomPS \
  --test-level RunLocalTests
```

**Target specific org:**
```bash
sf project deploy start --metadata SecuritySettings \
  --target-org <OrgAlias>
```

### 5. Automation and Output Formatting

**Force JSON output for all commands (set environment variable):**
```bash
export SF_CONTENT_TYPE=JSON
# All subsequent commands will output JSON by default
```

**Disable log files (recommended for production scripts):**
```bash
export SF_DISABLE_LOG_FILE=true
```

**Parse JSON output with jq (shell scripting):**
```bash
sf data query --query "SELECT Name FROM Account" --json | jq '.result.records'
```

**Example automation script pattern:**
```bash
#!/bin/bash
export SF_CONTENT_TYPE=JSON
export SF_DISABLE_LOG_FILE=true

# Authenticate
sf org login jwt --username user@example.com \
  --jwt-key-file server.key \
  --client-id $CLIENT_ID \
  --alias prod-org

# Query users
sf data query --query "SELECT Username, Profile.Name FROM User WHERE IsActive = true" \
  --target-org prod-org \
  --result-format csv > users_report.csv

# Retrieve security settings
sf project retrieve start --metadata SecuritySettings --target-org prod-org
```

## Command Pattern Reference

### Common Flags Across Commands

- `--target-org <alias>` or `-o <alias>`: Target specific org
- `--json`: Output in JSON format
- `--help` or `-h`: Display command help
- `--result-format <format>`: Output format (csv, json, human)

### Migration: Old (sfdx) vs New (sf) Syntax

| Old (sfdx) | New (sf) |
|------------|----------|
| `sfdx force:org:list` | `sf org list` |
| `sfdx force:org:display` | `sf org display` |
| `sfdx force:data:soql:query -q "..."` | `sf data query --query "..."` |
| `sfdx force:source:retrieve -m Type` | `sf project retrieve start --metadata Type` |
| `sfdx force:source:deploy -m Type` | `sf project deploy start --metadata Type` |
| `sfdx force:project:create -n Name` | `sf project generate --name Name` |

Both syntaxes still work, but `sf` is the current standard.

## Best Practices

1. **Always specify target org in automation:** Use `--target-org <alias>` to avoid ambiguity
2. **Use JSON output for parsing:** Add `--json` or set `SF_CONTENT_TYPE=JSON`
3. **Retrieve complete profiles:** When retrieving Profile metadata, also retrieve related components or use a comprehensive manifest
4. **Validate before deploying:** Use `--check-only` flag to test deployments without applying changes
5. **Handle API limits:** Use `--bulk` flag for queries returning >10,000 records
6. **Secure credentials:** Never hardcode JWT keys or auth URLs; use environment variables or secure vaults
7. **Version control metadata:** Store retrieved metadata in Git for change tracking and rollback capability

## References

For comprehensive CLI usage patterns, command examples, and security configuration automation workflows, refer to:

**`references/Salesforce_CLI_Usage_Guide.md`** - Complete guide covering:
- Setup and authentication methods
- Project setup and source tracking
- Metadata retrieval patterns
- SOQL query examples
- Deployment workflows
- Advanced security configuration management
- Continuous monitoring patterns

To access detailed information, read the reference file:
```
Read references/Salesforce_CLI_Usage_Guide.md
```

This reference contains in-depth explanations of command behavior, output formats, and real-world automation scenarios for security auditing and configuration management.
