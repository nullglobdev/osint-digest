"""User-supplied sector keywords. Matching is deterministic, before AI analysis."""
from functools import lru_cache
import hashlib
import json
import re
import unicodedata


# Parentheses express context: match the base term AND its qualifier. The
# catalog preserves the user's wording so operators can review every rule.
SECTORS = {
    'financial': ('Financial Services', 'bank, banking, credit union, fintech, payment, payments, ACH, wire transfer, SWIFT, card, credit card, debit, ATM, fraud, money mule, ransomware (finance), core banking, brokerage, insurance, underwriting, claims, student loan, lender'),
    'healthcare': ('Healthcare & Public Health', 'hospital, healthcare, clinic, medical, EHR, EMR, patient data, PHI, HIPAA, ransomware (health), medical device, pharmaceutical, pharmacy, clinical, research hospital, university hospital, telehealth'),
    'energy': ('Energy', 'power, electric, utility, grid, oil, gas, pipeline, energy, SCADA, ICS, OT, nuclear, renewable, solar, wind, substation, blackout'),
    'it': ('Information Technology', 'IT, software, SaaS, cloud, Azure, AWS, Google Cloud, identity, SSO, Active Directory, zero-day, vulnerability, exploit, patch, supply chain, open source, GitHub, npm, PyPI'),
    'government': ('Government Facilities / Public Sector', 'government, federal, state, local, municipality, agency, public sector, critical infrastructure, election, voting, public safety'),
    'transportation': ('Transportation Systems', 'airport, airline, aviation, rail, railroad, port, maritime, shipping, logistics, transit, DOT, TSA, vehicle, automotive'),
    'communications': ('Communications', 'telecom, telecommunications, ISP, broadband, 5G, satellite, radio, broadcast, network provider'),
    'water': ('Water and Wastewater', 'water, wastewater, utility, treatment plant, SCADA, ICS, municipal water'),
    'food': ('Food and Agriculture', 'agriculture, farm, food, processing, supply chain, USDA, livestock, crop'),
    'chemical': ('Chemical', 'chemical, manufacturing, plant, hazardous, ICS, OT'),
    'manufacturing': ('Critical Manufacturing', 'manufacturing, factory, industrial, ICS, OT, supply chain, semiconductor, electronics'),
    'defense': ('Defense Industrial Base', 'defense, DoD, military, contractor, aerospace, weapons, classified, research (defense)'),
    'commercial': ('Commercial Facilities', 'retail, shopping, mall, hotel, hospitality, stadium, entertainment, casino'),
    'emergency': ('Emergency Services', 'police, fire, EMS, 911, public safety, first responder'),
    'nuclear': ('Nuclear', 'nuclear, reactor, power plant, NRC'),
    'dams': ('Dams', 'dam, hydroelectric, water control'),
    'education_research': ('Education & Research', 'university, college, higher education, campus, student, faculty, staff, K-12, school, district, education, academic, research, lab, laboratory, R1, community college, EdTech, LMS, learning management, Canvas, Blackboard, Moodle, student information system, SIS, financial aid, bursar, enrollment, registrar, alumni, research data, intellectual property, IP theft, nation-state (research), APT (university)'),
    'education_platforms': ('EdTech & Shared Platforms', 'LMS, Canvas, Blackboard, Instructure, student portal, SSO, identity provider, Okta, Azure AD, Google Workspace, Microsoft 365, email, phishing (campus), ransomware (education), data breach (student), student PII, SSN, grades, transcripts'),
    'education_health': ('Healthcare (university-affiliated)', 'university hospital, teaching hospital, academic medical center, student health, research hospital, medical school, PHI (campus)'),
    'education_finance': ('Financial (campus-related)', 'student loan, financial aid, bursar, tuition, payment processor, scholarship, university finance'),
    'education_public': ('Government / Public (education overlap)', 'public university, state system, education department, student aid, Department of Education, research funding, grant'),
    'education_technology': ('Technology / SaaS (common on campus)', 'cloud, SaaS, identity, SSO, Active Directory, email compromise, phishing, supply chain (education vendor), zero-day (LMS or common campus software)'),
    'education_nation_state': ('Research & Nation-State', 'research, intellectual property, IP, nation-state, APT, espionage, China, Iran, Russia (academic targeting), quantum, AI research, defense research (university)'),
}
EDUCATION_QUICK = 'university, college, higher education, campus, student, faculty, K-12, school, education, academic, research, EdTech, LMS, Canvas, Blackboard, Instructure, student information system, financial aid, ransomware education, data breach student, phishing campus, nation-state research, university hospital, teaching hospital, student loan, public university, SSO, identity provider'
KEYWORDS = {key: tuple(term.strip() for term in words.split(',')) for key, (_, words) in SECTORS.items()}
KEYWORDS['education'] = tuple(dict.fromkeys([
    *(term.strip() for term in EDUCATION_QUICK.split(',')),
    *(term for key, terms in KEYWORDS.items() if key.startswith('education_') for term in terms)]))
SCOPES = {'': 'All', 'education': 'Education mode — all education keywords',
          **{key: value[0] for key, value in SECTORS.items()}}
CATALOG_VERSION = hashlib.sha256(json.dumps(KEYWORDS, sort_keys=True).encode()).hexdigest()[:16] + '-2'


def validate_scope(value):
    if not isinstance(value, str) or value not in SCOPES:
        raise ValueError('Choose a listed sector scope or All for all articles.')
    return value


def scope_signature(value):
    return CATALOG_VERSION + ':' + validate_scope(value) if value else ''


def normalize(text):
    text = unicodedata.normalize('NFKC', text)
    return text.translate(str.maketrans({'\u2010': '-', '\u2011': '-', '\u2012': '-',
                                       '\u2013': '-', '\u2014': '-', '\u00ad': ''}))


@lru_cache(maxsize=512)
def term_pattern(term):
    # Whole words prevent port/report, dam/damage, lab/label, and IT/it matches.
    # Hyphens and spaces are equivalent in phrases such as zero-day and K-12.
    def word(part):
        escaped = re.escape(part)
        if not part.isalpha() or len(part) < 3 or part.isupper():
            return escaped
        if part.lower() == 'campus':
            return escaped + '(?:es)?'
        if part.endswith('y') and part[-2].lower() not in 'aeiou':
            return re.escape(part[:-1]) + '(?:y|ies)'
        if part.endswith(('ch', 'sh', 'x')):
            return escaped + '(?:es)?'
        return escaped if part.endswith('s') else escaped + 's?'
    body = r'[\s-]+'.join(word(part) for part in re.split(r'[\s-]+', term))
    if term == 'K-12':
        body = r'K[\s-]*12'
    return re.compile(r'(?<!\w)' + body + r'(?!\w)', 0 if term in ('IT', 'OT', 'IP', 'RAT') else re.I)


def keyword_matches(term, text):
    contextual = re.fullmatch(r'(.+?)\s*\((.+)\)', term)
    if not contextual:
        return bool(term_pattern(term).search(text))
    base, qualifier = contextual.groups()
    return bool(term_pattern(base.strip()).search(text)) and any(
        term_pattern(context.strip()).search(text) for context in qualifier.split(' or '))


def classify(text):
    text = normalize(text)
    result = {}
    for scope, keywords in KEYWORDS.items():
        matches = [term for term in keywords if keyword_matches(term, text)]
        if matches:
            result[scope] = matches
    return result


def report_matches(report, scope):
    if not scope:
        return True
    validate_scope(scope)
    matches = report.get('sector_matches')
    if report.get('sector_catalog') == CATALOG_VERSION and isinstance(matches, dict):
        return bool(matches.get(scope))
    # Older saved reports have no full-text classification. The reader can
    # filter their available title/excerpt/summary; collection rechecks the page.
    text = [str(report.get(key, '')) for key in ('title', 'publisher_excerpt')]
    analysis = report.get('analysis')
    for claims in (analysis if isinstance(analysis, dict) else {}).values():
        if isinstance(claims, list):
            text.extend(str(claim.get('text', '')) for claim in claims if isinstance(claim, dict))
    return bool(classify('\n'.join(text)).get(scope))
