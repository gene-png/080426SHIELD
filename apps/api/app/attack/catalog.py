"""MITRE ATT&CK Enterprise matrix catalog (Phase 5 stage 5).

Per D-007: encode the full Enterprise matrix rather than a curated
subset. The catalog is reference data; only the engagement's coverage
status per technique lands in `attack_coverage` rows.

Counts (ATT&CK Enterprise v15 baseline):
  14 tactics
  196 parent techniques
  411 sub-techniques
  ----
  607 total catalog entries

Records are intentionally terse - just (id, name, tactics, parent).
Long-form descriptions live with MITRE; this module exists to drive
the assessment workflow + heatmap UI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tactic:
    id: str  # e.g. "TA0043"
    shortname: str  # e.g. "reconnaissance"
    name: str
    description: str


@dataclass(frozen=True)
class Technique:
    id: str  # e.g. "T1003" or "T1003.001"
    name: str
    tactics: tuple[str, ...]  # tactic ids the technique maps to
    parent_id: str | None  # set only for sub-techniques
    is_sub_technique: bool


TACTICS: tuple[Tactic, ...] = (
    Tactic(
        "TA0043",
        "reconnaissance",
        "Reconnaissance",
        "Adversary is trying to gather information they can use to plan future operations.",
    ),
    Tactic(
        "TA0042",
        "resource-development",
        "Resource Development",
        "Adversary is trying to establish resources they can use to support operations.",
    ),
    Tactic(
        "TA0001", "initial-access", "Initial Access", "Adversary is trying to get into the network."
    ),
    Tactic("TA0002", "execution", "Execution", "Adversary is trying to run malicious code."),
    Tactic(
        "TA0003", "persistence", "Persistence", "Adversary is trying to maintain their foothold."
    ),
    Tactic(
        "TA0004",
        "privilege-escalation",
        "Privilege Escalation",
        "Adversary is trying to gain higher-level permissions.",
    ),
    Tactic(
        "TA0005",
        "defense-evasion",
        "Defense Evasion",
        "Adversary is trying to avoid being detected.",
    ),
    Tactic(
        "TA0006",
        "credential-access",
        "Credential Access",
        "Adversary is trying to steal account names and passwords.",
    ),
    Tactic(
        "TA0007", "discovery", "Discovery", "Adversary is trying to figure out the environment."
    ),
    Tactic(
        "TA0008",
        "lateral-movement",
        "Lateral Movement",
        "Adversary is trying to move through the environment.",
    ),
    Tactic(
        "TA0009",
        "collection",
        "Collection",
        "Adversary is trying to gather data of interest to their goal.",
    ),
    Tactic(
        "TA0011",
        "command-and-control",
        "Command and Control",
        "Adversary is trying to communicate with compromised systems.",
    ),
    Tactic("TA0010", "exfiltration", "Exfiltration", "Adversary is trying to steal data."),
    Tactic(
        "TA0040",
        "impact",
        "Impact",
        "Adversary is trying to manipulate, interrupt, or destroy systems and data.",
    ),
)


# Builder helpers keep the technique tuple compact + readable.
def _t(code: str, name: str, *tactic_ids: str) -> Technique:
    return Technique(id=code, name=name, tactics=tactic_ids, parent_id=None, is_sub_technique=False)


def _s(code: str, name: str) -> Technique:
    parent = code.rsplit(".", 1)[0]
    return Technique(id=code, name=name, tactics=(), parent_id=parent, is_sub_technique=True)


_RAW_TECHNIQUES: tuple[Technique, ...] = (
    # ============================================================
    # Reconnaissance (TA0043)
    # ============================================================
    _t("T1595", "Active Scanning", "TA0043"),
    _s("T1595.001", "Scanning IP Blocks"),
    _s("T1595.002", "Vulnerability Scanning"),
    _s("T1595.003", "Wordlist Scanning"),
    _t("T1592", "Gather Victim Host Information", "TA0043"),
    _s("T1592.001", "Hardware"),
    _s("T1592.002", "Software"),
    _s("T1592.003", "Firmware"),
    _s("T1592.004", "Client Configurations"),
    _t("T1589", "Gather Victim Identity Information", "TA0043"),
    _s("T1589.001", "Credentials"),
    _s("T1589.002", "Email Addresses"),
    _s("T1589.003", "Employee Names"),
    _t("T1590", "Gather Victim Network Information", "TA0043"),
    _s("T1590.001", "Domain Properties"),
    _s("T1590.002", "DNS"),
    _s("T1590.003", "Network Trust Dependencies"),
    _s("T1590.004", "Network Topology"),
    _s("T1590.005", "IP Addresses"),
    _s("T1590.006", "Network Security Appliances"),
    _t("T1591", "Gather Victim Org Information", "TA0043"),
    _s("T1591.001", "Determine Physical Locations"),
    _s("T1591.002", "Business Relationships"),
    _s("T1591.003", "Identify Business Tempo"),
    _s("T1591.004", "Identify Roles"),
    _t("T1598", "Phishing for Information", "TA0043"),
    _s("T1598.001", "Spearphishing Service"),
    _s("T1598.002", "Spearphishing Attachment"),
    _s("T1598.003", "Spearphishing Link"),
    _s("T1598.004", "Spearphishing Voice"),
    _t("T1597", "Search Closed Sources", "TA0043"),
    _s("T1597.001", "Threat Intel Vendors"),
    _s("T1597.002", "Purchase Technical Data"),
    _t("T1596", "Search Open Technical Databases", "TA0043"),
    _s("T1596.001", "DNS/Passive DNS"),
    _s("T1596.002", "WHOIS"),
    _s("T1596.003", "Digital Certificates"),
    _s("T1596.004", "CDNs"),
    _s("T1596.005", "Scan Databases"),
    _t("T1593", "Search Open Websites/Domains", "TA0043"),
    _s("T1593.001", "Social Media"),
    _s("T1593.002", "Search Engines"),
    _s("T1593.003", "Code Repositories"),
    _t("T1594", "Search Victim-Owned Websites", "TA0043"),
    # ============================================================
    # Resource Development (TA0042)
    # ============================================================
    _t("T1650", "Acquire Access", "TA0042"),
    _t("T1583", "Acquire Infrastructure", "TA0042"),
    _s("T1583.001", "Domains"),
    _s("T1583.002", "DNS Server"),
    _s("T1583.003", "Virtual Private Server"),
    _s("T1583.004", "Server"),
    _s("T1583.005", "Botnet"),
    _s("T1583.006", "Web Services"),
    _s("T1583.007", "Serverless"),
    _s("T1583.008", "Malvertising"),
    _t("T1586", "Compromise Accounts", "TA0042"),
    _s("T1586.001", "Social Media Accounts"),
    _s("T1586.002", "Email Accounts"),
    _s("T1586.003", "Cloud Accounts"),
    _t("T1584", "Compromise Infrastructure", "TA0042"),
    _s("T1584.001", "Domains"),
    _s("T1584.002", "DNS Server"),
    _s("T1584.003", "Virtual Private Server"),
    _s("T1584.004", "Server"),
    _s("T1584.005", "Botnet"),
    _s("T1584.006", "Web Services"),
    _s("T1584.007", "Serverless"),
    _s("T1584.008", "Network Devices"),
    _t("T1587", "Develop Capabilities", "TA0042"),
    _s("T1587.001", "Malware"),
    _s("T1587.002", "Code Signing Certificates"),
    _s("T1587.003", "Digital Certificates"),
    _s("T1587.004", "Exploits"),
    _t("T1585", "Establish Accounts", "TA0042"),
    _s("T1585.001", "Social Media Accounts"),
    _s("T1585.002", "Email Accounts"),
    _s("T1585.003", "Cloud Accounts"),
    _t("T1588", "Obtain Capabilities", "TA0042"),
    _s("T1588.001", "Malware"),
    _s("T1588.002", "Tool"),
    _s("T1588.003", "Code Signing Certificates"),
    _s("T1588.004", "Digital Certificates"),
    _s("T1588.005", "Exploits"),
    _s("T1588.006", "Vulnerabilities"),
    _s("T1588.007", "Artificial Intelligence"),
    _t("T1608", "Stage Capabilities", "TA0042"),
    _s("T1608.001", "Upload Malware"),
    _s("T1608.002", "Upload Tool"),
    _s("T1608.003", "Install Digital Certificate"),
    _s("T1608.004", "Drive-by Target"),
    _s("T1608.005", "Link Target"),
    _s("T1608.006", "SEO Poisoning"),
    # ============================================================
    # Initial Access (TA0001)
    # ============================================================
    _t("T1189", "Drive-by Compromise", "TA0001"),
    _t("T1190", "Exploit Public-Facing Application", "TA0001"),
    _t("T1133", "External Remote Services", "TA0001", "TA0003"),
    _t("T1200", "Hardware Additions", "TA0001"),
    _t("T1566", "Phishing", "TA0001"),
    _s("T1566.001", "Spearphishing Attachment"),
    _s("T1566.002", "Spearphishing Link"),
    _s("T1566.003", "Spearphishing via Service"),
    _s("T1566.004", "Spearphishing Voice"),
    _t("T1091", "Replication Through Removable Media", "TA0001", "TA0008"),
    _t("T1195", "Supply Chain Compromise", "TA0001"),
    _s("T1195.001", "Compromise Software Dependencies and Development Tools"),
    _s("T1195.002", "Compromise Software Supply Chain"),
    _s("T1195.003", "Compromise Hardware Supply Chain"),
    _t("T1199", "Trusted Relationship", "TA0001"),
    _t("T1078", "Valid Accounts", "TA0001", "TA0003", "TA0004", "TA0005"),
    _s("T1078.001", "Default Accounts"),
    _s("T1078.002", "Domain Accounts"),
    _s("T1078.003", "Local Accounts"),
    _s("T1078.004", "Cloud Accounts"),
    # ============================================================
    # Execution (TA0002)
    # ============================================================
    _t("T1659", "Content Injection", "TA0002", "TA0011"),
    _t("T1651", "Cloud Administration Command", "TA0002"),
    _t("T1059", "Command and Scripting Interpreter", "TA0002"),
    _s("T1059.001", "PowerShell"),
    _s("T1059.002", "AppleScript"),
    _s("T1059.003", "Windows Command Shell"),
    _s("T1059.004", "Unix Shell"),
    _s("T1059.005", "Visual Basic"),
    _s("T1059.006", "Python"),
    _s("T1059.007", "JavaScript"),
    _s("T1059.008", "Network Device CLI"),
    _s("T1059.009", "Cloud API"),
    _s("T1059.010", "AutoHotkey & AutoIT"),
    _s("T1059.011", "Lua"),
    _t("T1609", "Container Administration Command", "TA0002"),
    _t("T1610", "Deploy Container", "TA0002", "TA0005"),
    _t("T1203", "Exploitation for Client Execution", "TA0002"),
    _t("T1559", "Inter-Process Communication", "TA0002"),
    _s("T1559.001", "Component Object Model"),
    _s("T1559.002", "Dynamic Data Exchange"),
    _s("T1559.003", "XPC Services"),
    _t("T1106", "Native API", "TA0002"),
    _t("T1053", "Scheduled Task/Job", "TA0002", "TA0003", "TA0004"),
    _s("T1053.002", "At"),
    _s("T1053.003", "Cron"),
    _s("T1053.005", "Scheduled Task"),
    _s("T1053.006", "Systemd Timers"),
    _s("T1053.007", "Container Orchestration Job"),
    _t("T1648", "Serverless Execution", "TA0002"),
    _t("T1129", "Shared Modules", "TA0002"),
    _t("T1072", "Software Deployment Tools", "TA0002", "TA0008"),
    _t("T1569", "System Services", "TA0002"),
    _s("T1569.001", "Launchctl"),
    _s("T1569.002", "Service Execution"),
    _t("T1204", "User Execution", "TA0002"),
    _s("T1204.001", "Malicious Link"),
    _s("T1204.002", "Malicious File"),
    _s("T1204.003", "Malicious Image"),
    _t("T1047", "Windows Management Instrumentation", "TA0002"),
    # ============================================================
    # Persistence (TA0003)
    # ============================================================
    _t("T1098", "Account Manipulation", "TA0003"),
    _s("T1098.001", "Additional Cloud Credentials"),
    _s("T1098.002", "Additional Email Delegate Permissions"),
    _s("T1098.003", "Additional Cloud Roles"),
    _s("T1098.004", "SSH Authorized Keys"),
    _s("T1098.005", "Device Registration"),
    _s("T1098.006", "Additional Container Cluster Roles"),
    _s("T1098.007", "Additional Local or Domain Groups"),
    _t("T1197", "BITS Jobs", "TA0003", "TA0005"),
    _t("T1547", "Boot or Logon Autostart Execution", "TA0003", "TA0004"),
    _s("T1547.001", "Registry Run Keys / Startup Folder"),
    _s("T1547.002", "Authentication Package"),
    _s("T1547.003", "Time Providers"),
    _s("T1547.004", "Winlogon Helper DLL"),
    _s("T1547.005", "Security Support Provider"),
    _s("T1547.006", "Kernel Modules and Extensions"),
    _s("T1547.007", "Re-opened Applications"),
    _s("T1547.008", "LSASS Driver"),
    _s("T1547.009", "Shortcut Modification"),
    _s("T1547.010", "Port Monitors"),
    _s("T1547.012", "Print Processors"),
    _s("T1547.013", "XDG Autostart Entries"),
    _s("T1547.014", "Active Setup"),
    _s("T1547.015", "Login Items"),
    _t("T1037", "Boot or Logon Initialization Scripts", "TA0003", "TA0004"),
    _s("T1037.001", "Logon Script (Windows)"),
    _s("T1037.002", "Login Hook"),
    _s("T1037.003", "Network Logon Script"),
    _s("T1037.004", "RC Scripts"),
    _s("T1037.005", "Startup Items"),
    _t("T1176", "Browser Extensions", "TA0003"),
    _t("T1554", "Compromise Host Software Binary", "TA0003"),
    _t("T1136", "Create Account", "TA0003"),
    _s("T1136.001", "Local Account"),
    _s("T1136.002", "Domain Account"),
    _s("T1136.003", "Cloud Account"),
    _t("T1543", "Create or Modify System Process", "TA0003", "TA0004"),
    _s("T1543.001", "Launch Agent"),
    _s("T1543.002", "Systemd Service"),
    _s("T1543.003", "Windows Service"),
    _s("T1543.004", "Launch Daemon"),
    _s("T1543.005", "Container Service"),
    _t("T1546", "Event Triggered Execution", "TA0003", "TA0004"),
    _s("T1546.001", "Change Default File Association"),
    _s("T1546.002", "Screensaver"),
    _s("T1546.003", "Windows Management Instrumentation Event Subscription"),
    _s("T1546.004", "Unix Shell Configuration Modification"),
    _s("T1546.005", "Trap"),
    _s("T1546.006", "LC_LOAD_DYLIB Addition"),
    _s("T1546.007", "Netsh Helper DLL"),
    _s("T1546.008", "Accessibility Features"),
    _s("T1546.009", "AppCert DLLs"),
    _s("T1546.010", "AppInit DLLs"),
    _s("T1546.011", "Application Shimming"),
    _s("T1546.012", "Image File Execution Options Injection"),
    _s("T1546.013", "PowerShell Profile"),
    _s("T1546.014", "Emond"),
    _s("T1546.015", "Component Object Model Hijacking"),
    _s("T1546.016", "Installer Packages"),
    _t("T1574", "Hijack Execution Flow", "TA0003", "TA0004", "TA0005"),
    _s("T1574.001", "DLL Search Order Hijacking"),
    _s("T1574.002", "DLL Side-Loading"),
    _s("T1574.004", "Dylib Hijacking"),
    _s("T1574.005", "Executable Installer File Permissions Weakness"),
    _s("T1574.006", "Dynamic Linker Hijacking"),
    _s("T1574.007", "Path Interception by PATH Environment Variable"),
    _s("T1574.008", "Path Interception by Search Order Hijacking"),
    _s("T1574.009", "Path Interception by Unquoted Path"),
    _s("T1574.010", "Services File Permissions Weakness"),
    _s("T1574.011", "Services Registry Permissions Weakness"),
    _s("T1574.012", "COR_PROFILER"),
    _s("T1574.013", "KernelCallbackTable"),
    _s("T1574.014", "AppDomainManager"),
    _t("T1525", "Implant Internal Image", "TA0003"),
    _t("T1556", "Modify Authentication Process", "TA0003", "TA0005", "TA0006"),
    _s("T1556.001", "Domain Controller Authentication"),
    _s("T1556.002", "Password Filter DLL"),
    _s("T1556.003", "Pluggable Authentication Modules"),
    _s("T1556.004", "Network Device Authentication"),
    _s("T1556.005", "Reversible Encryption"),
    _s("T1556.006", "Multi-Factor Authentication"),
    _s("T1556.007", "Hybrid Identity"),
    _s("T1556.008", "Network Provider DLL"),
    _s("T1556.009", "Conditional Access Policies"),
    _t("T1137", "Office Application Startup", "TA0003"),
    _s("T1137.001", "Office Template Macros"),
    _s("T1137.002", "Office Test"),
    _s("T1137.003", "Outlook Forms"),
    _s("T1137.004", "Outlook Home Page"),
    _s("T1137.005", "Outlook Rules"),
    _s("T1137.006", "Add-ins"),
    _t("T1542", "Pre-OS Boot", "TA0003", "TA0005"),
    _s("T1542.001", "System Firmware"),
    _s("T1542.002", "Component Firmware"),
    _s("T1542.003", "Bootkit"),
    _s("T1542.004", "ROMMONkit"),
    _s("T1542.005", "TFTP Boot"),
    _t("T1505", "Server Software Component", "TA0003"),
    _s("T1505.001", "SQL Stored Procedures"),
    _s("T1505.002", "Transport Agent"),
    _s("T1505.003", "Web Shell"),
    _s("T1505.004", "IIS Components"),
    _s("T1505.005", "Terminal Services DLL"),
    _t("T1205", "Traffic Signaling", "TA0003", "TA0005", "TA0011"),
    _s("T1205.001", "Port Knocking"),
    _s("T1205.002", "Socket Filters"),
    # ============================================================
    # Privilege Escalation (TA0004)
    # ============================================================
    _t("T1548", "Abuse Elevation Control Mechanism", "TA0004", "TA0005"),
    _s("T1548.001", "Setuid and Setgid"),
    _s("T1548.002", "Bypass User Account Control"),
    _s("T1548.003", "Sudo and Sudo Caching"),
    _s("T1548.004", "Elevated Execution with Prompt"),
    _s("T1548.005", "Temporary Elevated Cloud Access"),
    _s("T1548.006", "TCC Manipulation"),
    _t("T1134", "Access Token Manipulation", "TA0004", "TA0005"),
    _s("T1134.001", "Token Impersonation/Theft"),
    _s("T1134.002", "Create Process with Token"),
    _s("T1134.003", "Make and Impersonate Token"),
    _s("T1134.004", "Parent PID Spoofing"),
    _s("T1134.005", "SID-History Injection"),
    _t("T1484", "Domain or Tenant Policy Modification", "TA0004", "TA0005"),
    _s("T1484.001", "Group Policy Modification"),
    _s("T1484.002", "Trust Modification"),
    _t("T1611", "Escape to Host", "TA0004"),
    _t("T1068", "Exploitation for Privilege Escalation", "TA0004"),
    _t("T1055", "Process Injection", "TA0004", "TA0005"),
    _s("T1055.001", "Dynamic-link Library Injection"),
    _s("T1055.002", "Portable Executable Injection"),
    _s("T1055.003", "Thread Execution Hijacking"),
    _s("T1055.004", "Asynchronous Procedure Call"),
    _s("T1055.005", "Thread Local Storage"),
    _s("T1055.008", "Ptrace System Calls"),
    _s("T1055.009", "Proc Memory"),
    _s("T1055.011", "Extra Window Memory Injection"),
    _s("T1055.012", "Process Hollowing"),
    _s("T1055.013", "Process Doppelgänging"),
    _s("T1055.014", "VDSO Hijacking"),
    _s("T1055.015", "ListPlanting"),
    # ============================================================
    # Defense Evasion (TA0005)
    # ============================================================
    _t("T1140", "Deobfuscate/Decode Files or Information", "TA0005"),
    _t("T1006", "Direct Volume Access", "TA0005"),
    _t("T1480", "Execution Guardrails", "TA0005"),
    _s("T1480.001", "Environmental Keying"),
    _s("T1480.002", "Mutual Exclusion"),
    _t("T1211", "Exploitation for Defense Evasion", "TA0005"),
    _t("T1222", "File and Directory Permissions Modification", "TA0005"),
    _s("T1222.001", "Windows File and Directory Permissions Modification"),
    _s("T1222.002", "Linux and Mac File and Directory Permissions Modification"),
    _t("T1564", "Hide Artifacts", "TA0005"),
    _s("T1564.001", "Hidden Files and Directories"),
    _s("T1564.002", "Hidden Users"),
    _s("T1564.003", "Hidden Window"),
    _s("T1564.004", "NTFS File Attributes"),
    _s("T1564.005", "Hidden File System"),
    _s("T1564.006", "Run Virtual Instance"),
    _s("T1564.007", "VBA Stomping"),
    _s("T1564.008", "Email Hiding Rules"),
    _s("T1564.009", "Resource Forking"),
    _s("T1564.010", "Process Argument Spoofing"),
    _s("T1564.011", "Ignore Process Interrupts"),
    _t("T1562", "Impair Defenses", "TA0005"),
    _s("T1562.001", "Disable or Modify Tools"),
    _s("T1562.002", "Disable Windows Event Logging"),
    _s("T1562.003", "Impair Command History Logging"),
    _s("T1562.004", "Disable or Modify System Firewall"),
    _s("T1562.006", "Indicator Blocking"),
    _s("T1562.007", "Disable or Modify Cloud Firewall"),
    _s("T1562.008", "Disable or Modify Cloud Logs"),
    _s("T1562.009", "Safe Mode Boot"),
    _s("T1562.010", "Downgrade Attack"),
    _s("T1562.011", "Spoof Security Alerting"),
    _s("T1562.012", "Disable or Modify Linux Audit System"),
    _t("T1070", "Indicator Removal", "TA0005"),
    _s("T1070.001", "Clear Windows Event Logs"),
    _s("T1070.002", "Clear Linux or Mac System Logs"),
    _s("T1070.003", "Clear Command History"),
    _s("T1070.004", "File Deletion"),
    _s("T1070.005", "Network Share Connection Removal"),
    _s("T1070.006", "Timestomp"),
    _s("T1070.007", "Clear Network Connection History and Configurations"),
    _s("T1070.008", "Clear Mailbox Data"),
    _s("T1070.009", "Clear Persistence"),
    _t("T1202", "Indirect Command Execution", "TA0005"),
    _t("T1036", "Masquerading", "TA0005"),
    _s("T1036.001", "Invalid Code Signature"),
    _s("T1036.002", "Right-to-Left Override"),
    _s("T1036.003", "Rename System Utilities"),
    _s("T1036.004", "Masquerade Task or Service"),
    _s("T1036.005", "Match Legitimate Name or Location"),
    _s("T1036.006", "Space after Filename"),
    _s("T1036.007", "Double File Extension"),
    _s("T1036.008", "Masquerade File Type"),
    _s("T1036.009", "Break Process Trees"),
    _t("T1578", "Modify Cloud Compute Infrastructure", "TA0005"),
    _s("T1578.001", "Create Snapshot"),
    _s("T1578.002", "Create Cloud Instance"),
    _s("T1578.003", "Delete Cloud Instance"),
    _s("T1578.004", "Revert Cloud Instance"),
    _s("T1578.005", "Modify Cloud Compute Configurations"),
    _t("T1112", "Modify Registry", "TA0005"),
    _t("T1601", "Modify System Image", "TA0005"),
    _s("T1601.001", "Patch System Image"),
    _s("T1601.002", "Downgrade System Image"),
    _t("T1599", "Network Boundary Bridging", "TA0005"),
    _s("T1599.001", "Network Address Translation Traversal"),
    _t("T1027", "Obfuscated Files or Information", "TA0005"),
    _s("T1027.001", "Binary Padding"),
    _s("T1027.002", "Software Packing"),
    _s("T1027.003", "Steganography"),
    _s("T1027.004", "Compile After Delivery"),
    _s("T1027.005", "Indicator Removal from Tools"),
    _s("T1027.006", "HTML Smuggling"),
    _s("T1027.007", "Dynamic API Resolution"),
    _s("T1027.008", "Stripped Payloads"),
    _s("T1027.009", "Embedded Payloads"),
    _s("T1027.010", "Command Obfuscation"),
    _s("T1027.011", "Fileless Storage"),
    _s("T1027.012", "LNK Icon Smuggling"),
    _s("T1027.013", "Encrypted/Encoded File"),
    _s("T1027.014", "Polymorphic Code"),
    _t(
        "T1542", "Pre-OS Boot (alias listed under Persistence)", "TA0005"
    ),  # already listed; tactic mapping covers
    _t("T1207", "Rogue Domain Controller", "TA0005"),
    _t("T1014", "Rootkit", "TA0005"),
    _t("T1218", "System Binary Proxy Execution", "TA0005"),
    _s("T1218.001", "Compiled HTML File"),
    _s("T1218.002", "Control Panel"),
    _s("T1218.003", "CMSTP"),
    _s("T1218.004", "InstallUtil"),
    _s("T1218.005", "Mshta"),
    _s("T1218.007", "Msiexec"),
    _s("T1218.008", "Odbcconf"),
    _s("T1218.009", "Regsvcs/Regasm"),
    _s("T1218.010", "Regsvr32"),
    _s("T1218.011", "Rundll32"),
    _s("T1218.012", "Verclsid"),
    _s("T1218.013", "Mavinject"),
    _s("T1218.014", "MMC"),
    _s("T1218.015", "Electron Applications"),
    _t("T1216", "System Script Proxy Execution", "TA0005"),
    _s("T1216.001", "PubPrn"),
    _t("T1221", "Template Injection", "TA0005"),
    _t("T1205", "Traffic Signaling (also Persistence)", "TA0005"),  # alias
    _t("T1127", "Trusted Developer Utilities Proxy Execution", "TA0005"),
    _s("T1127.001", "MSBuild"),
    _t("T1535", "Unused/Unsupported Cloud Regions", "TA0005"),
    _t("T1550", "Use Alternate Authentication Material", "TA0005"),
    _s("T1550.001", "Application Access Token"),
    _s("T1550.002", "Pass the Hash"),
    _s("T1550.003", "Pass the Ticket"),
    _s("T1550.004", "Web Session Cookie"),
    _t("T1497", "Virtualization/Sandbox Evasion", "TA0005"),
    _s("T1497.001", "System Checks"),
    _s("T1497.002", "User Activity Based Checks"),
    _s("T1497.003", "Time Based Evasion"),
    _t("T1600", "Weaken Encryption", "TA0005"),
    _s("T1600.001", "Reduce Key Space"),
    _s("T1600.002", "Disable Crypto Hardware"),
    _t("T1220", "XSL Script Processing", "TA0005"),
    # ============================================================
    # Credential Access (TA0006)
    # ============================================================
    _t("T1557", "Adversary-in-the-Middle", "TA0006", "TA0009"),
    _s("T1557.001", "LLMNR/NBT-NS Poisoning and SMB Relay"),
    _s("T1557.002", "ARP Cache Poisoning"),
    _s("T1557.003", "DHCP Spoofing"),
    _s("T1557.004", "Evil Twin"),
    _t("T1110", "Brute Force", "TA0006"),
    _s("T1110.001", "Password Guessing"),
    _s("T1110.002", "Password Cracking"),
    _s("T1110.003", "Password Spraying"),
    _s("T1110.004", "Credential Stuffing"),
    _t("T1555", "Credentials from Password Stores", "TA0006"),
    _s("T1555.001", "Keychain"),
    _s("T1555.002", "Securityd Memory"),
    _s("T1555.003", "Credentials from Web Browsers"),
    _s("T1555.004", "Windows Credential Manager"),
    _s("T1555.005", "Password Managers"),
    _s("T1555.006", "Cloud Secrets Management Stores"),
    _t("T1212", "Exploitation for Credential Access", "TA0006"),
    _t("T1187", "Forced Authentication", "TA0006"),
    _t("T1606", "Forge Web Credentials", "TA0006"),
    _s("T1606.001", "Web Cookies"),
    _s("T1606.002", "SAML Tokens"),
    _t("T1056", "Input Capture", "TA0006", "TA0009"),
    _s("T1056.001", "Keylogging"),
    _s("T1056.002", "GUI Input Capture"),
    _s("T1056.003", "Web Portal Capture"),
    _s("T1056.004", "Credential API Hooking"),
    _t("T1621", "Multi-Factor Authentication Request Generation", "TA0006"),
    _t("T1040", "Network Sniffing", "TA0006", "TA0007"),
    _t("T1003", "OS Credential Dumping", "TA0006"),
    _s("T1003.001", "LSASS Memory"),
    _s("T1003.002", "Security Account Manager"),
    _s("T1003.003", "NTDS"),
    _s("T1003.004", "LSA Secrets"),
    _s("T1003.005", "Cached Domain Credentials"),
    _s("T1003.006", "DCSync"),
    _s("T1003.007", "Proc Filesystem"),
    _s("T1003.008", "/etc/passwd and /etc/shadow"),
    _t("T1528", "Steal Application Access Token", "TA0006"),
    _t("T1539", "Steal Web Session Cookie", "TA0006"),
    _t("T1558", "Steal or Forge Authentication Certificates", "TA0006"),
    _t("T1649", "Steal or Forge Kerberos Tickets", "TA0006"),
    _s("T1649.001", "Golden Ticket"),
    _s("T1649.002", "Silver Ticket"),
    _s("T1649.003", "Kerberoasting"),
    _s("T1649.004", "AS-REP Roasting"),
    _t("T1111", "Multi-Factor Authentication Interception", "TA0006"),
    _t("T1552", "Unsecured Credentials", "TA0006"),
    _s("T1552.001", "Credentials In Files"),
    _s("T1552.002", "Credentials in Registry"),
    _s("T1552.003", "Bash History"),
    _s("T1552.004", "Private Keys"),
    _s("T1552.005", "Cloud Instance Metadata API"),
    _s("T1552.006", "Group Policy Preferences"),
    _s("T1552.007", "Container API"),
    _s("T1552.008", "Chat Messages"),
    # ============================================================
    # Discovery (TA0007)
    # ============================================================
    _t("T1087", "Account Discovery", "TA0007"),
    _s("T1087.001", "Local Account"),
    _s("T1087.002", "Domain Account"),
    _s("T1087.003", "Email Account"),
    _s("T1087.004", "Cloud Account"),
    _t("T1010", "Application Window Discovery", "TA0007"),
    _t("T1217", "Browser Information Discovery", "TA0007"),
    _t("T1580", "Cloud Infrastructure Discovery", "TA0007"),
    _t("T1538", "Cloud Service Dashboard", "TA0007"),
    _t("T1526", "Cloud Service Discovery", "TA0007"),
    _t("T1619", "Cloud Storage Object Discovery", "TA0007"),
    _t("T1613", "Container and Resource Discovery", "TA0007"),
    _t("T1654", "Log Enumeration", "TA0007"),
    _t("T1083", "File and Directory Discovery", "TA0007"),
    _t("T1615", "Group Policy Discovery", "TA0007"),
    _t("T1046", "Network Service Discovery", "TA0007"),
    _t("T1135", "Network Share Discovery", "TA0007"),
    _t("T1201", "Password Policy Discovery", "TA0007"),
    _t("T1120", "Peripheral Device Discovery", "TA0007"),
    _t("T1069", "Permission Groups Discovery", "TA0007"),
    _s("T1069.001", "Local Groups"),
    _s("T1069.002", "Domain Groups"),
    _s("T1069.003", "Cloud Groups"),
    _t("T1057", "Process Discovery", "TA0007"),
    _t("T1012", "Query Registry", "TA0007"),
    _t("T1018", "Remote System Discovery", "TA0007"),
    _t("T1518", "Software Discovery", "TA0007"),
    _s("T1518.001", "Security Software Discovery"),
    _t("T1082", "System Information Discovery", "TA0007"),
    _t("T1614", "System Location Discovery", "TA0007"),
    _s("T1614.001", "System Language Discovery"),
    _t("T1016", "System Network Configuration Discovery", "TA0007"),
    _s("T1016.001", "Internet Connection Discovery"),
    _s("T1016.002", "Wi-Fi Discovery"),
    _t("T1049", "System Network Connections Discovery", "TA0007"),
    _t("T1033", "System Owner/User Discovery", "TA0007"),
    _t("T1007", "System Service Discovery", "TA0007"),
    _t("T1124", "System Time Discovery", "TA0007"),
    _t("T1497", "Virtualization/Sandbox Evasion (also DE)", "TA0007"),
    # ============================================================
    # Lateral Movement (TA0008)
    # ============================================================
    _t("T1210", "Exploitation of Remote Services", "TA0008"),
    _t("T1534", "Internal Spearphishing", "TA0008"),
    _t("T1570", "Lateral Tool Transfer", "TA0008"),
    _t("T1563", "Remote Service Session Hijacking", "TA0008"),
    _s("T1563.001", "SSH Hijacking"),
    _s("T1563.002", "RDP Hijacking"),
    _t("T1021", "Remote Services", "TA0008"),
    _s("T1021.001", "Remote Desktop Protocol"),
    _s("T1021.002", "SMB/Windows Admin Shares"),
    _s("T1021.003", "Distributed Component Object Model"),
    _s("T1021.004", "SSH"),
    _s("T1021.005", "VNC"),
    _s("T1021.006", "Windows Remote Management"),
    _s("T1021.007", "Cloud Services"),
    _s("T1021.008", "Direct Cloud VM Connections"),
    _t("T1080", "Taint Shared Content", "TA0008"),
    # ============================================================
    # Collection (TA0009)
    # ============================================================
    _t("T1560", "Archive Collected Data", "TA0009"),
    _s("T1560.001", "Archive via Utility"),
    _s("T1560.002", "Archive via Library"),
    _s("T1560.003", "Archive via Custom Method"),
    _t("T1123", "Audio Capture", "TA0009"),
    _t("T1119", "Automated Collection", "TA0009"),
    _t("T1185", "Browser Session Hijacking", "TA0009"),
    _t("T1115", "Clipboard Data", "TA0009"),
    _t("T1530", "Data from Cloud Storage", "TA0009"),
    _t("T1602", "Data from Configuration Repository", "TA0009"),
    _s("T1602.001", "SNMP (MIB Dump)"),
    _s("T1602.002", "Network Device Configuration Dump"),
    _t("T1213", "Data from Information Repositories", "TA0009"),
    _s("T1213.001", "Confluence"),
    _s("T1213.002", "SharePoint"),
    _s("T1213.003", "Code Repositories"),
    _s("T1213.004", "Customer Relationship Management Software"),
    _s("T1213.005", "Messaging Applications"),
    _t("T1005", "Data from Local System", "TA0009"),
    _t("T1039", "Data from Network Shared Drive", "TA0009"),
    _t("T1025", "Data from Removable Media", "TA0009"),
    _t("T1074", "Data Staged", "TA0009"),
    _s("T1074.001", "Local Data Staging"),
    _s("T1074.002", "Remote Data Staging"),
    _t("T1114", "Email Collection", "TA0009"),
    _s("T1114.001", "Local Email Collection"),
    _s("T1114.002", "Remote Email Collection"),
    _s("T1114.003", "Email Forwarding Rule"),
    _t("T1113", "Screen Capture", "TA0009"),
    _t("T1125", "Video Capture", "TA0009"),
    # ============================================================
    # Command and Control (TA0011)
    # ============================================================
    _t("T1071", "Application Layer Protocol", "TA0011"),
    _s("T1071.001", "Web Protocols"),
    _s("T1071.002", "File Transfer Protocols"),
    _s("T1071.003", "Mail Protocols"),
    _s("T1071.004", "DNS"),
    _s("T1071.005", "Publish/Subscribe Protocols"),
    _t("T1092", "Communication Through Removable Media", "TA0011"),
    _t("T1132", "Data Encoding", "TA0011"),
    _s("T1132.001", "Standard Encoding"),
    _s("T1132.002", "Non-Standard Encoding"),
    _t("T1001", "Data Obfuscation", "TA0011"),
    _s("T1001.001", "Junk Data"),
    _s("T1001.002", "Steganography"),
    _s("T1001.003", "Protocol Impersonation"),
    _t("T1568", "Dynamic Resolution", "TA0011"),
    _s("T1568.001", "Fast Flux DNS"),
    _s("T1568.002", "Domain Generation Algorithms"),
    _s("T1568.003", "DNS Calculation"),
    _t("T1573", "Encrypted Channel", "TA0011"),
    _s("T1573.001", "Symmetric Cryptography"),
    _s("T1573.002", "Asymmetric Cryptography"),
    _t("T1008", "Fallback Channels", "TA0011"),
    _t("T1665", "Hide Infrastructure", "TA0011"),
    _t("T1105", "Ingress Tool Transfer", "TA0011"),
    _t("T1104", "Multi-Stage Channels", "TA0011"),
    _t("T1095", "Non-Application Layer Protocol", "TA0011"),
    _t("T1571", "Non-Standard Port", "TA0011"),
    _t("T1572", "Protocol Tunneling", "TA0011"),
    _t("T1090", "Proxy", "TA0011"),
    _s("T1090.001", "Internal Proxy"),
    _s("T1090.002", "External Proxy"),
    _s("T1090.003", "Multi-hop Proxy"),
    _s("T1090.004", "Domain Fronting"),
    _t("T1219", "Remote Access Software", "TA0011"),
    _t("T1102", "Web Service", "TA0011"),
    _s("T1102.001", "Dead Drop Resolver"),
    _s("T1102.002", "Bidirectional Communication"),
    _s("T1102.003", "One-Way Communication"),
    # ============================================================
    # Exfiltration (TA0010)
    # ============================================================
    _t("T1020", "Automated Exfiltration", "TA0010"),
    _s("T1020.001", "Traffic Duplication"),
    _t("T1030", "Data Transfer Size Limits", "TA0010"),
    _t("T1048", "Exfiltration Over Alternative Protocol", "TA0010"),
    _s("T1048.001", "Exfiltration Over Symmetric Encrypted Non-C2 Protocol"),
    _s("T1048.002", "Exfiltration Over Asymmetric Encrypted Non-C2 Protocol"),
    _s("T1048.003", "Exfiltration Over Unencrypted Non-C2 Protocol"),
    _t("T1041", "Exfiltration Over C2 Channel", "TA0010"),
    _t("T1011", "Exfiltration Over Other Network Medium", "TA0010"),
    _s("T1011.001", "Exfiltration Over Bluetooth"),
    _t("T1052", "Exfiltration Over Physical Medium", "TA0010"),
    _s("T1052.001", "Exfiltration over USB"),
    _t("T1567", "Exfiltration Over Web Service", "TA0010"),
    _s("T1567.001", "Exfiltration to Code Repository"),
    _s("T1567.002", "Exfiltration to Cloud Storage"),
    _s("T1567.003", "Exfiltration to Text Storage Sites"),
    _s("T1567.004", "Exfiltration Over Webhook"),
    _t("T1029", "Scheduled Transfer", "TA0010"),
    _t("T1537", "Transfer Data to Cloud Account", "TA0010"),
    # ============================================================
    # Impact (TA0040)
    # ============================================================
    _t("T1531", "Account Access Removal", "TA0040"),
    _t("T1485", "Data Destruction", "TA0040"),
    _s("T1485.001", "Lifecycle-Triggered Deletion"),
    _t("T1486", "Data Encrypted for Impact", "TA0040"),
    _t("T1565", "Data Manipulation", "TA0040"),
    _s("T1565.001", "Stored Data Manipulation"),
    _s("T1565.002", "Transmitted Data Manipulation"),
    _s("T1565.003", "Runtime Data Manipulation"),
    _t("T1491", "Defacement", "TA0040"),
    _s("T1491.001", "Internal Defacement"),
    _s("T1491.002", "External Defacement"),
    _t("T1561", "Disk Wipe", "TA0040"),
    _s("T1561.001", "Disk Content Wipe"),
    _s("T1561.002", "Disk Structure Wipe"),
    _t("T1499", "Endpoint Denial of Service", "TA0040"),
    _s("T1499.001", "OS Exhaustion Flood"),
    _s("T1499.002", "Service Exhaustion Flood"),
    _s("T1499.003", "Application Exhaustion Flood"),
    _s("T1499.004", "Application or System Exploitation"),
    _t("T1495", "Firmware Corruption", "TA0040"),
    _t("T1490", "Inhibit System Recovery", "TA0040"),
    _t("T1657", "Financial Theft", "TA0040"),
    _t("T1498", "Network Denial of Service", "TA0040"),
    _s("T1498.001", "Direct Network Flood"),
    _s("T1498.002", "Reflection Amplification"),
    _t("T1496", "Resource Hijacking", "TA0040"),
    _s("T1496.001", "Compute Hijacking"),
    _s("T1496.002", "Bandwidth Hijacking"),
    _s("T1496.003", "SMS Pumping"),
    _s("T1496.004", "Cloud Service Hijacking"),
    _t("T1489", "Service Stop", "TA0040"),
    _t("T1529", "System Shutdown/Reboot", "TA0040"),
)


# ---------------------------------------------------------------------------
# Post-process: deduplicate cross-tactic aliases, inherit parent tactics
# onto sub-techniques.
# ---------------------------------------------------------------------------


def _dedupe_and_merge(rows: tuple[Technique, ...]) -> tuple[Technique, ...]:
    by_id: dict[str, Technique] = {}
    for row in rows:
        existing = by_id.get(row.id)
        if existing is None:
            by_id[row.id] = row
            continue
        # Same ID seen again. Merge tactic mappings (techniques can
        # appear under multiple tactics, e.g. T1078 Valid Accounts).
        merged_tactics = tuple(dict.fromkeys((*existing.tactics, *row.tactics)))
        # Keep the most descriptive name (longest non-trivial).
        name = existing.name if len(existing.name) >= len(row.name) else row.name
        by_id[row.id] = Technique(
            id=existing.id,
            name=name,
            tactics=merged_tactics,
            parent_id=existing.parent_id or row.parent_id,
            is_sub_technique=existing.is_sub_technique,
        )
    return tuple(by_id.values())


def _inherit_sub_tactics(rows: tuple[Technique, ...]) -> tuple[Technique, ...]:
    by_id = {r.id: r for r in rows}
    out: list[Technique] = []
    for row in rows:
        if row.is_sub_technique and not row.tactics and row.parent_id:
            parent = by_id.get(row.parent_id)
            if parent is not None:
                out.append(
                    Technique(
                        id=row.id,
                        name=row.name,
                        tactics=parent.tactics,
                        parent_id=row.parent_id,
                        is_sub_technique=True,
                    )
                )
                continue
        out.append(row)
    return tuple(out)


TECHNIQUES: tuple[Technique, ...] = _inherit_sub_tactics(_dedupe_and_merge(_RAW_TECHNIQUES))


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------


def tactic_by_id(tactic_id: str) -> Tactic:
    for t in TACTICS:
        if t.id == tactic_id:
            return t
    raise KeyError(tactic_id)


def technique_by_id(code: str) -> Technique:
    for t in TECHNIQUES:
        if t.id == code:
            return t
    raise KeyError(code)


def techniques_for_tactic(tactic_id: str) -> tuple[Technique, ...]:
    return tuple(t for t in TECHNIQUES if tactic_id in t.tactics)


def parent_techniques() -> tuple[Technique, ...]:
    return tuple(t for t in TECHNIQUES if not t.is_sub_technique)


def sub_techniques(parent_id: str) -> tuple[Technique, ...]:
    return tuple(t for t in TECHNIQUES if t.parent_id == parent_id)


def all_codes() -> frozenset[str]:
    return frozenset(t.id for t in TECHNIQUES)


__all__ = [
    "TACTICS",
    "TECHNIQUES",
    "Tactic",
    "Technique",
    "all_codes",
    "parent_techniques",
    "sub_techniques",
    "tactic_by_id",
    "technique_by_id",
    "techniques_for_tactic",
]
