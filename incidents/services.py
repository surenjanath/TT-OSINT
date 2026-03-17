"""
AI extraction engine (Ollama) and geocoding services.
With granular per-article logging callbacks and progress tracking.
"""
import json
import logging
import re
import time
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from articles.models import Article
from .models import Incident, Person

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Trinidad & Tobago Location Fallback Dictionary
# Maps common place names → (lat, lng, region)
# ═══════════════════════════════════════════════════════════════
TT_LOCATIONS = {
    'port of spain': (10.6596, -61.5086, 'port_of_spain'),
    'san fernando': (10.2833, -61.4667, 'san_fernando'),
    'chaguanas': (10.5167, -61.4000, 'chaguanas'),
    'arima': (10.6333, -61.2833, 'arima'),
    'point fortin': (10.1833, -61.6833, 'point_fortin'),
    'diego martin': (10.6833, -61.5667, 'diego_martin'),
    'tunapuna': (10.6500, -61.3833, 'tunapuna_piarco'),
    'piarco': (10.5953, -61.3372, 'tunapuna_piarco'),
    'san juan': (10.6500, -61.4500, 'san_juan_laventille'),
    'laventille': (10.6500, -61.4833, 'san_juan_laventille'),
    'couva': (10.4333, -61.4500, 'couva_tabaquite_talparo'),
    'tabaquite': (10.3833, -61.3000, 'couva_tabaquite_talparo'),
    'sangre grande': (10.5833, -61.1333, 'sangre_grande'),
    'siparia': (10.1500, -61.5000, 'siparia'),
    'penal': (10.1667, -61.4667, 'penal_debe'),
    'debe': (10.2167, -61.4500, 'penal_debe'),
    'princes town': (10.2667, -61.3833, 'princes_town'),
    'mayaro': (10.2833, -61.0167, 'mayaro_rio_claro'),
    'rio claro': (10.3167, -61.1833, 'mayaro_rio_claro'),
    'scarborough': (11.1833, -60.7333, 'tobago'),
    'tobago': (11.2500, -60.6667, 'tobago'),
    'crown point': (11.1500, -60.8333, 'tobago'),
    'morvant': (10.6500, -61.4667, 'san_juan_laventille'),
    'barataria': (10.6333, -61.4333, 'san_juan_laventille'),
    'marabella': (10.3000, -61.4500, 'san_fernando'),
    'curepe': (10.6333, -61.4000, 'tunapuna_piarco'),
    'st augustine': (10.6333, -61.3833, 'tunapuna_piarco'),
    'saint augustine': (10.6333, -61.3833, 'tunapuna_piarco'),
    'st joseph': (10.6500, -61.4167, 'tunapuna_piarco'),
    'saint joseph': (10.6500, -61.4167, 'tunapuna_piarco'),
    'el socorro': (10.6167, -61.4167, 'san_juan_laventille'),
    'woodbrook': (10.6583, -61.5250, 'port_of_spain'),
    'st james': (10.6667, -61.5333, 'port_of_spain'),
    'saint james': (10.6667, -61.5333, 'port_of_spain'),
    'belmont': (10.6667, -61.5000, 'port_of_spain'),
    'newtown': (10.6667, -61.5167, 'port_of_spain'),
    'st clair': (10.6667, -61.5167, 'port_of_spain'),
    'maraval': (10.6833, -61.5333, 'diego_martin'),
    'petit valley': (10.6833, -61.5500, 'diego_martin'),
    'carenage': (10.6833, -61.5833, 'diego_martin'),
    'la brea': (10.2333, -61.6167, 'siparia'),
    'fyzabad': (10.1833, -61.4833, 'siparia'),
    'gasparillo': (10.3333, -61.4333, 'couva_tabaquite_talparo'),
    'claxton bay': (10.3500, -61.4667, 'couva_tabaquite_talparo'),
    'cunupia': (10.5500, -61.3833, 'chaguanas'),
    'longdenville': (10.5333, -61.3500, 'chaguanas'),
    'arouca': (10.6333, -61.3333, 'tunapuna_piarco'),
    'trincity': (10.6167, -61.3333, 'tunapuna_piarco'),
    'ariapita avenue': (10.6583, -61.5250, 'port_of_spain'),
    'frederick street': (10.6560, -61.5080, 'port_of_spain'),
    'charlotte street': (10.6560, -61.5050, 'port_of_spain'),
    'queens park savannah': (10.6667, -61.5133, 'port_of_spain'),
    'brian lara promenade': (10.6520, -61.5100, 'port_of_spain'),
    'wrightson road': (10.6500, -61.5100, 'port_of_spain'),
    'sea lots': (10.6500, -61.5167, 'port_of_spain'),
    'beetham': (10.6500, -61.4833, 'port_of_spain'),
    'enterprise': (10.2500, -61.4500, 'chaguanas'),
    'south oropouche': (10.1833, -61.4667, 'siparia'),
    'carapichaima': (10.4667, -61.4333, 'couva_tabaquite_talparo'),
    'freeport': (10.4667, -61.4167, 'couva_tabaquite_talparo'),
    'la romaine': (10.2833, -61.4667, 'san_fernando'),
    'santa cruz': (10.7000, -61.4667, 'san_juan_laventille'),
    'kelly village': (10.5333, -61.4167, 'chaguanas'),
    'bon air': (10.6333, -61.3167, 'tunapuna_piarco'),
    'mt hope': (10.6500, -61.4000, 'tunapuna_piarco'),
    'mount hope': (10.6500, -61.4000, 'tunapuna_piarco'),
    'champs fleurs': (10.6333, -61.4333, 'san_juan_laventille'),
    'diego martin highway': (10.6850, -61.5600, 'diego_martin'),
    'beetham highway': (10.6450, -61.4900, 'port_of_spain'),
    'lady young road': (10.6600, -61.4970, 'port_of_spain'),
    'churchill roosevelt highway': (10.6167, -61.3500, 'tunapuna_piarco'),
    'uriah butler highway': (10.5600, -61.4100, 'chaguanas'),
    'solomon hochoy highway': (10.4500, -61.4300, 'couva_tabaquite_talparo'),
    'Priority bus route': (10.6500, -61.4800, 'san_juan_laventille'),
    # POS & environs — more neighborhoods and landmarks
    'beetham gardens': (10.6480, -61.4850, 'san_juan_laventille'),
    'laventille hill': (10.6520, -61.4780, 'san_juan_laventille'),
    'east dry river': (10.6550, -61.5120, 'port_of_spain'),
    'gonzales': (10.6620, -61.5180, 'port_of_spain'),
    'bamboo settlement': (10.6680, -61.4950, 'san_juan_laventille'),
    'john john': (10.6540, -61.4880, 'san_juan_laventille'),
    'sea view': (10.6520, -61.5200, 'port_of_spain'),
    'cocorite': (10.6680, -61.5380, 'port_of_spain'),
    'flagstaff': (10.6720, -61.5150, 'port_of_spain'),
    'st anns': (10.6700, -61.5080, 'port_of_spain'),
    'saint anns': (10.6700, -61.5080, 'port_of_spain'),
    'cascade': (10.6720, -61.5020, 'port_of_spain'),
    'east port of spain': (10.6580, -61.5020, 'port_of_spain'),
    'coronation': (10.6620, -61.4950, 'san_juan_laventille'),
    'duncan street pos': (10.6540, -61.5080, 'port_of_spain'),
    'independence square': (10.6520, -61.5080, 'port_of_spain'),
    'woodford square': (10.6540, -61.5060, 'port_of_spain'),
    'chaguaramas': (10.6833, -61.6167, 'diego_martin'),
    'westmoorings': (10.6780, -61.5480, 'diego_martin'),
    'goodwood park': (10.6750, -61.5420, 'diego_martin'),
    'glencoe': (10.6880, -61.5750, 'diego_martin'),
    'blanchisseuse': (10.7667, -61.3000, 'sangre_grande'),
    'toco': (10.8333, -60.9500, 'sangre_grande'),
    'matelot': (10.8167, -61.0500, 'sangre_grande'),
    'sangre grande town': (10.5833, -61.1333, 'sangre_grande'),
    'guaico': (10.5667, -61.1167, 'sangre_grande'),
    'manzanilla': (10.4500, -61.0500, 'sangre_grande'),
    # San Fernando & South
    'san fernando hill': (10.2850, -61.4680, 'san_fernando'),
    'high street san fernando': (10.2833, -61.4667, 'san_fernando'),
    'marabella': (10.3000, -61.4500, 'san_fernando'),
    'vistabella': (10.2930, -61.4580, 'san_fernando'),
    'clifton hill': (10.2780, -61.4720, 'san_fernando'),
    'mon repos': (10.2900, -61.4550, 'san_fernando'),
    'st joseph village': (10.2680, -61.4380, 'princes_town'),
    'st marys': (10.2720, -61.3850, 'princes_town'),
    'moruga': (10.1500, -61.2833, 'princes_town'),
    'barrackpore': (10.2333, -61.3667, 'princes_town'),
    'debe junction': (10.2167, -61.4500, 'penal_debe'),
    'penal rock road': (10.1700, -61.4700, 'penal_debe'),
    'siparia town': (10.1500, -61.5000, 'siparia'),
    'fyzabad': (10.1833, -61.4833, 'siparia'),
    'point fortin town': (10.1833, -61.6833, 'point_fortin'),
    'la fortune': (10.2167, -61.4667, 'penal_debe'),
    # Chaguanas & Central
    'chaguanas main road': (10.5167, -61.4000, 'chaguanas'),
    'montrose': (10.5080, -61.4080, 'chaguanas'),
    'chase village': (10.5400, -61.3950, 'chaguanas'),
    'felicity': (10.5280, -61.3780, 'chaguanas'),
    'waterloo': (10.5050, -61.4180, 'chaguanas'),
    'caroni': (10.5333, -61.4167, 'chaguanas'),
    'preysal': (10.4800, -61.4380, 'couva_tabaquite_talparo'),
    'pointe a pierre': (10.3167, -61.4500, 'san_fernando'),
    'point a pierre': (10.3167, -61.4500, 'san_fernando'),
    'st margarets': (10.3500, -61.4550, 'couva_tabaquite_talparo'),
    'brasso': (10.3833, -61.3167, 'couva_tabaquite_talparo'),
    'tabaquite': (10.3833, -61.3000, 'couva_tabaquite_talparo'),
    'talparo': (10.4167, -61.2833, 'couva_tabaquite_talparo'),
    'rio claro village': (10.3167, -61.1833, 'mayaro_rio_claro'),
    'biche': (10.2833, -61.0500, 'mayaro_rio_claro'),
    'mayaro village': (10.2833, -61.0167, 'mayaro_rio_claro'),
    'guayaguayare': (10.1667, -61.0167, 'mayaro_rio_claro'),
    # Tobago — villages and landmarks
    'plymouth': (11.2167, -60.7833, 'tobago'),
    'charlotteville': (11.3000, -60.5500, 'tobago'),
    'speyside': (11.2833, -60.5333, 'tobago'),
    'roxborough': (11.2500, -60.5833, 'tobago'),
    'castara': (11.2833, -60.7000, 'tobago'),
    'bloody bay': (11.2667, -60.7167, 'tobago'),
    'buccoo': (11.1667, -60.8333, 'tobago'),
    'store bay': (11.1500, -60.8333, 'tobago'),
    'pidgeon point': (11.1333, -60.8500, 'tobago'),
    'black rock': (11.2000, -60.7667, 'tobago'),
    'lowlands': (11.1833, -60.7500, 'tobago'),
    'canaan': (11.1833, -60.7333, 'tobago'),
    'bon accord': (11.1667, -60.7333, 'tobago'),
    'crown point airport': (11.1498, -60.8322, 'tobago'),
    'scarborough hospital': (11.1833, -60.7333, 'tobago'),
    # Police stations and key buildings (approximate)
    'port of spain general hospital': (10.6580, -61.5080, 'port_of_spain'),
    'san fernando general hospital': (10.2833, -61.4667, 'san_fernando'),
    'eric williams medical complex': (10.6500, -61.4000, 'tunapuna_piarco'),
    'chaguanas police station': (10.5167, -61.4000, 'chaguanas'),
    'san juan police station': (10.6500, -61.4500, 'san_juan_laventille'),
    'arima police station': (10.6333, -61.2833, 'arima'),
    'st joseph police station': (10.6500, -61.4167, 'tunapuna_piarco'),
    'couva police station': (10.4333, -61.4500, 'couva_tabaquite_talparo'),
    'princes town police station': (10.2667, -61.3833, 'princes_town'),
    'siparia police station': (10.1500, -61.5000, 'siparia'),
    'point fortin police station': (10.1833, -61.6833, 'point_fortin'),
    'scarborough police station': (11.1833, -60.7333, 'tobago'),
    # More highways and roads
    'sir solomon hochoy highway': (10.4500, -61.4300, 'couva_tabaquite_talparo'),
    'priority bus route pos': (10.6500, -61.4800, 'san_juan_laventille'),
    'elizabeth street': (10.6560, -61.5100, 'port_of_spain'),
    'henry street': (10.6550, -61.5070, 'port_of_spain'),
    'park street': (10.6580, -61.5060, 'port_of_spain'),
    'tragarete road': (10.6620, -61.5200, 'port_of_spain'),
    'lady hailes avenue': (10.2800, -61.4650, 'san_fernando'),
    'cipero road': (10.2900, -61.4480, 'san_fernando'),
    'gulf city': (10.2950, -61.4550, 'san_fernando'),
    'long circular mall': (10.6380, -61.4280, 'san_juan_laventille'),
    'west mall': (10.6680, -61.5380, 'port_of_spain'),
    'grand bazaar': (10.6200, -61.3680, 'tunapuna_piarco'),
    'trincity mall': (10.6167, -61.3333, 'tunapuna_piarco'),
    'price plaza': (10.5167, -61.4000, 'chaguanas'),
    'south park': (10.2850, -61.4600, 'san_fernando'),
    # Additional neighborhoods
    'el dorado': (10.6400, -61.3800, 'tunapuna_piarco'),
    'tacarigua': (10.6167, -61.3667, 'tunapuna_piarco'),
    'wallerfield': (10.6167, -61.3500, 'tunapuna_piarco'),
    'cleaver woods': (10.6280, -61.3920, 'tunapuna_piarco'),
    'orange grove': (10.6100, -61.3580, 'tunapuna_piarco'),
    'mausica': (10.6000, -61.3400, 'tunapuna_piarco'),
    'omeara': (10.5700, -61.3800, 'chaguanas'),
    'edinburgh': (10.5200, -61.3850, 'chaguanas'),
    'california': (10.5080, -61.3920, 'chaguanas'),
    'reform': (10.2680, -61.3950, 'princes_town'),
    'tableland': (10.2500, -61.3500, 'princes_town'),
    'roper road': (10.2580, -61.3780, 'princes_town'),
    'new grant': (10.2333, -61.3833, 'princes_town'),
    'pearl': (10.2000, -61.4500, 'penal_debe'),
    'siparia ervilla': (10.1333, -61.5000, 'siparia'),
    'la brea junction': (10.2333, -61.6167, 'siparia'),
    'avocat': (10.2667, -61.4833, 'siparia'),
    'fanny village': (10.1833, -61.4833, 'siparia'),
    'guapo': (10.2000, -61.6167, 'siparia'),
    'fullerton': (10.1833, -61.6500, 'point_fortin'),
    'mahaila': (10.2167, -61.4667, 'penal_debe'),
    'parfum gardens': (10.6500, -61.4750, 'san_juan_laventille'),
    'green acres': (10.6420, -61.4420, 'san_juan_laventille'),
    'laventille road': (10.6520, -61.4780, 'san_juan_laventille'),
    'beetham': (10.6500, -61.4833, 'san_juan_laventille'),
    'nevada': (10.6480, -61.4920, 'san_juan_laventille'),
    'san juan market': (10.6500, -61.4500, 'san_juan_laventille'),
    'bourg mulatresse': (10.6550, -61.4720, 'san_juan_laventille'),
    'mucurapo': (10.6650, -61.5320, 'port_of_spain'),
    'diego martin main road': (10.6850, -61.5600, 'diego_martin'),
    'bagatelle': (10.6380, -61.3580, 'tunapuna_piarco'),
    'valsayn': (10.6420, -61.3980, 'tunapuna_piarco'),
    'saint augustine': (10.6333, -61.3833, 'tunapuna_piarco'),
    'university of trinidad': (10.6400, -61.4000, 'tunapuna_piarco'),
    'uta': (10.6400, -61.4000, 'tunapuna_piarco'),
    'el socorro south': (10.6167, -61.4167, 'san_juan_laventille'),
    'maloney': (10.6080, -61.4080, 'san_juan_laventille'),
    'diamond vale': (10.6720, -61.5580, 'diego_martin'),
    'four roads': (10.6780, -61.5450, 'diego_martin'),
    'blue basin': (10.6900, -61.5780, 'diego_martin'),
    'paramin': (10.7000, -61.5300, 'diego_martin'),
    'arima market': (10.6333, -61.2833, 'arima'),
    'arima velodrome': (10.6350, -61.2850, 'arima'),
    'tumpuna road': (10.6380, -61.2780, 'arima'),
    'wallerfield road': (10.6200, -61.3200, 'arima'),
    'sangre grande market': (10.5833, -61.1333, 'sangre_grande'),
    'cumuto': (10.5167, -61.1833, 'sangre_grande'),
    'tamana': (10.4500, -61.1500, 'sangre_grande'),
    'mayaro beach': (10.2833, -61.0167, 'mayaro_rio_claro'),
    'radix village': (10.2667, -61.0500, 'mayaro_rio_claro'),
}

# ═══════════════════════════════════════════════════════════════
# Category mapping
# ═══════════════════════════════════════════════════════════════
CATEGORY_MAP = {
    # Shooting
    'shooting': 'shooting',
    'gunfire': 'shooting',
    'shot': 'shooting',
    'firearm discharge': 'shooting',
    # Murder
    'murder': 'murder',
    'homicide': 'murder',
    'killing': 'murder',
    'manslaughter': 'murder',
    'double murder': 'murder',
    'triple murder': 'murder',
    # Robbery / theft — MUST come before generic terms
    'robbery': 'robbery',
    'larceny': 'robbery',
    'theft': 'robbery',
    'burglary': 'robbery',
    'stolen': 'robbery',
    'stealing': 'robbery',
    'break-in': 'robbery',
    'break in': 'robbery',
    'heist': 'robbery',
    'carjacking': 'robbery',
    'car theft': 'robbery',
    'vehicle theft': 'robbery',
    'snatching': 'robbery',
    'snatch': 'robbery',
    'robbed': 'robbery',
    'stole': 'robbery',
    'piracy': 'robbery',
    # Assault
    'assault': 'assault',
    'stabbing': 'assault',
    'wounding': 'assault',
    'chopping': 'assault',
    'cutlass': 'assault',
    'beating': 'assault',
    'attack': 'assault',
    # Kidnapping
    'kidnapping': 'kidnapping',
    'abduction': 'kidnapping',
    'kidnap': 'kidnapping',
    # Violent crime
    'violent crime': 'violent_crime',
    'gang': 'violent_crime',
    # Traffic accidents
    'traffic accident': 'traffic_accident',
    'vehicular': 'traffic_accident',
    'road accident': 'traffic_accident',
    'hit-and-run': 'traffic_accident',
    'hit and run': 'traffic_accident',
    'fatal crash': 'traffic_accident',
    # Vehicle collision (actual crashes, NOT stolen vehicles)
    'collision': 'vehicle_collision',
    'crash': 'vehicle_collision',
    'pile-up': 'vehicle_collision',
    'pileup': 'vehicle_collision',
    # Pedestrian
    'pedestrian': 'pedestrian_accident',
    # Fire
    'fire': 'fire',
    'arson': 'fire',
    'blaze': 'fire',
    'inferno': 'fire',
    # Flood (weather flooding, NOT drowning)
    'flood': 'flood',
    'flooding': 'flood',
    # Natural disaster
    'landslide': 'natural_disaster',
    'earthquake': 'natural_disaster',
    'hurricane': 'natural_disaster',
    'storm': 'natural_disaster',
    'natural disaster': 'natural_disaster',
    # Police activity
    'police': 'police_activity',
    'ttps': 'police_activity',
    'arrest': 'police_activity',
    'raid': 'police_activity',
    'seizure': 'police_activity',
    'warrant': 'police_activity',
    # Drug related
    'drug': 'drug_related',
    'marijuana': 'drug_related',
    'cocaine': 'drug_related',
    'narcotics': 'drug_related',
    'cannabis': 'drug_related',
    'heroin': 'drug_related',
    # Domestic violence
    'domestic': 'domestic_violence',
    # Fraud
    'fraud': 'fraud',
    'scam': 'fraud',
    'embezzlement': 'fraud',
    # Other — drowning, electrocution, etc.
    'drowning': 'other',
    'drowned': 'other',
    'electrocution': 'other',
    'electrocuted': 'other',
}


class OllamaExtractor:
    """Extract incident data from article text using Ollama LLM."""

    PROMPT_VERSION = 'v3'

    EXTRACTION_PROMPT = """You are an incident extraction engine for Trinidad and Tobago news.
Your job is to find EVERY newsworthy incident in the article. Be AGGRESSIVE — do NOT return an empty array unless the article is truly just opinion, entertainment, sports scores, or politics with zero criminal/safety events.

The article was published on {publish_date}.

WHAT COUNTS AS AN INCIDENT (extract ALL of these):
- ANY crime: theft, robbery, break-in, larceny, stolen property, stolen vehicles, burglary, fraud, scam
- ANY violent crime: murder, shooting, stabbing, assault, chopping, kidnapping, domestic violence
- ANY accident: traffic collision, drowning, workplace accident, electrocution, industrial accident
- ANY disaster: fire, flood, landslide, building collapse
- ANY drug activity: drug seizure, drug bust, marijuana find, cocaine find
- ANY police action: arrest, raid, seizure, wanted person captured, police chase
- Deaths from ANY cause (drowning, fire, accident, medical negligence, etc.)

CRITICAL DATE RULES:
- The "date" field MUST be within a few days of {publish_date}. News reports recent events.
- If the article says "Friday", "yesterday", "last week", calculate relative to {publish_date}.
- If unsure, use "{publish_date}".

CATEGORY DEFINITIONS — choose the BEST match:
- robbery: theft, larceny, stolen property, stolen vehicles, break-ins, burglary, carjacking, snatching
- murder: killing, homicide, manslaughter (someone died from violence)
- shooting: gunfire, shot, firearm discharge (no death)
- assault: stabbing, chopping, wounding, beating, cutlass attack (no death)
- kidnapping: abduction, missing person taken by force
- violent_crime: gang violence, armed confrontation, other violent acts
- traffic_accident: road accident, vehicular accident, hit-and-run, fatal crash
- vehicle_collision: two or more vehicles collided (NOT stolen vehicles — that is robbery)
- pedestrian_accident: pedestrian struck by vehicle
- fire: structure fire, bush fire, arson, blaze
- flood: weather-related flooding of areas, NOT drowning at a beach or river
- natural_disaster: earthquake, hurricane, storm, landslide
- police_activity: arrest, police raid, drug seizure, warrant execution, suspect captured
- drug_related: drug possession, drug trafficking, marijuana/cocaine/narcotics find
- domestic_violence: abuse within household or family
- fraud: financial fraud, scam, identity theft, embezzlement
- other: drowning, electrocution, industrial accident, workplace death, any incident not fitting above

COMMON MISCLASSIFICATIONS TO AVOID:
- Stolen/recovered vehicle = "robbery", NOT "vehicle_collision" (collision means crash/impact)
- Drowning at beach/river/pool = "other", NOT "flood" (flood means area flooding from weather)
- Person found dead (no violence) = "other", NOT "murder" (unless foul play confirmed)
- Drug seizure by police = "drug_related" (primary) — only use "police_activity" if no drugs involved
- Chopping/cutlass attack = "assault", NOT "other"

For each incident, return a JSON object with these fields:

REQUIRED:
- incident_type: short descriptive label (e.g. "Robbery", "Vehicle Theft", "Drowning", "Double Murder", "Drug Seizure", "Larceny", "Stolen Vehicle Recovery")
- category: one of: shooting, murder, robbery, assault, kidnapping, violent_crime, traffic_accident, vehicle_collision, pedestrian_accident, fire, flood, natural_disaster, police_activity, drug_related, domestic_violence, fraud, other
- severity: low / medium / high / critical
  * critical = deaths occurred
  * high = firearms used, serious injury, large value theft (>$50,000)
  * medium = property crime, minor injury
  * low = no injury, minor property damage, recovery of stolen goods
- confidence: 0-100

LOCATION (be maximally specific — copy exact wording from article):
- location: exact location text (e.g. "Hyatt Regency Hotel, Port of Spain", "Union Road near Solera, Marabella")
- city: specific town (e.g. "Port of Spain", "Marabella", "Sangre Grande")
- region: municipality (e.g. "Port of Spain", "San Fernando", "Tunapuna-Piarco")

TIME:
- date: YYYY-MM-DD format. MUST be near {publish_date}.
- time: HH:MM 24h format if mentioned, else ""

DETAILS:
- description: 2-3 sentence factual summary of THIS incident only. CRITICAL: The narrative must match the numbers you set below. If fatality_count is 1, say one person was killed (e.g. "One man was shot dead at ..."); if 2, say two; never say "three men were shot dead" unless fatality_count is 3. Describe only this single incident, not other incidents in the article.
- victim_count: integer (0 if unknown)
- fatality_count: integer (0 if unknown)
- injured_count: integer — number injured but not killed (0 if unknown)
- suspect_description: brief text or ""
- weapon: "firearm", "knife", "cutlass", etc. or ""
- vehicle_info: make/model/color/plate if mentioned, or ""
- value_stolen: number or null — estimated value in TTD/USD if theft/robbery/fraud, else null
- premises_type: one of: residence, business, road, school, hospital, public_space, vehicle, other (or "" if unknown)
- motive: brief motive if mentioned (e.g. "gang-related", "domestic dispute"), else ""
- is_resolved: true if arrests made or case resolved, else false

PERSONS (extract ALL named or described individuals):
- persons: array of objects, each with:
  - role: "victim", "suspect", "arrested", or "witness"
  - name: full name if mentioned, else ""
  - age: integer if mentioned, else null
  - gender: "male", "female", or "unknown"
  - condition: "uninjured", "injured", "hospitalized", "deceased", or "unknown"
  - description: brief text (e.g. "taxi driver from Chaguanas")
  - address: home address/area if mentioned, else ""
  - occupation: if mentioned, else ""

When an article describes multiple incidents (e.g. "three men were shot dead in separate incidents"), output one JSON object per incident. Each object's description, victim_count, and fatality_count must refer to THAT incident only (e.g. the first incident = 1 fatality, the second = 1, the third = 1), not the article total.

Return ONLY a valid JSON array. No markdown, no explanation. Empty array [] ONLY if truly no incidents.

ARTICLE:
{article_text}
"""

    def extract_incidents(self, article: Article, log_fn=None) -> list[dict]:
        """Send article to Ollama and parse extracted incidents."""
        if not article.content or not article.content.strip():
            msg = 'Article has no content'
            if log_fn:
                log_fn(f'    ⚠️ Article #{article.id} has no content — skipping AI', 'warning')
            raise ValueError(msg)

        # Get settings from DB, gracefully handling if DB not ready
        from core.models import SystemSetting
        try:
            ollama_host = SystemSetting.get_setting('ollama_host', getattr(settings, 'OLLAMA_HOST', 'http://localhost:11434')).rstrip('/')
            ollama_model = SystemSetting.get_setting('ollama_model', getattr(settings, 'OLLAMA_MODEL', 'llama3'))
            max_chars = int(SystemSetting.get_setting('ai_content_max_chars', '6000'))
            temperature = float(SystemSetting.get_setting('ai_temperature', '0.1'))
            num_predict = int(SystemSetting.get_setting('ai_num_predict', '2000'))
            timeout_sec = int(SystemSetting.get_setting('ai_timeout', '120'))
            db_prompt = SystemSetting.get_setting('ai_extraction_prompt', '').strip()
            prompt_version = SystemSetting.get_setting('ai_prompt_version', '')
            if db_prompt and prompt_version == self.PROMPT_VERSION:
                prompt_template = db_prompt
            else:
                prompt_template = self.EXTRACTION_PROMPT
                SystemSetting.set_setting('ai_extraction_prompt', '')
                SystemSetting.set_setting('ai_prompt_version', self.PROMPT_VERSION)
        except Exception:
            ollama_host = getattr(settings, 'OLLAMA_HOST', 'http://localhost:11434').rstrip('/')
            ollama_model = getattr(settings, 'OLLAMA_MODEL', 'llama3')
            max_chars = 6000
            temperature = 0.1
            num_predict = 2000
            timeout_sec = 120
            prompt_template = self.EXTRACTION_PROMPT

        max_chars = max(500, min(30000, max_chars))
        text = article.content[:max_chars]

        # Pass article publish date so the AI anchors dates correctly
        pub_date_str = ''
        if article.published_date:
            pub_date_str = article.published_date.strftime('%Y-%m-%d')
        else:
            pub_date_str = timezone.now().strftime('%Y-%m-%d')

        try:
            prompt = prompt_template.format(
                article_text=text,
                publish_date=pub_date_str,
            )
        except KeyError:
            prompt = self.EXTRACTION_PROMPT.format(
                article_text=text,
                publish_date=pub_date_str,
            )

        try:
            if log_fn:
                log_fn(f'    🤖 Sending to Ollama ({len(text)} chars)...', 'info')

            start = time.time()
            response = requests.post(
                f"{ollama_host}/api/generate",
                json={
                    'model': ollama_model,
                    'prompt': prompt,
                    'stream': False,
                    'options': {
                        'temperature': max(0, min(2, temperature)),
                        'num_predict': max(256, min(8192, num_predict)),
                    },
                },
                timeout=timeout_sec,
            )
            response.raise_for_status()
            elapsed = time.time() - start

            result = response.json()
            raw_text = result.get('response', '')
            incidents = self._parse_json_response(raw_text)

            if log_fn:
                if incidents:
                    types = [i.get('incident_type', '?') for i in incidents]
                    log_fn(
                        f'    🎯 AI found {len(incidents)} incident(s) in {elapsed:.1f}s: {", ".join(types)}',
                        'success'
                    )
                else:
                    log_fn(f'    ○ No incidents detected ({elapsed:.1f}s)', 'info')

            return incidents

        except requests.exceptions.ConnectionError as e:
            msg = 'Cannot connect to Ollama — is it running? (Start with: ollama serve)'
            logger.error(msg)
            if log_fn:
                log_fn(f'❌ {msg}', 'error')
            raise RuntimeError(msg) from e
        except requests.exceptions.Timeout as e:
            msg = f'Ollama request timed out ({timeout_sec}s)'
            if log_fn:
                log_fn(f'    ⏱️ {msg}', 'error')
            raise RuntimeError(msg) from e
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 404:
                msg = f"Model not found. Please run `ollama pull {ollama_model}`"
                logger.error(msg)
                if log_fn:
                    log_fn(f'❌ {msg}', 'error')
            else:
                msg = str(e)
                logger.error(f"Ollama HTTP error: {e}")
                if log_fn:
                    log_fn(f'    ❌ AI error: {e}', 'error')
            raise RuntimeError(msg or 'Ollama HTTP error') from e
        except Exception as e:
            logger.error(f"Ollama extraction error: {e}")
            if log_fn:
                log_fn(f'    ❌ AI error: {type(e).__name__}: {e}', 'error')
            raise

    def _parse_json_response(self, text: str) -> list[dict]:
        """Parse JSON from LLM response, handling common formatting issues."""
        text = text.strip()

        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning(f"Could not parse JSON from LLM response: {text[:200]}")
        return []


class GeocodingService:
    """Multi-provider geocoding for Trinidad and Tobago.

    Provider chain (configurable via Settings):
      1. Google Maps Geocoding API (if API key set — best accuracy, 10k/month free)
      2. geocode.xyz (free, no key, decent TT coverage)
      3. Nominatim / OSM (free, good for neighborhoods)
      4. TT_LOCATIONS dictionary (instant offline fallback)
    """

    _DIRECTIONAL_PREFIXES = ('east ', 'west ', 'north ', 'south ',
                             'upper ', 'lower ', 'central ')
    _NOM_HEADERS = {'User-Agent': 'TT_OSINT/1.0 (tt-crime-map)'}
    TT_BBOX = (9.8, -62.1, 11.5, -60.0)

    def _get_google_key(self):
        from core.models import SystemSetting
        try:
            return SystemSetting.get_setting('google_maps_api_key', '').strip()
        except Exception:
            return ''

    def geocode(self, location_name: str, city: str = '', region: str = '', log_fn=None) -> dict:
        if not location_name:
            return {'latitude': None, 'longitude': None, 'region': 'unknown'}

        loc_lower = location_name.lower().strip()

        # 1. Exact dictionary match (instant, free)
        if loc_lower in TT_LOCATIONS:
            lat, lng, reg = TT_LOCATIONS[loc_lower]
            if log_fn:
                log_fn(f'    [dict] "{location_name}" -> {reg}', 'info')
            return {'latitude': lat, 'longitude': lng, 'region': reg}

        # 2. Google Maps (if API key configured — best accuracy)
        google_key = self._get_google_key()
        if google_key:
            result = self._google_geocode(location_name, city, google_key, log_fn)
            if result['latitude'] is not None:
                return result

        # 3. geocode.xyz (free, no key, good TT data)
        result = self._geocodexyz(location_name, city, log_fn)
        if result['latitude'] is not None:
            return result

        # 4. Nominatim with smart query variations
        queries = self._build_nominatim_queries(location_name, city)
        for query in queries:
            result = self._nominatim_single(query, log_fn)
            if result['latitude'] is not None:
                return result

        # 5. Partial dictionary match
        search_terms = [t for t in [loc_lower, city.lower().strip(), region.lower().strip()] if t]
        for term in search_terms:
            for key, (lat, lng, reg) in TT_LOCATIONS.items():
                if term in key or key in term:
                    if log_fn:
                        log_fn(f'    [dict] partial: "{location_name}" -> {reg} ("{key}")', 'info')
                    return {'latitude': lat, 'longitude': lng, 'region': reg}

        if log_fn:
            log_fn(f'    [!] Could not geocode "{location_name}"', 'warning')
        return {'latitude': None, 'longitude': None, 'region': 'unknown'}

    def _in_tt(self, lat, lng):
        return (self.TT_BBOX[0] <= lat <= self.TT_BBOX[2]
                and self.TT_BBOX[1] <= lng <= self.TT_BBOX[3])

    # ------------------------------------------------------------------
    # Google Maps Geocoding API
    # ------------------------------------------------------------------

    def _google_geocode(self, location: str, city: str, api_key: str, log_fn=None) -> dict:
        addr = f"{location}, Trinidad and Tobago"
        try:
            if log_fn:
                log_fn(f'    [google] "{location}"', 'info')
            resp = requests.get(
                'https://maps.googleapis.com/maps/api/geocode/json',
                params={'address': addr, 'key': api_key, 'components': 'country:TT'},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get('results'):
                geo = data['results'][0]['geometry']['location']
                lat, lng = float(geo['lat']), float(geo['lng'])
                if self._in_tt(lat, lng):
                    region = self._classify_region(lat, lng)
                    if log_fn:
                        log_fn(f'    [google] ({lat:.6f}, {lng:.6f}) -> {region}', 'success')
                    return {'latitude': lat, 'longitude': lng, 'region': region}
        except Exception as e:
            logger.debug(f"Google geocode: {e}")
        return {'latitude': None, 'longitude': None, 'region': 'unknown'}

    # ------------------------------------------------------------------
    # geocode.xyz (free, no key, 1 req/sec)
    # ------------------------------------------------------------------

    def _geocodexyz(self, location: str, city: str, log_fn=None) -> dict:
        """geocode.xyz — free tier, good TT coverage, throttles aggressively."""
        queries = [location]
        if city and city.lower() not in location.lower():
            queries.insert(0, f"{location}, {city}")

        for q in queries:
            addr = f"{q}, Trinidad and Tobago"
            try:
                time.sleep(2)
                if log_fn:
                    log_fn(f'    [geocode.xyz] "{q}"', 'info')
                resp = requests.get(
                    'https://geocode.xyz/',
                    params={'locate': addr, 'region': 'TT', 'json': '1'},
                    headers={'User-Agent': 'TT_OSINT/1.0 (tt-crime-map)'},
                    timeout=15,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                lat_s = str(data.get('latt', ''))
                lng_s = str(data.get('longt', ''))
                if 'Throttled' in lat_s or not lat_s:
                    if log_fn:
                        log_fn(f'    [geocode.xyz] throttled — skipping', 'warning')
                    continue
                lat, lng = float(lat_s), float(lng_s)
                if abs(lat) < 0.01 and abs(lng) < 0.01:
                    continue
                if self._in_tt(lat, lng):
                    region = self._classify_region(lat, lng)
                    if log_fn:
                        log_fn(f'    [geocode.xyz] ({lat:.6f}, {lng:.6f}) -> {region}', 'success')
                    return {'latitude': lat, 'longitude': lng, 'region': region}
            except Exception as e:
                logger.debug(f"geocode.xyz '{q}': {e}")
                continue

        return {'latitude': None, 'longitude': None, 'region': 'unknown'}

    # ------------------------------------------------------------------
    # Nominatim query builder — neighborhoods BEFORE street+city combos
    # ------------------------------------------------------------------

    def _strip_directional(self, text: str) -> str:
        t = text.strip()
        for prefix in self._DIRECTIONAL_PREFIXES:
            if t.lower().startswith(prefix):
                return t[len(prefix):].strip()
        return t

    def _build_nominatim_queries(self, location: str, city: str) -> list[str]:
        """Build Nominatim queries ordered for TT: neighborhood > full > street+city."""
        parts = [p.strip() for p in location.split(',') if p.strip()]
        seen = set()
        queries = []
        TT = 'Trinidad and Tobago'

        def _add(q: str):
            key = q.lower().strip()
            if key and key not in seen:
                seen.add(key)
                queries.append(q)

        if len(parts) == 1:
            _add(f'{parts[0]}, {city}, {TT}' if city else f'{parts[0]}, {TT}')
            stripped = self._strip_directional(parts[0])
            if stripped.lower() != parts[0].lower():
                _add(f'{stripped}, {TT}')
            return queries

        stripped_last = self._strip_directional(parts[-1])

        # A. Full original
        _add(f'{location}, {TT}')

        # B. Full with directional stripped
        if stripped_last.lower() != parts[-1].lower():
            _add(', '.join(parts[:-1] + [stripped_last]) + f', {TT}')

        # C. NEIGHBORHOOD ALONE — highest value for TT (OSM has neighborhoods mapped)
        #    For "22nd St, Beetham Gardens, East POS" this tries "Beetham Gardens, TT"
        for part in parts[1:-1] if len(parts) >= 3 else []:
            _add(f'{part}, {TT}')

        # D. Drop street → neighborhood + city
        if len(parts) >= 2:
            _add(', '.join(parts[1:]) + f', {TT}')
            if stripped_last.lower() != parts[-1].lower():
                _add(', '.join(parts[1:-1] + [stripped_last]) + f', {TT}')

        # E. Street + city (skip neighborhood) — may find wrong street, so goes late
        if len(parts) >= 3:
            _add(f'{parts[0]}, {stripped_last}, {TT}')
            _add(f'{parts[0]}, {parts[-1]}, {TT}')

        # F. City alone
        if city:
            stripped_city = self._strip_directional(city)
            _add(f'{stripped_city}, {TT}')
            if stripped_city.lower() != city.lower():
                _add(f'{city}, {TT}')

        return queries

    # ------------------------------------------------------------------
    # Nominatim: single free-text query
    # ------------------------------------------------------------------

    def _nominatim_single(self, query: str, log_fn=None) -> dict:
        try:
            time.sleep(1.05)
            if log_fn:
                log_fn(f'    [nom] "{query}"', 'info')
            response = requests.get(
                'https://nominatim.openstreetmap.org/search',
                params={'q': query, 'format': 'json', 'limit': 1, 'countrycodes': 'tt'},
                headers=self._NOM_HEADERS, timeout=10,
            )
            response.raise_for_status()
            results = response.json()
            if results:
                lat, lng = float(results[0]['lat']), float(results[0]['lon'])
                if self._in_tt(lat, lng):
                    region = self._classify_region(lat, lng)
                    if log_fn:
                        log_fn(f'    [nom] ({lat:.6f}, {lng:.6f}) -> {region}', 'success')
                    return {'latitude': lat, 'longitude': lng, 'region': region}
        except Exception as e:
            logger.debug(f"Nominatim '{query}': {e}")
        return {'latitude': None, 'longitude': None, 'region': 'unknown'}

    def _classify_region(self, lat: float, lng: float) -> str:
        """Classify coordinates into a TT region. Uses ordered bounding boxes then nearest-point fallback."""
        # Ordered (region, lat_lo, lat_hi, lng_lo, lng_hi) — more specific areas first to avoid overlap
        bounds = [
            ('port_of_spain', 10.642, 10.678, -61.535, -61.495),
            ('diego_martin', 10.665, 10.720, -61.620, -61.530),
            ('san_juan_laventille', 10.605, 10.705, -61.505, -61.410),
            ('tunapuna_piarco', 10.575, 10.685, -61.430, -61.320),
            ('arima', 10.615, 10.660, -61.295, -61.265),
            ('chaguanas', 10.495, 10.565, -61.455, -61.350),
            ('couva_tabaquite_talparo', 10.330, 10.495, -61.505, -61.250),
            ('san_fernando', 10.268, 10.318, -61.505, -61.435),
            ('princes_town', 10.195, 10.305, -61.430, -61.280),
            ('penal_debe', 10.148, 10.250, -61.505, -61.415),
            ('siparia', 10.095, 10.220, -61.620, -61.440),
            ('point_fortin', 10.148, 10.220, -61.700, -61.640),
            ('sangre_grande', 10.450, 10.850, -61.200, -60.920),
            ('mayaro_rio_claro', 10.145, 10.350, -61.220, -61.000),
            ('tobago', 11.090, 11.350, -60.880, -60.500),
        ]
        for region, lat_lo, lat_hi, lng_lo, lng_hi in bounds:
            if lat_lo <= lat <= lat_hi and lng_lo <= lng <= lng_hi:
                return region
        # Fallback: nearest point in TT_LOCATIONS
        best_region = 'unknown'
        best_dist = 1e9
        for _key, (la, ln, reg) in TT_LOCATIONS.items():
            dist = (lat - la) ** 2 + (lng - ln) ** 2
            if dist < best_dist:
                best_dist = dist
                best_region = reg
        return best_region


VALID_CATEGORIES = {
    'shooting', 'murder', 'robbery', 'assault', 'kidnapping', 'violent_crime',
    'traffic_accident', 'vehicle_collision', 'pedestrian_accident', 'fire',
    'flood', 'natural_disaster', 'police_activity', 'drug_related',
    'domestic_violence', 'fraud', 'other',
}

# Override rules: if incident_type contains these words, force a category
# regardless of what the AI returned as category (fixes common AI mistakes)
INCIDENT_TYPE_OVERRIDES = [
    (['stolen', 'theft', 'larceny', 'robbed', 'robbery', 'burglary', 'break-in', 'carjacking', 'heist'], 'robbery'),
    (['drowning', 'drowned'], 'other'),
    (['electrocution', 'electrocuted'], 'other'),
]


def classify_category(raw_category: str, raw_incident_type: str = '') -> str:
    """Map raw AI output to a standardized category.

    First checks if raw_category is already a valid choice. Then applies
    override rules based on incident_type to fix common AI misclassifications
    (e.g. stolen vehicle → robbery, not vehicle_collision).
    """
    if not raw_category and not raw_incident_type:
        return 'other'

    type_lower = raw_incident_type.lower().strip() if raw_incident_type else ''
    cat_lower = raw_category.lower().strip() if raw_category else ''

    # Override: incident_type keywords take priority to fix misclassifications
    for keywords, forced_category in INCIDENT_TYPE_OVERRIDES:
        for kw in keywords:
            if kw in type_lower:
                return forced_category

    # If the AI returned a valid category directly, use it
    if cat_lower in VALID_CATEGORIES:
        return cat_lower

    # Try exact match in CATEGORY_MAP
    if cat_lower in CATEGORY_MAP:
        return CATEGORY_MAP[cat_lower]

    # Keyword match in the raw category string
    for keyword, category in CATEGORY_MAP.items():
        if keyword in cat_lower:
            return category

    # Fall back to incident_type keyword match
    if type_lower:
        if type_lower in CATEGORY_MAP:
            return CATEGORY_MAP[type_lower]
        for keyword, category in CATEGORY_MAP.items():
            if keyword in type_lower:
                return category

    return 'other'


def _description_word_overlap(desc1: str, desc2: str, threshold: float = 0.5) -> float:
    """Return word overlap ratio (Jaccard-like). Words are lowercased, non-alpha stripped."""
    if not desc1 or not desc2:
        return 0.0
    words1 = set(re.findall(r'[a-z0-9]+', desc1.lower()))
    words2 = set(re.findall(r'[a-z0-9]+', desc2.lower()))
    if not words1 or not words2:
        return 0.0
    inter = len(words1 & words2)
    union = len(words1 | words2)
    return inter / union if union else 0.0


class IncidentProcessorService:
    """Orchestrate the full AI extraction → geocoding → save pipeline."""

    def __init__(self, log_fn=None):
        self.extractor = OllamaExtractor()
        self.geocoder = GeocodingService()
        self.log_fn = log_fn

    def _log(self, message, level='info'):
        if self.log_fn:
            self.log_fn(message, level)

    def _find_matching_incident(
        self,
        category: str,
        incident_date,
        region: str,
        lat,
        lng,
        description: str,
    ):
        """Find an existing incident that likely describes the same event. Returns Incident or None."""
        from django.db.models import Q
        date_lo = incident_date - timedelta(days=3)
        date_hi = incident_date + timedelta(days=3)
        qs = Incident.objects.filter(
            category=category,
            incident_date__date__gte=date_lo.date(),
            incident_date__date__lte=date_hi.date(),
            region=region,
        )
        for inc in qs[:50]:
            if _description_word_overlap(description, inc.description or '') >= 0.5:
                if lat is not None and lng is not None and inc.latitude is not None and inc.longitude is not None:
                    if abs(lat - inc.latitude) > 0.02 or abs(lng - inc.longitude) > 0.02:
                        continue
                return inc
            elif lat is not None and lng is not None and inc.latitude is not None and inc.longitude is not None:
                if abs(lat - inc.latitude) <= 0.02 and abs(lng - inc.longitude) <= 0.02 and _description_word_overlap(description, inc.description or '') >= 0.3:
                    return inc
        return None

    def process_unprocessed_articles(self, limit: int = 50) -> int:
        """Process all unprocessed articles. Returns count of incidents created."""
        articles = list(Article.objects.filter(is_processed=False)[:limit])
        total_incidents = 0
        total_no_content = 0
        total_ai_failed = 0
        pipeline_start = time.time()

        if not articles:
            self._log('⚠️ No unprocessed articles to extract from', 'warning')
            return 0

        self._log(f'🚀 Starting AI extraction on {len(articles)} article(s)', 'info')

        for i, article in enumerate(articles):
            article_start = time.time()
            source_name = article.source.name if article.source else 'Unknown'
            title_short = article.title[:70]

            self._log(
                f'━━━ [{i+1}/{len(articles)}] "{title_short}..." ({source_name}) ━━━',
                'info'
            )

            if not article.content or len(article.content.strip()) < 50:
                self._log(f'    ⚠️ Content too short ({len(article.content or "")} chars) — skipping', 'warning')
                total_no_content += 1
                article.processing_error = 'Content too short for analysis'
                article.save(update_fields=['processing_error'])
                continue

            try:
                count = self._process_single_article(article)
            except Exception as e:
                total_ai_failed += 1
                err_msg = str(e)[:500]
                self._log(f'    ❌ AI failed: {err_msg}', 'error')
                article.processing_error = err_msg
                article.save(update_fields=['processing_error'])
                continue

            article_elapsed = time.time() - article_start
            total_incidents += count
            article.processing_error = ''
            article.is_processed = True
            article.save(update_fields=['processing_error', 'is_processed'])

            if count > 0:
                self._log(f'    ✅ Created {count} incident(s) ({article_elapsed:.1f}s)', 'success')
            else:
                self._log(f'    ○ No incidents from this article ({article_elapsed:.1f}s)', 'info')

        total_elapsed = time.time() - pipeline_start
        self._log(
            f'🏁 Extraction complete in {total_elapsed:.1f}s — '
            f'{total_incidents} incident(s) from {len(articles)} article(s), '
            f'{total_no_content} skipped (no content), {total_ai_failed} AI failures',
            'success' if total_incidents else 'warning'
        )

        # Run story clustering on recently processed articles
        try:
            from articles.clustering import cluster_stories
            clustered = cluster_stories(window_days=7, min_overlap=0.4, log_fn=self.log_fn)
            if clustered:
                self._log(f'📚 Story clustering: {clustered} article(s) assigned to stories', 'info')
        except Exception as e:
            logger.warning(f'Story clustering failed: {e}')
            if self.log_fn:
                self.log_fn(f'    ⚠️ Story clustering skipped: {e}', 'warning')

        logger.info(
            f"Processed {len(articles)} articles → {total_incidents} incidents in {total_elapsed:.1f}s"
        )
        return total_incidents

    def _process_single_article(self, article: Article) -> int:
        """Extract incidents from a single article."""
        raw_incidents = self.extractor.extract_incidents(article, log_fn=self.log_fn)
        count = 0

        for raw in raw_incidents:
            try:
                ai_location = raw.get('location', '')
                ai_city = raw.get('city', '')
                ai_region = raw.get('region', '')

                # Geocode with full chain: Photon -> Nominatim -> Dictionary
                geo = self.geocoder.geocode(
                    ai_location, ai_city, ai_region,
                    log_fn=self.log_fn,
                )

                # Parse AI-extracted date (stored separately for analysis)
                ai_incident_date = None
                raw_date = raw.get('date', '')
                if raw_date:
                    try:
                        ai_incident_date = parse_datetime(raw_date)
                        if ai_incident_date and timezone.is_naive(ai_incident_date):
                            ai_incident_date = timezone.make_aware(ai_incident_date)
                    except (ValueError, TypeError):
                        pass

                # incident_date ALWAYS comes from the article for reliability
                incident_date = article.published_date or timezone.now()

                category = classify_category(
                    raw.get('category', ''),
                    raw.get('incident_type', ''),
                )

                severity = raw.get('severity', 'medium')
                if severity not in ('low', 'medium', 'high', 'critical'):
                    severity = 'medium'

                confidence = float(raw.get('confidence', 50))
                confidence = max(0, min(100, confidence))

                # Build enriched description
                desc = raw.get('description', '')
                enrichment_parts = []
                if raw.get('victim_count') and int(raw.get('victim_count', 0)) > 0:
                    enrichment_parts.append(f"Victims: {raw['victim_count']}")
                if raw.get('fatality_count') and int(raw.get('fatality_count', 0)) > 0:
                    enrichment_parts.append(f"Fatalities: {raw['fatality_count']}")
                if raw.get('weapon'):
                    enrichment_parts.append(f"Weapon: {raw['weapon']}")
                if raw.get('suspect_description'):
                    enrichment_parts.append(f"Suspects: {raw['suspect_description']}")
                if raw.get('vehicle_info'):
                    enrichment_parts.append(f"Vehicle: {raw['vehicle_info']}")
                if raw.get('time'):
                    enrichment_parts.append(f"Time: {raw['time']}")
                if enrichment_parts:
                    desc = f"{desc}\n[{' | '.join(enrichment_parts)}]"

                victim_count = 0
                try:
                    victim_count = int(raw.get('victim_count', 0))
                except (ValueError, TypeError):
                    pass

                fatality_count = 0
                try:
                    fatality_count = int(raw.get('fatality_count', 0))
                except (ValueError, TypeError):
                    pass

                injured_count = 0
                try:
                    injured_count = int(raw.get('injured_count', 0))
                except (ValueError, TypeError):
                    pass

                value_stolen = None
                if raw.get('value_stolen') is not None:
                    try:
                        value_stolen = float(raw.get('value_stolen'))
                    except (ValueError, TypeError):
                        pass

                premises_type = str(raw.get('premises_type', ''))[:50].strip()
                motive = str(raw.get('motive', ''))[:100].strip()
                is_resolved = bool(raw.get('is_resolved', False))

                # Filter out non-TT incidents (lat/lng outside bounding box)
                TT_LAT_RANGE = (9.8, 11.5)
                TT_LNG_RANGE = (-62.1, -60.0)
                if geo['latitude'] is not None and geo['longitude'] is not None:
                    if not (TT_LAT_RANGE[0] <= geo['latitude'] <= TT_LAT_RANGE[1]
                            and TT_LNG_RANGE[0] <= geo['longitude'] <= TT_LNG_RANGE[1]):
                        self._log(
                            f'    ⏭️ Skipping: "{ai_location}" is outside Trinidad & Tobago bounds '
                            f'({geo["latitude"]:.4f}, {geo["longitude"]:.4f})',
                            'warning'
                        )
                        continue

                # Dedup: try to link to an existing incident (same category, date window, region, similar description)
                match = self._find_matching_incident(
                    category=category,
                    incident_date=incident_date,
                    region=geo['region'],
                    lat=geo['latitude'],
                    lng=geo['longitude'],
                    description=desc[:500],
                )
                if match:
                    match.related_articles.add(article)
                    count += 1
                    self._log(
                        f'    🔗 Linked to existing incident #{match.pk}: {match.incident_type} @ {ai_location or "?"}',
                        'success'
                    )
                    continue

                incident = Incident.objects.create(
                    incident_type=raw.get('incident_type', 'Unknown')[:100],
                    category=category,
                    description=desc[:2000],
                    severity=severity,
                    location_name=ai_location[:300],
                    ai_location_raw=ai_location[:500],
                    ai_city=ai_city[:200],
                    latitude=geo['latitude'],
                    longitude=geo['longitude'],
                    region=geo['region'],
                    incident_date=incident_date,
                    ai_incident_date=ai_incident_date,
                    incident_time=str(raw.get('time', ''))[:10],
                    confidence_score=confidence,
                    victim_count=victim_count,
                    fatality_count=fatality_count,
                    injured_count=injured_count,
                    value_stolen=value_stolen,
                    premises_type=premises_type,
                    motive=motive,
                    is_resolved=is_resolved,
                    weapon=str(raw.get('weapon', ''))[:100],
                    suspect_description=str(raw.get('suspect_description', ''))[:500],
                    vehicle_info=str(raw.get('vehicle_info', ''))[:300],
                    status='approved' if confidence >= 40 else 'pending',
                    primary_article=article,
                )
                incident.related_articles.add(article)

                # Create Person records (victims, suspects, witnesses, arrested)
                for p in raw.get('persons') or []:
                    if not isinstance(p, dict):
                        continue
                    role = (p.get('role') or 'victim').lower().strip()
                    if role not in ('victim', 'suspect', 'witness', 'arrested'):
                        role = 'victim'
                    gender = (p.get('gender') or 'unknown').lower().strip()
                    if gender not in ('male', 'female', 'unknown'):
                        gender = 'unknown'
                    condition = (p.get('condition') or 'unknown').lower().strip()
                    if condition not in ('uninjured', 'injured', 'hospitalized', 'deceased', 'unknown'):
                        condition = 'unknown'
                    try:
                        age = int(p['age']) if p.get('age') is not None else None
                    except (ValueError, TypeError):
                        age = None
                    Person.objects.create(
                        incident=incident,
                        role=role,
                        name=str(p.get('name', ''))[:300].strip(),
                        age=age,
                        gender=gender,
                        condition=condition,
                        description=str(p.get('description', ''))[:2000].strip(),
                        address=str(p.get('address', ''))[:500].strip(),
                        occupation=str(p.get('occupation', ''))[:200].strip(),
                    )

                count += 1

                self._log(
                    f'    💾 Saved: {incident.incident_type} @ {ai_location or "?"}'
                    f' [{incident.severity.upper()}] conf={confidence:.0f}%'
                    f' status={incident.status}',
                    'success'
                )

            except Exception as e:
                logger.error(f"Error creating incident from article {article.id}: {e}")
                self._log(f'    ❌ Save failed: {type(e).__name__}: {e}', 'error')

        return count
