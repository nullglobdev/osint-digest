"""Independent article filters: AND across scopes, OR across option aliases."""
import hashlib
import json
import re

from osint_digest.core import sectors


def aliases(label, *terms):
    return label, tuple((term,) for term in terms)


# Each alternative contains one or more terms that must occur in the article.
# Education combinations use co-occurrence rather than requiring adjacent words.
ACTORS = {
    'ransomware': aliases('Ransomware group / RaaS', 'ransomware group', 'ransomware gang', 'RaaS', 'ransomware-as-a-service'),
    'cybercriminal': aliases('Cybercriminal / financially motivated', 'cybercriminal', 'financially motivated'),
    'nation_state': aliases('Nation-state / APT', 'nation-state', 'state-sponsored', 'APT', 'advanced persistent threat'),
    'espionage': aliases('Espionage', 'espionage', 'cyber espionage'),
    'hacktivist': aliases('Hacktivist', 'hacktivist', 'hacktivism'),
    'insider': aliases('Insider threat', 'insider threat', 'malicious insider'),
    'broker': aliases('Initial access broker', 'initial access broker', 'IAB'),
    'affiliate': ('Ransomware affiliate', (('ransomware', 'affiliate'),)),
    'script_kiddie': aliases('Script kiddie', 'script kiddie'),
    'organized_crime': aliases('Organized crime', 'organized crime', 'cybercrime syndicate'),
    'chinese_apt': aliases('Chinese APT', 'Chinese APT'),
    'iran_linked': aliases('Iran-linked', 'Iran-linked'),
    'russian_speaking': aliases('Russian-speaking', 'Russian-speaking'),
    'north_korean': aliases('North Korean', 'North Korean'),
    'extortion': aliases('Double / triple extortion', 'double extortion', 'triple extortion'),
    'data_extortion': aliases('Data extortion group', 'data extortion group'),
    'leak_site': aliases('Leak site / data leak', 'leak site', 'data leak'),
}
SOCIAL = {
    'phishing': aliases('Phishing', 'phishing'),
    'spear_phishing': aliases('Spear phishing', 'spear phishing', 'spear-phishing'),
    'whaling': aliases('Whaling', 'whaling'),
    'smishing': aliases('Smishing / SMS phishing', 'smishing', 'SMS phishing'),
    'vishing': aliases('Vishing / voice phishing', 'vishing', 'voice phishing'),
    'social_engineering': aliases('Social engineering', 'social engineering'),
    'pretexting': aliases('Pretexting', 'pretexting'),
    'bec': aliases('Business email compromise', 'business email compromise', 'BEC'),
    'impersonation': aliases('Impersonation', 'impersonation'),
    'credential_harvesting': aliases('Credential harvesting', 'credential harvesting'),
    'fake_login': aliases('Fake login / credential phishing', 'fake login', 'credential phishing'),
    'ai_phishing': aliases('AI phishing / voice or video deepfake', 'AI-generated phishing', 'deepfake (voice or video)'),
    'quishing': aliases('QR code phishing / quishing', 'QR code phishing', 'quishing'),
}
ACCESS = {
    'initial_access': aliases('Initial access', 'initial access'),
    'brute_force': aliases('Brute force', 'brute force'),
    'password_spraying': aliases('Password spraying', 'password spraying'),
    'credential_stuffing': aliases('Credential stuffing', 'credential stuffing'),
    'mfa_fatigue': aliases('MFA fatigue / bombing', 'MFA fatigue', 'MFA bombing'),
    'zero_day': aliases('Zero-day / 0-day', 'zero-day', '0-day'),
    'vulnerability_exploitation': aliases('Vulnerability exploitation', 'vulnerability exploitation'),
    'unpatched_system': aliases('Unpatched system', 'unpatched system'),
    'public_facing': aliases('Public-facing application', 'public-facing application'),
    'web_shell': aliases('Web shell', 'web shell'),
    'supply_chain': aliases('Supply chain attack', 'supply chain attack'),
    'third_party': aliases('Third-party compromise', 'third-party compromise'),
    'vendor': aliases('Vendor compromise', 'vendor compromise'),
}
MALWARE = {
    'ransomware': aliases('Ransomware', 'ransomware'),
    'malware': aliases('Malware', 'malware'),
    'infostealer': aliases('Infostealer / information stealer', 'infostealer', 'information stealer'),
    'rat': aliases('Remote access trojan / RAT', 'remote access trojan', 'RAT'),
    'loader': aliases('Loader', 'loader'),
    'wiper': aliases('Wiper', 'wiper'),
    'ddos': aliases('DDoS', 'DDoS', 'distributed denial of service'),
    'exfiltration': aliases('Data exfiltration / theft', 'data exfiltration', 'data theft'),
    'encryption': aliases('Encryption', 'encryption'),
    'double_extortion': aliases('Double extortion', 'double extortion'),
    'data_breach': aliases('Data breach', 'data breach'),
    'leak': aliases('Leak / leaked data', 'leak', 'leaked data'),
}
OTHER = {
    'lateral_movement': aliases('Lateral movement', 'lateral movement'),
    'privilege_escalation': aliases('Privilege escalation', 'privilege escalation'),
    'living_off_land': aliases('Living off the land', 'living off the land'),
    'command_control': aliases('Command and control / C2', 'command and control', 'C2'),
    'persistence': aliases('Persistence', 'persistence'),
    'defense_evasion': aliases('Defense evasion', 'defense evasion'),
    'reconnaissance': aliases('Reconnaissance', 'reconnaissance'),
    'scanning': aliases('Scanning', 'scanning', 'vulnerability scanning'),
    'misconfiguration': aliases('Misconfiguration', 'misconfiguration'),
    'exposed_credentials': aliases('Exposed credentials', 'exposed credentials'),
    'dark_web': aliases('Dark web / leak site posting', 'dark web', 'leak site posting'),
}
EDUCATION = {
    'university_phishing': ('University phishing', (('university', 'phishing'),)),
    'campus_phishing': ('Campus phishing', (('campus', 'phishing'),)),
    'student_phishing': ('Student phishing', (('student', 'phishing'),)),
    'financial_aid_phishing': ('Financial aid phishing', (('financial aid', 'phishing'),)),
    'lms_phishing': ('LMS / Canvas phishing', (('LMS', 'phishing'), ('Canvas', 'phishing'))),
    'education_ransomware': ('Education / university ransomware', (('education', 'ransomware'), ('university', 'ransomware'))),
    'student_breach': ('Student data breach', (('student', 'data breach'),)),
    'research_espionage': ('Research / academic espionage', (('research', 'espionage'), ('academic', 'espionage'))),
    'nation_state_university': ('Nation-state university', (('nation-state', 'university'),)),
    'edtech_supply_chain': ('EdTech supply chain', (('EdTech', 'supply chain'),)),
    'campus_credentials': ('Campus credential compromise', (('credential compromise', 'campus'),)),
    'university_vishing': ('University / help desk vishing', (('vishing', 'university'), ('help desk', 'vishing'))),
}
CATALOGS = {'actor_scope': ACTORS, 'social_scope': SOCIAL, 'access_scope': ACCESS,
            'malware_scope': MALWARE, 'other_scope': OTHER, 'education_scope': EDUCATION}
LABELS = {'sector_scope': 'Sector', 'actor_scope': 'Threat actor',
          'social_scope': 'Social engineering', 'access_scope': 'Access & exploitation',
          'malware_scope': 'Malware & impact', 'other_scope': 'Other styles',
          'education_scope': 'Education combinations'}
CHOICES = {'sector_scope': sectors.SCOPES,
           **{key: {'': 'All', **{value: label for value, (label, _) in catalog.items()}}
              for key, catalog in CATALOGS.items()}}
DEFAULTS = dict.fromkeys(LABELS, '')
CATALOG_VERSION = hashlib.sha256(json.dumps(CATALOGS, sort_keys=True).encode()).hexdigest()[:16] + ':' + sectors.CATALOG_VERSION + ':1'


def selection(values):
    """Accept a settings mapping or argparse namespace; absent scopes mean All."""
    get = values.get if isinstance(values, dict) else lambda key, default: getattr(values, key, default)
    result = {key: get(key, '') for key in LABELS}
    for key, value in result.items():
        if not isinstance(value, str) or value not in CHOICES[key]:
            raise ValueError('Choose a listed option or All for ' + LABELS[key] + '.')
    return result


def describe(selected):
    return '; '.join(LABELS[key] + ': ' + CHOICES[key][value] for key, value in selected.items() if value) or 'All'


def signature(selected):
    return CATALOG_VERSION + ':' + json.dumps(selected, sort_keys=True) if any(selected.values()) else ''


def rule_matches(rule, text):
    # Avoid the animal "rat" and adjective "apt" when matching actor acronyms.
    return all(bool(re.search(sectors.term_pattern(term).pattern, text)) if term in ('APT', 'RAT')
               else sectors.keyword_matches(term, text) for term in rule)


def classify(text, sector_matches=None):
    text = sectors.normalize(text)
    result = {'sector_scope': sectors.classify(text) if sector_matches is None else sector_matches}
    for key, catalog in CATALOGS.items():
        result[key] = {option: [' + '.join(rule) for rule in rules if rule_matches(rule, text)]
                       for option, (_, rules) in catalog.items()}
        result[key] = {option: terms for option, terms in result[key].items() if terms}
    return result


def matches(classification, selected):
    return all(not value or bool(classification.get(key, {}).get(value)) for key, value in selected.items())


def has_full_metadata(report, selected):
    if report.get('filter_catalog') == CATALOG_VERSION and isinstance(report.get('filter_matches'), dict):
        return all(not value or isinstance(report['filter_matches'].get(key), dict) for key, value in selected.items())
    return (not any(selected.get(key) for key in CATALOGS)
            and report.get('sector_catalog') == sectors.CATALOG_VERSION
            and isinstance(report.get('sector_matches'), dict))


def report_matches(report, selected):
    selected = selection(selected)
    if not any(selected.values()):
        return True
    if has_full_metadata(report, selected):
        metadata = report.get('filter_matches')
        if report.get('filter_catalog') != CATALOG_VERSION or not isinstance(metadata, dict):
            metadata = {'sector_scope': report['sector_matches']}
        return matches(metadata, selected)
    # Reader fallback for pre-filter reports. Collector refetches the full page.
    pieces = [str(report.get(key, '')) for key in ('title', 'publisher_excerpt')]
    analysis = report.get('analysis')
    for claims in (analysis if isinstance(analysis, dict) else {}).values():
        if isinstance(claims, list):
            pieces.extend(str(claim.get('text', '')) for claim in claims if isinstance(claim, dict))
    metadata = classify('\n'.join(pieces))
    if report.get('sector_catalog') == sectors.CATALOG_VERSION and isinstance(report.get('sector_matches'), dict):
        metadata['sector_scope'] = report['sector_matches']
    return matches(metadata, selected)


def keywords(key, option):
    if not option:
        return 'All (no restriction)'
    if key == 'sector_scope':
        return ', '.join(sectors.KEYWORDS[option])
    return ' OR '.join(' + '.join(rule) for rule in CATALOGS[key][option][1])
