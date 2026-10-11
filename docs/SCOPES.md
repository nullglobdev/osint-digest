# Article scopes and filters

Choose one option independently in each of seven scopes. **All** is the default for every scope and adds no restriction. An article must match **every active scope** (AND); synonyms within an option are **alternatives** (OR). All enabled sources are still checked.

| Scope | Purpose | Original CLI flag |
|---|---|---|
| Sector | Existing sector and combined Education mode keyword lists | `--sector-scope` |
| Threat actor | Actor type/style or a specified regional indicator | `--actor-scope` |
| Social engineering | Human-focused attack techniques | `--social-scope` |
| Access & exploitation | Initial access and exploitation techniques | `--access-scope` |
| Malware & impact | Malware categories and effects | `--malware-scope` |
| Other styles | Other tactics, conditions, and disclosure channels | `--other-scope` |
| Education combinations | Paired campus-related concepts | `--education-scope` |

- **Windows:** open the **Filters** tab (Ctrl+7), or **Article filters** on the Dashboard. Selection saves immediately and applies to the next task and the Results/Previews views. **View selected keywords** explains the chosen options; **Reset all filters** returns every scope to All.
- **Linux/server:** `sh scripts/server.sh filters`, or Settings option **14 Article filters**. Choose a scope, select an option, and choose **0 Done** to save. The setup wizard offers the same menu. The existing `scope` command remains an alias. One saved combination applies to every enabled webhook.
- **Original CLI:** provide the desired flags using option IDs below; omit a flag for All. Example: `py -3 bot.py --sector-scope education --actor-scope nation_state --social-scope phishing --per-source-limit 5 --max-age-hours 48 --dry-run`.

For example, Sector = Education mode, Threat actor = Nation-state / APT, Social engineering = Phishing, and everything else = All requires an education keyword AND a nation-state/APT alias AND phishing. Selecting Malware = Ransomware additionally requires ransomware; it does not broaden the query. To find either of several attack styles without requiring all of them, leave unrelated scopes at All.

The collector checks the feed title and extracted visible article body **before** AI summaries and IOC extraction. Nonmatches do not call AI, are not published, and do not consume the per-source article limit. The article must still be fetched to evaluate its text. Reports store matched keywords for each scope. These are deterministic keyword filters, not verified actor attribution or semantic relevance scores.

Education combinations require both concepts somewhere in the same article, in either order: university phishing matches an article mentioning university and phishing even when the words are separated. An OR offers equivalent alternatives, such as LMS + phishing OR Canvas + phishing. Other multiword aliases match as phrases. Explicit parenthetical qualifiers remain required: deepfake (voice or video) requires deepfake plus voice or video. Country/regional actor options are individually selectable.

Matching uses word boundaries, common plurals, and equivalent hyphens/spaces. Most matching ignores case; IT, OT, and IP require uppercase, and APT/RAT in the new actor/malware scopes require uppercase to avoid ordinary-word matches. Sector **Education mode** continues to match any of the previously supplied education keywords, including broad terms such as cloud, research, IP, China, and Iran without additional campus context.

Normal desktop and server collection retains the **48-hour** window, per-source limits, and previous-delivery history. Dev previews, AI tests, and manual resends use the selected **1-365 day** test timeframe (default 2 days) with these same scope filters. Increasing the timeframe only considers articles still available in feeds.

Changing filters during a task affects the next task. Normal runs remember excluded articles for the exact filter combination to avoid refetching them each cycle. Changing any selection reconsiders eligible unsent articles; Dev/test mode rechecks current feed entries. Delivered articles still stay skipped during normal runs. Cached server reports are checked against the new combination; older reports lacking full-text metadata are rechecked against the article body without generating another AI summary.

Changing filters never deletes Results or delivery history. Reset all filters to show every saved result again. New reports contain full-body match metadata for all scopes. Older reports are filtered in the reader using their available title/excerpt/summary and any existing sector metadata. Upgrading keeps your existing sector selection, credentials, limits, and history; the six new scopes start at All.

## Keyword catalog

### Financial Services (`financial`)

bank, banking, credit union, fintech, payment, payments, ACH, wire transfer, SWIFT, card, credit card, debit, ATM, fraud, money mule, ransomware (finance), core banking, brokerage, insurance, underwriting, claims, student loan, lender

### Healthcare & Public Health (`healthcare`)

hospital, healthcare, clinic, medical, EHR, EMR, patient data, PHI, HIPAA, ransomware (health), medical device, pharmaceutical, pharmacy, clinical, research hospital, university hospital, telehealth

### Energy (`energy`)

power, electric, utility, grid, oil, gas, pipeline, energy, SCADA, ICS, OT, nuclear, renewable, solar, wind, substation, blackout

### Information Technology (`it`)

IT, software, SaaS, cloud, Azure, AWS, Google Cloud, identity, SSO, Active Directory, zero-day, vulnerability, exploit, patch, supply chain, open source, GitHub, npm, PyPI

### Government Facilities / Public Sector (`government`)

government, federal, state, local, municipality, agency, public sector, critical infrastructure, election, voting, public safety

### Transportation Systems (`transportation`)

airport, airline, aviation, rail, railroad, port, maritime, shipping, logistics, transit, DOT, TSA, vehicle, automotive

### Communications (`communications`)

telecom, telecommunications, ISP, broadband, 5G, satellite, radio, broadcast, network provider

### Water and Wastewater (`water`)

water, wastewater, utility, treatment plant, SCADA, ICS, municipal water

### Food and Agriculture (`food`)

agriculture, farm, food, processing, supply chain, USDA, livestock, crop

### Chemical (`chemical`)

chemical, manufacturing, plant, hazardous, ICS, OT

### Critical Manufacturing (`manufacturing`)

manufacturing, factory, industrial, ICS, OT, supply chain, semiconductor, electronics

### Defense Industrial Base (`defense`)

defense, DoD, military, contractor, aerospace, weapons, classified, research (defense)

### Commercial Facilities (`commercial`)

retail, shopping, mall, hotel, hospitality, stadium, entertainment, casino

### Emergency Services (`emergency`)

police, fire, EMS, 911, public safety, first responder

### Nuclear (`nuclear`)

nuclear, reactor, power plant, NRC

### Dams (`dams`)

dam, hydroelectric, water control

### Education & Research (`education_research`)

university, college, higher education, campus, student, faculty, staff, K-12, school, district, education, academic, research, lab, laboratory, R1, community college, EdTech, LMS, learning management, Canvas, Blackboard, Moodle, student information system, SIS, financial aid, bursar, enrollment, registrar, alumni, research data, intellectual property, IP theft, nation-state (research), APT (university)

### EdTech & Shared Platforms (`education_platforms`)

LMS, Canvas, Blackboard, Instructure, student portal, SSO, identity provider, Okta, Azure AD, Google Workspace, Microsoft 365, email, phishing (campus), ransomware (education), data breach (student), student PII, SSN, grades, transcripts

### Healthcare (university-affiliated) (`education_health`)

university hospital, teaching hospital, academic medical center, student health, research hospital, medical school, PHI (campus)

### Financial (campus-related) (`education_finance`)

student loan, financial aid, bursar, tuition, payment processor, scholarship, university finance

### Government / Public (education overlap) (`education_public`)

public university, state system, education department, student aid, Department of Education, research funding, grant

### Technology / SaaS (common on campus) (`education_technology`)

cloud, SaaS, identity, SSO, Active Directory, email compromise, phishing, supply chain (education vendor), zero-day (LMS or common campus software)

### Research & Nation-State (`education_nation_state`)

research, intellectual property, IP, nation-state, APT, espionage, China, Iran, Russia (academic targeting), quantum, AI research, defense research (university)

### Education mode quick list

university, college, higher education, campus, student, faculty, K-12, school, education, academic, research, EdTech, LMS, Canvas, Blackboard, Instructure, student information system, financial aid, ransomware education, data breach student, phishing campus, nation-state research, university hospital, teaching hospital, student loan, public university, SSO, identity provider

## Additional scope options

Every list also includes **All**. In the rules below, **OR** separates alternatives and **+** requires both concepts.

### Threat actor

| Option | ID | Matching keywords / concepts |
|---|---|---|
| Ransomware group / RaaS | `ransomware` | ransomware group OR ransomware gang OR RaaS OR ransomware-as-a-service |
| Cybercriminal / financially motivated | `cybercriminal` | cybercriminal OR financially motivated |
| Nation-state / APT | `nation_state` | nation-state OR state-sponsored OR APT OR advanced persistent threat |
| Espionage | `espionage` | espionage OR cyber espionage |
| Hacktivist | `hacktivist` | hacktivist OR hacktivism |
| Insider threat | `insider` | insider threat OR malicious insider |
| Initial access broker | `broker` | initial access broker OR IAB |
| Ransomware affiliate | `affiliate` | ransomware + affiliate |
| Script kiddie | `script_kiddie` | script kiddie |
| Organized crime | `organized_crime` | organized crime OR cybercrime syndicate |
| Chinese APT | `chinese_apt` | Chinese APT |
| Iran-linked | `iran_linked` | Iran-linked |
| Russian-speaking | `russian_speaking` | Russian-speaking |
| North Korean | `north_korean` | North Korean |
| Double / triple extortion | `extortion` | double extortion OR triple extortion |
| Data extortion group | `data_extortion` | data extortion group |
| Leak site / data leak | `leak_site` | leak site OR data leak |

### Social engineering

| Option | ID | Matching keywords / concepts |
|---|---|---|
| Phishing | `phishing` | phishing |
| Spear phishing | `spear_phishing` | spear phishing OR spear-phishing |
| Whaling | `whaling` | whaling |
| Smishing / SMS phishing | `smishing` | smishing OR SMS phishing |
| Vishing / voice phishing | `vishing` | vishing OR voice phishing |
| Social engineering | `social_engineering` | social engineering |
| Pretexting | `pretexting` | pretexting |
| Business email compromise | `bec` | business email compromise OR BEC |
| Impersonation | `impersonation` | impersonation |
| Credential harvesting | `credential_harvesting` | credential harvesting |
| Fake login / credential phishing | `fake_login` | fake login OR credential phishing |
| AI phishing / voice or video deepfake | `ai_phishing` | AI-generated phishing OR deepfake (voice or video) |
| QR code phishing / quishing | `quishing` | QR code phishing OR quishing |

### Access & exploitation

| Option | ID | Matching keywords / concepts |
|---|---|---|
| Initial access | `initial_access` | initial access |
| Brute force | `brute_force` | brute force |
| Password spraying | `password_spraying` | password spraying |
| Credential stuffing | `credential_stuffing` | credential stuffing |
| MFA fatigue / bombing | `mfa_fatigue` | MFA fatigue OR MFA bombing |
| Zero-day / 0-day | `zero_day` | zero-day OR 0-day |
| Vulnerability exploitation | `vulnerability_exploitation` | vulnerability exploitation |
| Unpatched system | `unpatched_system` | unpatched system |
| Public-facing application | `public_facing` | public-facing application |
| Web shell | `web_shell` | web shell |
| Supply chain attack | `supply_chain` | supply chain attack |
| Third-party compromise | `third_party` | third-party compromise |
| Vendor compromise | `vendor` | vendor compromise |

### Malware & impact

| Option | ID | Matching keywords / concepts |
|---|---|---|
| Ransomware | `ransomware` | ransomware |
| Malware | `malware` | malware |
| Infostealer / information stealer | `infostealer` | infostealer OR information stealer |
| Remote access trojan / RAT | `rat` | remote access trojan OR RAT |
| Loader | `loader` | loader |
| Wiper | `wiper` | wiper |
| DDoS | `ddos` | DDoS OR distributed denial of service |
| Data exfiltration / theft | `exfiltration` | data exfiltration OR data theft |
| Encryption | `encryption` | encryption |
| Double extortion | `double_extortion` | double extortion |
| Data breach | `data_breach` | data breach |
| Leak / leaked data | `leak` | leak OR leaked data |

### Other styles

| Option | ID | Matching keywords / concepts |
|---|---|---|
| Lateral movement | `lateral_movement` | lateral movement |
| Privilege escalation | `privilege_escalation` | privilege escalation |
| Living off the land | `living_off_land` | living off the land |
| Command and control / C2 | `command_control` | command and control OR C2 |
| Persistence | `persistence` | persistence |
| Defense evasion | `defense_evasion` | defense evasion |
| Reconnaissance | `reconnaissance` | reconnaissance |
| Scanning | `scanning` | scanning OR vulnerability scanning |
| Misconfiguration | `misconfiguration` | misconfiguration |
| Exposed credentials | `exposed_credentials` | exposed credentials |
| Dark web / leak site posting | `dark_web` | dark web OR leak site posting |

### Education combinations

| Option | ID | Matching keywords / concepts |
|---|---|---|
| University phishing | `university_phishing` | university + phishing |
| Campus phishing | `campus_phishing` | campus + phishing |
| Student phishing | `student_phishing` | student + phishing |
| Financial aid phishing | `financial_aid_phishing` | financial aid + phishing |
| LMS / Canvas phishing | `lms_phishing` | LMS + phishing OR Canvas + phishing |
| Education / university ransomware | `education_ransomware` | education + ransomware OR university + ransomware |
| Student data breach | `student_breach` | student + data breach |
| Research / academic espionage | `research_espionage` | research + espionage OR academic + espionage |
| Nation-state university | `nation_state_university` | nation-state + university |
| EdTech supply chain | `edtech_supply_chain` | EdTech + supply chain |
| Campus credential compromise | `campus_credentials` | credential compromise + campus |
| University / help desk vishing | `university_vishing` | vishing + university OR help desk + vishing |

