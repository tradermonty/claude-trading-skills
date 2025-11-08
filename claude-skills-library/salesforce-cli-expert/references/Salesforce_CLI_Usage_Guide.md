# Salesforce CLI: Usage Guide for Security Configuration Automation

## Introduction

Salesforce CLI is a command-line interface that simplifies development and build automation when working with Salesforce orgs[1]. Developers use it to create and manage orgs, synchronize source (metadata) to and from orgs, create and install packages, and more[2]. In our context, the Salesforce CLI will enable an AI agent (or a developer) to retrieve Salesforce configuration data – especially security-related settings and user information – and assist in generating documentation or even automating deployments of security updates. This guide covers the basic operations of Salesforce CLI and highlights advanced topics relevant to security configuration management.

Note: Salesforce CLI originally used sfdx commands (often in the form sfdx force:<...>). These have been replaced by updated sf commands in the latest CLI version (v2), though the old commands still work[3]. This guide will mention both styles where appropriate.

## Setup and Authentication

Before retrieving any data, you must install Salesforce CLI (via installer or npm) and authenticate it with your Salesforce org. Once Salesforce CLI is installed, verify the installation by running sf --version and list available commands with sf commands[4].

Authenticating to a Salesforce Org: Use an OAuth web login for interactive authentication. For example, to log in to an org and set an alias and default, run:

sf org login web --alias <YourOrgAlias> --set-default (for Dev Hub or default org)[5].

This command opens a browser to Salesforce’s login page and, upon success, saves your credentials locally under the given alias. After authentication, you can refer to the org by its alias or use it as the default for CLI commands. You can see all authenticated orgs with sf org list and display details of the default org with sf org display (or the older sfdx force:org:list and force:org:display commands).

Headless Authentication (CI/Automation): In non-interactive environments (like CI or an AI agent running on a server), you can authenticate using JWT or an auth URL file instead of the web login. For example, use a JWT flow with a connected app:

sf org login jwt --username <user@example.com> --jwt-key-file <path/to/server.key> --client-id <OAuthClientId> --alias <Alias> --set-default[6]

Or use a pre-generated SFDX auth URL:

sf org login sfdx-url --sfdx-url-file <authFile.json> --alias <Alias> --set-default[7].

These methods allow the CLI to authenticate without manual input (suitable for an AI agent script). Remember to keep keys and URLs secure.

## Basic CLI Operations

Once set up, Salesforce CLI provides a wide range of commands to interact with your org. Below we cover the most essential operations, especially those relevant to retrieving and managing org configuration and security data.

### Project Setup and Source Tracking

Salesforce CLI operations are often run within the context of a local project. You can create a new project (with a scaffold directory structure and configuration files) using:

sf project generate --name <ProjectName> --template standard (or sfdx force:project:create).

Projects enable source tracking for scratch orgs and organize retrieved metadata in folders. However, for retrieving configuration from non-scratch orgs (like sandboxes or production), you can also work with manifests or direct commands without an elaborate project setup.

If you want to retrieve all metadata from an org (for a comprehensive documentation or backup), the CLI can automatically generate a manifest. For example, the following command generates a package.xml (manifest) containing every metadata component in the org:

sf project generate manifest --output-dir manifest --name allMetadata --from-org <YourOrgAlias>[8].

This creates a file (e.g., manifest/allMetadata.xml) listing all components. You can then retrieve everything by using this manifest (discussed below). This is a powerful way to capture the entire state of an org’s configuration in one go.

### Retrieving Metadata (Configuration Data)

One of the most important CLI operations for our purposes is retrieving metadata from Salesforce. Metadata includes configurations like Profiles, Permission Sets, Security Settings, Sharing Rules, etc. Retrieving these as source files allows you (or an AI agent) to inspect and document the org’s settings.

Retrieve by Metadata Type: You can retrieve specific components by specifying their metadata type and name. For example, to retrieve all sharing rules and the org’s security settings, use:

sfdx force:source:retrieve -m SharingRules,SecuritySettings

This pulls the SharingRules and SecuritySettings metadata from the default org into your local project[9]. In the updated CLI syntax, the equivalent is:

sf project retrieve start --metadata SharingRules,SecuritySettings

Both commands will fetch the sharing model (OWD and sharing rules) and the org-wide security settings (such as password policies, session settings, network access settings, etc.) into your local files.

You can retrieve other metadata in a similar way by listing them in the -m/--metadata flag (separated by commas). For example, to retrieve a specific Profile and a Permission Set:

sf project retrieve start --metadata Profile:Admin,PermissionSet:MyPermissionSet

(Old syntax: sfdx force:source:retrieve -m Profile:Admin,PermissionSet:MyPermissionSet.) Keep in mind that when retrieving Profiles by name, they may only include permissions related to components you retrieved at the same time[10]. To get a full profile, it’s often necessary to retrieve all related components or use a manifest (package.xml) that includes everything.

Retrieve using a Manifest: If you have a package.xml manifest (for example, the allMetadata.xml generated earlier or a tailored manifest listing specific components), you can retrieve according to that manifest. Use:

sf project retrieve start --manifest manifest/your_package.xml

(Old syntax: sfdx force:source:retrieve -x manifest/your_package.xml.) This will pull all components specified in the XML. Using a manifest is useful when you want to script retrieval of a known set of metadata types (like all security-related types) or even the entire org config. It’s an effective way to ensure you capture everything needed for documentation or deployment.

Source vs Metadata API format: By default, project retrieve (or force:source:retrieve) gives you metadata in source format (organized by folders for each metadata type). Alternatively, you can use Metadata API commands to retrieve a ZIP file of metadata:

sfdx force:mdapi:retrieve -r ./output-dir -u <alias> -k package.xml

which would retrieve per the package.xml and save a ZIP in the output directory. This might be useful if you prefer working with the raw Metadata API files. In most cases, using the source commands in a project is more convenient for reading and editing configuration.

### Running SOQL Queries (Retrieving Data Records)

In addition to metadata, you may need to retrieve data from Salesforce, such as user records, role assignments, or other security-related records. Salesforce CLI allows running SOQL queries directly against your org:

The new syntax: sf data query --query "<SOQL query>"

The old syntax: sfdx force:data:soql:query -q "<SOQL query>"

For example, to get basic information about users and their profile, you could run:

sf data query --query "SELECT Id, Name, Profile.Name, UserRole.Name FROM User LIMIT 10"

By default this will display results in a human-readable table. You can specify output formats: add --json for JSON output or --result-format csv (-r csv) for CSV output. For instance:

Using JSON output: sfdx force:data:soql:query -q "SELECT Name FROM Account LIMIT 10" --json[11]

Using CSV output: sfdx force:data:soql:query -q "SELECT Name FROM Account LIMIT 10" -r=csv[12]

The Salesforce CLI grants you the ability to run SOQL queries against your org’s data via the REST API, and you can retrieve results in a script-friendly format. “You can add a --json flag to retrieve your data in JSON for programmatic use.”[13] In fact, any CLI command can output JSON by adding --json, which is extremely useful for an AI agent. When you use --json, the CLI prints detailed results in JSON (including status information and the returned records), which your program or agent can then parse. For example, running a data query with --json will produce an object containing the queried records under a result field[13]. This can be piped to tools like jq for filtering if used in shell scripts, or parsed directly by the agent code[14].

Bulk and Complex Queries: The CLI also supports querying large data sets. If a SOQL query might return more than 10,000 records, you can add the --bulk flag to use Bulk API automatically[15]. This will handle large results asynchronously. For most security documentation needs (e.g., listing users, profiles, etc.), the regular query is sufficient. But it's good to know the CLI can handle scale with bulk operations if needed.

### Deploying Changes and Metadata Updates

Salesforce CLI not only retrieves metadata; it can also deploy changes back to an org. This is useful if the AI agent or developer needs to automate security updates (for example, updating a setting or deploying a revised Profile or Permission Set after review).

Deploying metadata: To deploy local metadata files to an org, use:

sf project deploy start --metadata <components> (or sfdx force:source:deploy -m ...) for deploying specific components by name. For example, after editing security settings or sharing rules in the local files, you can deploy them:

sf project deploy start --metadata SharingRules,SecuritySettings

This would push the updated sharing model and security settings to the target org[16]. The CLI will output the result of the deployment (success or errors). In a production deployment, by default all tests might run if deploying certain types of components; you can control this with flags like --test-level (e.g., RunLocalTests, RunSpecifiedTests) if needed. You can also do a validation only (check) deployment by adding --check-only (or -c in sfdx). This is prudent if you want to verify changes before applying them.

Using Source Control and CI: In a broader development process, you'd normally have your metadata in source control. The CLI integrates well with CI pipelines – you can authenticate via JWT, run sf project retrieve to fetch changes from an org, commit to Git, and use sf project deploy to deploy to another org. This aligns with an automated agent’s role in capturing org state and applying updates.

### Automation and CLI Output Formatting

When building an AI agent or any automation around Salesforce CLI, formatting output for easy consumption is key. As mentioned, most commands accept the --json flag to return structured JSON output instead of human-readable text. You can even make JSON the default output format for all commands by setting an environment variable: setting SF_CONTENT_TYPE=JSON forces all Salesforce CLI commands to output results in JSON form by default[17][18]. This can simplify parsing, as you don't need to remember to add --json every time.

Additionally, some data commands allow direct CSV output (-r csv as shown above), which can be handy for quickly generating reports. However, for an AI agent that will post-process the information, JSON is typically easier to handle programmatically.

Finally, the CLI commands return exit codes that indicate success or failure, which your automation can check. In JSON output, a "status": 0 usually indicates success. Error messages (and stack traces if any) are included in the JSON output as well, which an agent could analyze for troubleshooting.

## Advanced Topics for Security Configuration Management

The following are advanced Salesforce CLI usages tailored to retrieving and managing security-related configurations, aligning with our goal of automating security documentation and updates:

Org Security Settings: The org’s global security settings (password policies, session settings, network access IP ranges, etc.) can be retrieved via the SecuritySettings metadata type. Use a retrieve command as shown earlier to pull this metadata[9]. The resulting Security.settings XML file will contain settings like password expiration days, login lockout policies, session timeout, etc., which are critical for security audits.

Sharing Settings (OWD and Sharing Rules): Organization-Wide Defaults (OWD) and sharing rules determine baseline record access. These are retrievable via SharingRules metadata. As demonstrated, you can retrieve all sharing rules (which implicitly includes OWD settings) with --metadata SharingRules. After retrieval, you might see files like objectName.sharingRules and an OrgWideDefaults.settings (depending on API version) or included within SecuritySettings. Changes to OWD or sharing rules can likewise be deployed by specifying those components in a deploy command[9]. Always test deployments of sharing settings carefully, as they affect data visibility.

Profiles and Permission Sets: To document user permissions, you should retrieve Profile and PermissionSet metadata. Profiles include user permissions, field-level security, and other settings. Note that when retrieving profiles, the Metadata API returns only the parts of the profile related to other retrieved components[10]. A strategy to get complete profiles is to either retrieve “*” (all metadata) via a generated manifest or to retrieve profiles along with all relevant metadata. Permission sets (and Permission Set Groups) can be retrieved similarly. These XML files can then be parsed to list out assigned permissions, password policies (for profiles), etc., providing a detailed view of security configuration at the user level.

User Data and Roles: Metadata doesn’t include actual user records or role hierarchy assignments, but you can fetch those with SOQL queries. For example, use queries like SELECT Username, Email, Profile.Name, UserRole.Name FROM User to get a list of users and their roles/profiles. Similarly, you can query PermissionSetAssignment to see which users have which permission sets. Running such queries via CLI (sf data query ...) and outputting to JSON/CSV allows you to compile human-friendly tables for documentation. An AI agent can run these queries and then format the results into a report section (e.g., "List of admin users", "Users with MFA disabled", etc. – any condition you can filter via SOQL).

Automating Security Updates: If the agent identifies that a security setting must be updated (for instance, enabling a new Session Setting), you can automate the change by editing the retrieved metadata file and deploying it back. For example, if Security.settings has <enableRequireHttps>false</enableRequireHttps> and you need it true, the agent could modify that line and use sf project deploy start --metadata SecuritySettings to apply it. Similarly, adding a new IP range to the NetworkAccess (part of SecuritySettings) or changing a Profile permission can be done by modifying XML and deploying. The CLI will handle the deployment and report success or errors. This approach can be integrated into a pipeline where after deployment, verification queries or retrieves are run to confirm the changes.

Continuous Monitoring: An advanced use-case is to script the CLI to regularly export security settings (e.g., nightly retrieval of SecuritySettings, Profiles, etc.) and compare them against a baseline or commit to version control. This way, any unexpected change in security configuration can be detected. While not a built-in feature of CLI, it’s straightforward to implement with CLI commands and a source control system. An AI agent could leverage this to alert on changes or automatically document differences.

## Conclusion

Salesforce CLI is a powerful tool for extracting and managing Salesforce org configurations, and it is well-suited for automation use cases. We covered how to authenticate and set up the CLI, retrieve metadata (especially security-related configurations like org settings, sharing rules, profiles), run SOQL queries to get user and access data, and deploy changes back to the org. The CLI’s flexibility – including outputting JSON for scripting[13][14] – makes it possible for an AI agent or CI job to interact with Salesforce in an automated way, serving tasks such as generating security design documents or applying security updates.

By mastering these CLI operations, an AI agent can be programmed to fetch comprehensive security settings, user access details, and other org configurations and translate them into documentation or actionable change deployments. The key is using the CLI’s capabilities (with proper flags and perhaps environment settings like SF_CONTENT_TYPE=JSON for convenience[17]) to ensure the agent can reliably pull the data it needs and interpret the results. With these tools and techniques, you can automate the auditing and enforcement of Salesforce security policies as part of your project’s workflow, improving accuracy and efficiency in maintaining secure org configurations.

Sources: The information above was compiled from Salesforce’s official documentation and developer blogs, including the Salesforce CLI Setup Guide[1][2], Salesforce CLI Command Reference, and relevant articles that illustrate Salesforce CLI usage for security settings deployment[9] and data queries[11]. These resources provide detailed command syntax and examples that were referenced throughout the guide.


[1] [4] [17] [18] Salesforce CLI Setup Guide

https://resources.docs.salesforce.com/latest/latest/en-us/sfdc/pdf/sfdx_setup.pdf

[2] Quick Start | Salesforce CLI Setup Guide

https://developer.salesforce.com/docs/atlas.en-us.sfdx_setup.meta/sfdx_setup/sfdx_setup_intro.htm

[3] The Complete Guide to Retrieving Salesforce Metadata

https://www.salto.io/blog-posts/the-complete-guide-to-retrieving-salesforce-metadata

[5] [6] [7] Salesforce CLI Command Reference

https://resources.docs.salesforce.com/latest/latest/en-us/sfdc/pdf/sfdx_cli_reference.pdf

[8] How to retrieve your entire Salesforce metadata with 2 commands

https://www.pablogonzalez.io/how-to-retrieve-your-entire-salesforce-metadata-with-2-commands/

[9] [16] How to Deploy OWD Changes in Salesforce | by UATeam | Medium

https://medium.com/@aleksej.gudkov/how-to-deploy-owd-changes-in-salesforce-35fb8223fe4f

[10] SFDX: where can set Field-level security and accessibility?

https://salesforce.stackexchange.com/questions/263343/sfdx-where-can-set-field-level-security-and-accessibility

[11] [12] Run SOQL with SFDX and Export Results to File · crmcog

https://crmcog.com/sfdx-soql-export-file/

[13] [14] [15] Manipulate Data with the Salesforce CLI | Salesforce Developers Blog

https://developer.salesforce.com/blogs/2024/02/manipulate-data-with-the-salesforce-cli

