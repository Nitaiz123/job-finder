"""
Bootstrap companies.json from public sources.

Pulls from Simplify's New-Grad-Positions and Summer-Internships GitHub repos
(README.md files contain markdown tables with company names + application URLs).
Extracts ATS slugs from the URLs.

Also merges in a curated seed list of well-known tech companies on each ATS
so the tool works even if the upstream repos change format.

Run once, or weekly to refresh. Idempotent.
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from config import USER_AGENT, REQUEST_TIMEOUT

OUT_PATH = Path(__file__).parent / "companies.json"

SIMPLIFY_README_URLS = [
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/README.md",
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/master/README.md",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2025-Internships/dev/README.md",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md",
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2025-Internships/master/README.md",
]

# Regex patterns for each ATS's canonical URL format
ATS_PATTERNS = {
    "greenhouse": [
        re.compile(r"boards\.greenhouse\.io/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE),
        re.compile(r"job-boards\.greenhouse\.io/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE),
        re.compile(r"boards\.eu\.greenhouse\.io/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE),
    ],
    "lever": [
        re.compile(r"jobs\.lever\.co/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE),
    ],
    "ashby": [
        re.compile(r"jobs\.ashbyhq\.com/([a-z0-9][a-z0-9\-\.]*)", re.IGNORECASE),
        re.compile(r"ashbyhq\.com/([a-z0-9][a-z0-9\-\.]*)", re.IGNORECASE),
    ],
    "workable": [
        re.compile(r"apply\.workable\.com/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE),
        # Second pattern: company.workable.com but NOT apply.workable.com
        re.compile(r"(?<![a-z])(?!apply\.)([a-z0-9][a-z0-9\-]+)\.workable\.com", re.IGNORECASE),
    ],
    "recruitee": [
        re.compile(r"([a-z0-9][a-z0-9\-]*)\.recruitee\.com", re.IGNORECASE),
    ],
    # Workday: captures (tenant, wdN, site) from URLs like:
    #   https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/...
    #   https://salesforce.wd1.myworkdayjobs.com/External_Career_Site/...
    "workday": [
        re.compile(
            r"([a-z0-9][a-z0-9\-]*)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-zA-Z\-_]+/)?([A-Za-z0-9_\-]+)",
            re.IGNORECASE,
        ),
    ],
    # Amazon: amazon.jobs URLs
    # (not URL-extractable from repos; handled via sentinel slug in CURATED_SEED)
    # Apple: jobs.apple.com URLs
    # (not URL-extractable from repos; handled via sentinel slug in CURATED_SEED)
    # Eightfold: captures company from URLs like https://capitalone.eightfold.ai/careers
    "eightfold": [
        re.compile(r"([a-z0-9][a-z0-9\-]*)\.eightfold\.ai", re.IGNORECASE),
    ],
    # iCIMS: careers-{slug}.icims.com or {slug}.icims.com. Capture the slug,
    # normalizing the careers- prefix so we don't store both forms.
    "icims": [
        re.compile(r"careers-([a-z0-9][a-z0-9\-]*)\.icims\.com", re.IGNORECASE),
        re.compile(r"(?<![a-z\-])([a-z0-9][a-z0-9\-]+)\.icims\.com", re.IGNORECASE),
    ],
}

# Curated seed list of well-known tech companies on each ATS.
# These are the slugs you'd use in the API URL (e.g. boards-api.greenhouse.io/v1/boards/<slug>/jobs).
# Hand-collected from public career pages; safe to extend.
CURATED_SEED = {
    "greenhouse": [
        # --- Verified top tech companies (confirmed via API) ---
        "block",         # Block Inc. (Square/Cash App) - 194 jobs
        "spacex",        # SpaceX - 1674 jobs
        "roblox",        # Roblox - 260 jobs
        "epicgames",     # Epic Games - 114 jobs
        # --- Core tech companies ---
        "airbnb", "stripe", "doordash", "instacart", "robinhood", "coinbase", "discord", "dropbox",
        "figma", "notion", "linear", "vercel", "openai", "anthropic", "scale", "rippling",
        "ramp", "brex", "mercury", "plaid", "checkr", "cloudflare", "datadog", "elastic",
        "mongodb", "hashicorp", "pagerduty", "twilio", "okta", "snyk", "auth0", "github",
        "gitlab", "atlassian", "asana", "monday", "miro", "calendly", "intercom",
        "zendesk", "freshworks", "samsara", "deel", "remote", "gusto", "carta", "wealthfront",
        "betterment", "chime", "affirm", "klarna", "marqeta", "wise", "revolut",
        "lyft", "uber", "instacart", "gopuff", "drizly", "blueapron", "wayfair",
        "etsy", "shopify", "squarespace", "wix", "zapier", "loom", "frame", "pinterest",
        "reddit", "medium", "substack", "patreon", "spotify", "soundcloud", "audible",
        "duolingo", "khanacademy", "coursera", "udemy", "masterclass", "chegg",
        "peloton", "wahoofitness", "mirror", "tonal", "whoop", "ouraring",
        "warbyparker", "allbirds", "casper", "purple", "tuftandneedle",
        "openai", "anthropic", "cohere", "huggingface", "weightsandbiases", "modal",
        "replicate", "runway", "midjourney", "characterai", "perplexity", "you",
        "snowflake", "databricks", "confluent", "starburst", "fivetran", "dbt",
        "airbyte", "rudderstack", "segment", "amplitude", "mixpanel", "fullstory",
        "heap", "rudder", "split", "launchdarkly", "statsig", "growthbook",
        "vercel", "netlify", "render", "fly", "supabase", "neon", "planetscale",
        "cockroachlabs", "yugabyte", "pinecone", "weaviate", "qdrant", "chroma",
        "sourcegraph", "tabnine", "codeium", "cursor", "warp", "fig",
        "meta", "facebook",  # Meta uses Greenhouse for many engineering roles
        "retool", "appsmith", "airplane", "windmill", "n8n", "make",
        "lattice", "culture-amp", "15five", "betterup", "modernhealth", "lyrahealth",
        "headspace", "calm", "hims", "ro", "hers", "noom",
        "doordash", "uber", "instacart", "shipt", "postmates", "grubhub",
        "boltfinancial", "fastly", "imply", "rockset", "materialize", "tecton",
        "iterable", "klaviyo", "mailgun", "sendgrid", "postmark", "courier",
        "front", "missiveapp", "spike", "superhuman", "hey",
        # EU / UK / Canada companies on Greenhouse
        "wise", "monzo", "revolut", "gocardless", "checkout", "thoughtmachine",
        "deliveroo", "wayve", "improbable", "darktrace", "graphcore",
        "snyk", "elastic", "spotify", "klarna", "northvolt", "kry",
        "tractable", "synthesia", "tessian", "cleo", "starlingbank",
        "multiverse", "beamery", "onfido", "quantexa", "paddle",
        "shopify", "wealthsimple", "clio", "1password", "faire", "ada",
        "cohere", "benchsci", "wattpad", "hootsuite", "lightspeed",
        " apryse", "ssense", "coveo", "dialpad", "vidyard",
        "celonis", "personio", "contentful", "n26", "getyourguide",
        "trade-republic", "pennylane", "qonto", "alan", "swile",
        "datadog", "miro", "pigment", "payfit", "ledger", "sorare",
        "back-market", "mirakl", "aircall", "spendesk", "contentsquare",
        # --- Additional verified Greenhouse companies ---
        "waymo",         # Waymo (Alphabet) - 418 jobs
        "databricks",    # Databricks - 765 jobs
        "anthropic",     # Anthropic - 376 jobs (also in ashby, greenhouse is primary)
        "lyft",          # Lyft - 124 jobs
        "pinterest",     # Pinterest - 176 jobs
        "reddit",        # Reddit - 156 jobs
        "cloudflare",    # Cloudflare - 149 jobs
        "figma",         # Figma - 159 jobs
        "okta",          # Okta - 354 jobs
        "mongodb",       # MongoDB - 427 jobs
        "datadog",       # Datadog - 424 jobs
        "stripe",        # Stripe - 475 jobs
        "airbnb",        # Airbnb - 236 jobs
        "brex",          # Brex - 223 jobs
        "instacart",     # Instacart - 136 jobs
        "robinhood",     # Robinhood - 129 jobs
        "discord",       # Discord - 74 jobs
        "duolingo",      # Duolingo - 65 jobs
        "fastly",        # Fastly - 55 jobs
        "pagerduty",     # PagerDuty - 41 jobs
        "airtable",      # Airtable - 26 jobs
        "lattice",       # Lattice - 13 jobs
        "coursera",      # Coursera - 11 jobs
        "gusto",         # Gusto - 84 jobs
        # --- More verified Greenhouse companies ---
        "betterhelp",    # BetterHelp - 257 jobs
        "affirm",        # Affirm - 168 jobs
        "scaleai",       # Scale AI - 167 jobs
        "elastic",       # Elastic - 159 jobs
        "intercom",      # Intercom - 152 jobs
        "sofi",          # SoFi - 146 jobs
        "twilio",        # Twilio - 145 jobs
        "fivetran",      # Fivetran - 137 jobs
        "oura",          # Oura Ring - 107 jobs
        "justworks",     # Justworks - 95 jobs
        "vercel",        # Vercel - 74 jobs
        "chime",         # Chime - 69 jobs
        "checkr",        # Checkr - 62 jobs
        "dropbox",       # Dropbox - 61 jobs
        "peloton",       # Peloton - 61 jobs
        "amplitude",     # Amplitude - 51 jobs
        "carta",         # Carta - 51 jobs
        "launchdarkly",  # LaunchDarkly - 50 jobs
        "mixpanel",      # Mixpanel - 45 jobs
        "cockroachlabs", # CockroachDB - 33 jobs
        "khanacademy",   # Khan Academy - 33 jobs
        "yugabyte",      # YugabyteDB - 32 jobs
        "betterment",    # Betterment - 31 jobs
        "squarespace",   # Squarespace - 27 jobs
        "marqeta",       # Marqeta - 39 jobs
        "modernhealth",  # Modern Health - 12 jobs
        "masterclass",   # MasterClass - 4 jobs
        # --- Media, News & Entertainment companies (verified) ---
        # News & Media
        "thenewyorktimes",  # The New York Times - 177 jobs
        "axios",            # Axios - 24 jobs
        "voxmedia",         # Vox Media - 17 jobs
        "forbes",           # Forbes - 19 jobs
        "insider",          # Business Insider - 11 jobs
        "propublica",       # ProPublica - 4 jobs
        "buzzfeed",         # BuzzFeed - 7 jobs
        "rumble",           # Rumble - 16 jobs
        "abc",              # ABC News - 24 jobs
        "fox",              # Fox Corporation - 7 jobs
        # Entertainment & Streaming
        "a24",              # A24 Films - 8 jobs
        "twitch",           # Twitch (Amazon) - 58 jobs
        "crunchyroll",      # Crunchyroll - 65 jobs
        # Sports & Gaming
        "fanduel",          # FanDuel - 126 jobs
        "barstoolsports",   # Barstool Sports - 2 jobs
        # Gaming
        "riotgames",        # Riot Games (LoL, Valorant) - 186 jobs
        "scopely",          # Scopely - 198 jobs
        "2k",               # 2K Games - 109 jobs
        "rockstargames",    # Rockstar Games (GTA) - 84 jobs
        "taketwo",          # Take-Two Interactive - 32 jobs
        "naughtydog",       # Naughty Dog (PlayStation) - 10 jobs
        "insomniac",        # Insomniac Games (Spider-Man) - 3 jobs
        "bungie",           # Bungie (Destiny) - 1 job

        # --- Sector expansion: Finance & Fintech (verified) ---
        "adyen",         # Adyen - 213 jobs
        "sezzle",        # Sezzle - 207 jobs
        "ripple",        # Ripple (XRP) - 127 jobs
        "nubank",        # Nubank - 105 jobs
        "gemini",        # Gemini (crypto) - 27 jobs
        "pandadoc",      # PandaDoc - 48 jobs
        "blend",         # Blend (mortgage tech) - 5 jobs
        "brex",          # Brex - 227 jobs
        "slice",         # Slice (pizza tech) - 75 jobs
        "shift4",        # Shift4 Payments - 71 jobs

        # --- Sector expansion: Healthcare & Biotech (verified) ---
        "natera",        # Natera (genetic testing) - 198 jobs
        "oscar",         # Oscar Health - 226 jobs
        "amwell",        # Amwell (telehealth) - 19 jobs
        "modernhealth",  # Modern Health - 11 jobs
        "10xgenomics",   # 10x Genomics - 35 jobs
        "solidpower",    # Solid Power (batteries) - 10 jobs
        "branch",        # Branch (insurance) - 8 jobs
        "cerebral",      # Cerebral (mental health) - 3 jobs
        "climateai",     # ClimateAI - 2 jobs
        "sunnova",       # Sunnova (solar) - 2 jobs
        "tomorrow",      # Tomorrow.io (weather AI) - 12 jobs

        # --- Sector expansion: Defense & Aerospace (verified) ---
        "rocketlab",     # Rocket Lab - 311 jobs
        "motional",      # Motional (AV) - 120 jobs
        "nuro",          # Nuro (delivery robots) - 108 jobs
        "kodiak",        # Kodiak Robotics - 58 jobs
        "wing",          # Wing (drone delivery) - 29 jobs
        "spire",         # Spire Global (satellites) - 45 jobs
        "supernal",      # Supernal (eVTOL) - 3 jobs
        "archer",        # Archer Aviation - 1 job

        # --- Sector expansion: Enterprise & SaaS (verified) ---
        "nice",          # NICE Systems - 358 jobs
        "purestorage",   # Pure Storage - 334 jobs
        "samsara",       # Samsara - 315 jobs
        "toast",         # Toast (restaurant tech) - 297 jobs
        "canonical",     # Canonical (Ubuntu) - 289 jobs
        "clickhouse",    # ClickHouse - 169 jobs
        "via",           # Via (transit) - 168 jobs
        "newrelic",      # New Relic - 72 jobs
        "zoominfo",      # ZoomInfo - 58 jobs
        "salesloft",     # Salesloft - 31 jobs
        "6sense",        # 6sense - 34 jobs
        "project44",     # project44 (logistics) - 33 jobs
        "starburst",     # Starburst (data) - 22 jobs
        "veracode",      # Veracode (security) - 20 jobs
        "imply",         # Imply (Druid) - 7 jobs
        "dremio",        # Dremio - 6 jobs
        "materialize",   # Materialize (streaming SQL) - 3 jobs
        "bombora",       # Bombora (B2B intent) - 1 job

        # --- Sector expansion: Transportation & Logistics (verified) ---
        "bird",          # Bird (scooters) - 41 jobs
        "spin",          # Spin (scooters) - 23 jobs
        "vacasa",        # Vacasa (vacation rentals) - 47 jobs
        "shipmonk",      # ShipMonk (fulfillment) - 41 jobs
        "fourkites",     # FourKites (supply chain) - 8 jobs
        "motive",        # Motive (fleet) - 4 jobs
        "netradyne",     # Netradyne (fleet safety) - 65 jobs
        "nauto",         # Nauto (fleet AI) - 4 jobs
        "loadsmart",     # Loadsmart - 17 jobs (also Lever)

        # --- Sector expansion: Travel & Hospitality (verified) ---
        "tripadvisor",   # TripAdvisor - 94 jobs
        "skyscanner",    # Skyscanner - 23 jobs
        "kayak",         # KAYAK - 1 job

        # --- Sector expansion: Food & Restaurant Tech (verified) ---
        "sweetgreen",    # Sweetgreen - 52 jobs
        "touchbistro",   # TouchBistro - 5 jobs
        "papa",          # Papa (elder care) - 4 jobs

        # --- Sector expansion: Real Estate & Proptech (verified) ---
        "orchard",       # Orchard (home buying) - 72 jobs
        "crexi",         # Crexi (commercial RE) - 15 jobs
        "hover",         # Hover (3D home imaging) - 24 jobs
        "knock",         # Knock (home trade-in) - 4 jobs
        "homeward",      # Homeward - 2 jobs
        "convene",       # Convene (flex office) - 35 jobs

        # --- Sector expansion: Education & Edtech (verified) ---
        "d2l",           # D2L (Brightspace LMS) - 31 jobs
        "generalassembly", # General Assembly - 28 jobs
        "newsela",       # Newsela - 16 jobs
        "udacity",       # Udacity - 14 jobs
        "udemy",         # Udemy - 7 jobs
        "springboard",   # Springboard - 6 jobs

        # --- Sector expansion: Legal Tech (verified) ---
        "litify",        # Litify (legal CRM) - 8 jobs

        # --- Sector expansion: Insurance & Insurtech (verified) ---
        "openly",        # Openly (home insurance) - 6 jobs

        # --- Sector expansion: Other (verified) ---
        "virtu",         # Virtu Financial (HFT) - 37 jobs
        "jumptrading",   # Jump Trading (quant) - 68 jobs
        "tcs",           # Tata Consultancy Services - 71 jobs
        "array",         # Array (solar tracking) - 17 jobs
        "offerup",       # OfferUp (marketplace) - 4 jobs
        "mercari",       # Mercari (marketplace) - 3 jobs
        "disney",        # Disney (some roles on GH) - 1 job
        "figment",       # Figment (crypto staking) - 1 job
        "shield",        # Shield AI (defense) - 1 job
        "calm",          # Calm (meditation) - 1 job
        "revel",         # Revel Systems (POS) - 1 job

        # --- Newly verified Greenhouse companies (Jun 2026) ---
        # Finance & Trading
        "janestreet",    # Jane Street (quant trading) - 204 jobs
        "zscaler",       # Zscaler (cloud security) - 329 jobs
        "relativity",   # Relativity Space (rockets) - 291 jobs
        "braze",         # Braze (marketing automation) - 194 jobs
        "workato",       # Workato (automation) - 177 jobs
        "sofi",          # SoFi (neobank) - 135 jobs
        "vonage",        # Vonage (CPaaS) - 52 jobs
        "bandwidth",     # Bandwidth (comms API) - 31 jobs
        "sendbird",      # Sendbird (chat API) - 16 jobs
        "neo4j",         # Neo4j (graph DB) - 39 jobs
        "tigergraph",    # TigerGraph (graph analytics) - 2 jobs
        "sisense",       # Sisense (BI) - 12 jobs
        "newrelic",      # New Relic (observability) - 72 jobs
        "comet",         # Comet (ML experiment tracking) - 6 jobs
        "deepmind",      # Google DeepMind - 47 jobs
        "tcs",           # Tata Consultancy Services - 71 jobs
        "flexport",      # Flexport (logistics) - 100 jobs
        "openspace",     # OpenSpace (construction AI) - 12 jobs
        "coalition",     # Coalition (cyber insurance) - 28 jobs
        "costar",        # CoStar (real estate data) - 3 jobs
        "2u",            # 2U (online education) - 23 jobs
        "greenhouse",    # Greenhouse (ATS company itself) - 22 jobs
        "typeform",      # Typeform (forms) - 19 jobs
        "salesloft",     # Salesloft (sales engagement) - 31 jobs
        "zoominfo",      # ZoomInfo (B2B data) - 58 jobs
        "pandadoc",      # PandaDoc (document automation) - 48 jobs
        "project44",     # project44 (supply chain visibility) - 33 jobs
        "shipmonk",      # ShipMonk (fulfillment) - 41 jobs
        "bringg",        # Bringg (delivery orchestration) - 5 jobs
        "motive",        # Motive (fleet management) - 4 jobs
        "fourkites",     # FourKites (supply chain) - 8 jobs
        "sweetgreen",    # Sweetgreen (restaurant) - 53 jobs
        "tripadvisor",   # TripAdvisor (travel) - 94 jobs
        "spin",          # Spin (scooters) - 23 jobs
        "indigo",        # Indigo Agriculture - 2 jobs
        "branch",        # Branch (insurance) - 8 jobs
        "hover",         # Hover (3D imaging) - 23 jobs
        "d2l",           # D2L (Brightspace LMS) - 31 jobs
        "airtable",      # Airtable (no-code DB) - 26 jobs
        "riotgames",     # Riot Games - 188 jobs
        "2k",            # 2K Games - 115 jobs
        "epicgames",     # Epic Games - 136 jobs
        "bungie",        # Bungie (Destiny) - 1 job
        "naughtydog",    # Naughty Dog (PlayStation) - 13 jobs
        "insomniac",     # Insomniac Games - 3 jobs
        "roblox",        # Roblox - 234 jobs
        "a24",           # A24 Films - 8 jobs
        "axios",         # Axios (news) - 23 jobs
        "buzzfeed",      # BuzzFeed - 7 jobs
        "disney",        # Disney - 1 job
        "spire",         # Spire Global (satellites) - 45 jobs
        "relativity",    # Relativity Space - 291 jobs
        "motional",      # Motional (AV) - 120 jobs
        "nuro",          # Nuro (delivery robots) - 107 jobs
        "bird",          # Bird (scooters) - 41 jobs
        "vacasa",        # Vacasa (vacation rentals) - 47 jobs
        "nubank",        # Nubank (neobank Brazil) - 105 jobs
        "adyen",         # Adyen (payments) - 213 jobs
        "10xgenomics",   # 10x Genomics - 35 jobs
        "oscar",         # Oscar Health - 230 jobs
        "sunnova",       # Sunnova (solar) - 2 jobs

        # --- Newly verified Greenhouse companies (Jul 2026) ---
        # Cybersecurity & Identity
        "rubrik",        # Rubrik (data security) - 103 jobs
        "beyondtrust",   # BeyondTrust (privileged access) - 48 jobs
        "druva",         # Druva (cloud data protection) - 31 jobs
        "yubico",        # Yubico (hardware security keys) - 16 jobs
        "godaddy",       # GoDaddy (domain/hosting) - 31 jobs
        "orca",          # Orca Security (cloud security) - 1 job
        # Data & Analytics
        "collibra",      # Collibra (data governance) - 40 jobs
        "backblaze",     # Backblaze (cloud storage) - 40 jobs
        # Finance & Trading
        "carvana",       # Carvana (used cars) - 1905 jobs
        "imc",           # IMC Trading (quant) - 153 jobs
        "aqr",           # AQR Capital Management - 46 jobs
        "bitgo",         # BitGo (crypto custody) - 39 jobs
        "fireblocks",    # Fireblocks (crypto infra) - 64 jobs
        # Enterprise SaaS
        "netskope",      # Netskope (cloud security) - 141 jobs
        "smartsheet",    # Smartsheet (work management) - 100 jobs
        "digicert",      # DigiCert (PKI/TLS) - 57 jobs
        "qualtrics",     # Qualtrics (experience mgmt) - 53 jobs
        "algolia",       # Algolia (search API) - 49 jobs
        "sumologic",     # Sumo Logic (log analytics) - 19 jobs
        "assemblyai",    # AssemblyAI (speech AI) - 10 jobs
        "circleci",      # CircleCI (CI/CD) - 8 jobs
        "cybereason",    # Cybereason (endpoint security) - 8 jobs
        # Gaming & Entertainment
        "nintendo",      # Nintendo of America - 50 jobs
        "bethesda",      # Bethesda Softworks - 2 jobs
        # Other
        "linkedin",      # LinkedIn (also Greenhouse) - 53 jobs
        "everlaw",       # Everlaw (legal tech) - 33 jobs
        "disco",         # DISCO (legal AI) - 31 jobs
        "glossier",      # Glossier (beauty) - 20 jobs
        "homelight",     # HomeLight (real estate) - 18 jobs
        "autotrader",    # AutoTrader (car marketplace) - 13 jobs
        "labelbox",      # Labelbox (data labeling) - 9 jobs
        "watershed",     # Watershed (carbon accounting) - 8 jobs
        "sas",           # SAS Institute (analytics) - 6 jobs
        "bcg",           # Boston Consulting Group - 4 jobs
        "binance",       # Binance (crypto exchange) - 1 job
        "eve",           # Eve Sleep (UK mattress) - 32 jobs
        "beam",          # Beam (benefits) - 9 jobs
    ],
    "lever": [
        # --- Verified Lever companies ---
        "palantir",      # Palantir - 5 jobs (verified)
        "linkedin",      # LinkedIn - 16 jobs (verified)
        # --- Media & Entertainment on Lever ---
        "spotify",       # Spotify - 183 jobs
        "theathletic",   # The Athletic (NYT) - 15 jobs
        "wmg",           # Warner Music Group - 23 jobs
        "slate",         # Slate Magazine - 4 jobs
        # --- Core Lever companies ---
        "netflix", "spotify", "kpler", "ramp", "attentive", "blend", "carta", "checkr",
        "clearbit", "color", "convoy", "cruise", "crunchbase", "discord", "doordash",
        "figma", "gem", "gusto", "highspot", "humu", "imply", "instabase", "kustomer",
        "lattice", "lever", "linktree", "modernhealth", "mux", "netlify", "nightfall",
        "notion", "outschool", "patreon", "plaid", "podium", "postman", "ramp",
        "ribbon", "scaleai", "shippo", "snyk", "tala", "tally", "thoughtworks",
        "thumbtack", "tiger-analytics", "tinybird", "turing", "uipath", "udemy",
        "verkada", "vouch", "warbyparker", "writer", "yotpo", "zipline", "zylo",
        "anduril", "applied-intuition", "cresta", "elementl", "fathomvideo",
        "fivetran", "glean", "groq", "huggingface", "humanloop", "mistralai",
        "modal", "openphone", "patreon", "perplexity-ai", "pinecone", "predibase",
        "replicate", "runway", "scale", "snorkelai", "together-ai", "weaviate",
        "weightsandbiases", "wove", "writer",
        # EU / UK / Canada on Lever
        "spotify", "wealthsimple", "hopper", "ada-support", "cohere",
        "faire", "dialpad", "vidyard", "thinkific", "trulioo",
        "deliveroo", "starlingbank", "tide", "bulb", "depop",
        "soundcloud", "babbel", "gympass", "wefox", "raisin",
        "mambu", "solarisbank", "moonpig", "secret-escapes",
        # --- Sector expansion: verified Lever companies ---
        "veeva",         # Veeva Systems - 1028 jobs
        "sila",          # Sila Nanotechnologies (batteries) - 283 jobs
        "filevine",      # Filevine (legal tech) - 134 jobs
        "ro",            # Ro (telehealth) - 53 jobs
        "outreach",      # Outreach (sales) - 34 jobs
        "olo",           # Olo (restaurant tech) - 14 jobs
        "chownow",       # ChowNow (restaurant tech) - 10 jobs
        "15five",        # 15Five (HR) - 4 jobs
        "relay",         # Relay (banking) - 3 jobs

        # --- Newly verified Lever companies (Jun 2026) ---
        "gopuff",        # GoPuff (instant delivery) - 802 jobs
        "shieldai",      # Shield AI (defense) - 333 jobs
        "farfetch",      # Farfetch (luxury fashion) - 62 jobs
        "contentsquare", # ContentSquare (analytics) - 40 jobs
        "outreach",      # Outreach (sales engagement) - 34 jobs
        "neon",          # Neon (serverless Postgres) - 15 jobs
        "wealthfront",   # Wealthfront (robo-advisor) - 13 jobs
        "brilliant",     # Brilliant (math/science learning) - 3 jobs
        "straighterline", # StraighterLine (online courses) - 2 jobs

        # --- Newly verified Lever companies (Jul 2026) ---
        "saviynt",       # Saviynt (identity security) - 117 jobs
        "acceldata",     # Acceldata (data observability) - 53 jobs
        "appen",         # Appen (AI training data) - 52 jobs
        "anchorage",     # Anchorage Digital (crypto) - 46 jobs
        "matillion",     # Matillion (data integration) - 19 jobs
        "pipedrive",     # Pipedrive (CRM) - 17 jobs
        "people-ai",     # People.ai (revenue AI) - 9 jobs
        "anomali",       # Anomali (threat intelligence) - 8 jobs
        "immutable",     # Immutable (Web3 gaming) - 3 jobs
        "topdesk",       # TOPdesk (ITSM) - 6 jobs
    ],
    "ashby": [
        # --- Verified Ashby companies (confirmed via API) ---
        "openai",        # OpenAI - 716 jobs
        "snowflake",     # Snowflake - 409 jobs
        "notion",        # Notion - 143 jobs
        "cohere",        # Cohere - 129 jobs
        "ramp",          # Ramp - 119 jobs
        "plaid",         # Plaid - 91 jobs
        "confluent",     # Confluent - 49 jobs
        "benchling",     # Benchling - 46 jobs
        "linear",        # Linear - 26 jobs
        "nerdwallet",    # NerdWallet - 25 jobs
        "strava",        # Strava - 25 jobs
        "airbyte",       # Airbyte - 8 jobs
        # --- Other Ashby companies ---
        "vercel", "deepgram", "anthropic", "scale",
        "modal", "replicate", "supabase", "neon", "planetscale", "fly", "render",
        "warp", "raycast", "arc", "tldraw", "cursor", "codeium", "tabnine",
        "perplexity", "you", "harvey", "ironclad", "evenup", "casetext",
        "watershed", "carbon-direct", "patch", "pachama", "stripe", "mercury",
        "wise", "revolut", "monzo", "starlingbank", "n26",
        "huggingface", "weights-biases", "modal-labs", "replicate-ai", "pinecone-io",
        "weaviate", "qdrant", "chroma-core", "cohere", "mistral", "groq", "together",
        "sambanova", "cerebras", "lambda", "coreweave", "runpod",
        "linear-app", "raycast-app", "warp-terminal", "fig-io",
        "anysphere", "sourcegraph", "supermaven", "augmentcode", "magic-dev",
        "decagon", "sierra-ai", "pylon", "kustomer", "frontapp",
        "rippling", "deel-com", "remote-com", "oysterhr", "remotebase",
        # --- Additional verified Ashby companies ---
        "cursor",        # Cursor AI - 86 jobs
        "perplexity",    # Perplexity AI - 60 jobs
        # --- Media on Ashby ---
        "slate",         # Slate Magazine - 7 jobs
        "take2",         # Take-Two Interactive - 5 jobs
        # --- Sector expansion: verified Ashby companies ---
        "airwallex",     # Airwallex (fintech) - 577 jobs
        "elevenlabs",    # ElevenLabs (voice AI) - 148 jobs
        "deepgram",      # Deepgram (speech AI) - 60 jobs
        "suno",          # Suno (music AI) - 43 jobs
        "relay",         # Relay.app (automation) - 37 jobs
        "modal",         # Modal (cloud compute) - 31 jobs
        "astronomer",    # Astronomer (Airflow) - 28 jobs
        "render",        # Render (cloud hosting) - 23 jobs
        "anyscale",      # Anyscale (Ray) - 11 jobs
        "column",        # Column (banking infra) - 11 jobs
        "novo",          # Novo (SMB banking) - 11 jobs
        "railway",       # Railway (cloud hosting) - 9 jobs
        "unit",          # Unit (embedded banking) - 9 jobs
        "clearco",       # Clearco (revenue-based financing) - 7 jobs
        "neon",          # Neon (serverless Postgres) - 7 jobs
        "aquant",        # Aquant (field service AI) - 5 jobs
        "griffin",       # Griffin (banking-as-a-service) - 5 jobs
        "pika",          # Pika (video AI) - 5 jobs
        "prefect",       # Prefect (data orchestration) - 4 jobs
        "runway",        # Runway (video AI) - 4 jobs
        "capchase",      # Capchase (revenue financing) - 3 jobs
        "conductor",     # Conductor (SEO) - 3 jobs
        "found",         # Found (SMB banking) - 3 jobs
        "datafold",      # Datafold (data quality) - 1 job
        "tekton",        # Tekton (CI/CD) - 1 job

        # --- Newly verified Ashby companies (Jul 2026) ---
        "clickhouse",    # ClickHouse (analytics DB) - 171 jobs
        "clickup",       # ClickUp (project mgmt) - 67 jobs
        "docker",        # Docker (containers) - 53 jobs
        "sentry",        # Sentry (error monitoring) - 48 jobs
        "amplitude",     # Amplitude (product analytics) - 46 jobs
        "miro",          # Miro (visual collaboration) - 43 jobs
        "n8n",           # n8n (workflow automation) - 37 jobs
        "elliptic",      # Elliptic (crypto compliance) - 33 jobs
        "redis",         # Redis (in-memory DB) - 28 jobs
        "midjourney",    # Midjourney (AI image gen) - 20 jobs
        "alchemy",       # Alchemy (Web3 infra) - 17 jobs
        "zapier",        # Zapier (automation) - 15 jobs
        "insitro",       # Insitro (ML drug discovery) - 13 jobs
        "mural",         # MURAL (visual collaboration) - 10 jobs
        "helpscout",     # Help Scout (customer support) - 9 jobs
        "atlan",         # Atlan (data workspace) - 5 jobs
        "lightspeed",    # Lightspeed (commerce) - 5 jobs
        "neptune",       # Neptune.ai (MLOps) - 4 jobs
        "materialize",   # Materialize (streaming SQL) - 4 jobs
        "chilipiper",    # Chili Piper (scheduling) - 3 jobs
        "windmill",      # Windmill (dev platform) - 3 jobs
        "flink",         # Flink (quick commerce) - 2 jobs
        "prometheus",    # Prometheus (monitoring) - 2 jobs
        "opensea",       # OpenSea (NFT marketplace) - 1 job
        "delinea",       # Delinea (privileged access) - 62 jobs
        "close",         # Close (CRM) - 7 jobs
        "orca",          # Orca Security (cloud security) - 1 job
    ],
    "workable": [
        "doctolib", "klarna", "back-market", "alan", "swile",
        "carwow", "trustpilot", "trainline", "babylonhealth", "babbel",
        "n26", "trivago", "kry", "kahoot", "blablacar", "vinted",
        "shopify-plus", "wolt", "bolt", "glovo", "deliveryhero",
        "celonis", "personio", "miro", "contentful", "typeform",
        "factorial", "spendesk", "qonto", "memorabledev",
        # More EU/UK Workable tenants (Workable is heavily European)
        "gymshark", "monzo", "starlingbank", "cleo", "tide", "curve",
        "bulb", "ovo", "depop", "moonpig", "bloomandwild", "cazoo",
        "secretescapes", "zego", "marshmallow", "habito", "primer",
        "yapily", "truelayer", "form3", "modulr", "gocardless",
        "freetrade", "moneybox", "wagestream", "lendable",
        "mews", "messagebird", "bird", "framer", "channable", "bunq",
        "adyen-careers", "mollie", "picnic", "catawiki", "wetransfer",
        " wefox", "raisin", "solarisbank", "getyourguide", "omio",
        "tier", "grover", "kontist", "pitch", "demodesk",
        "pipedrive", "bolt-eu", "wise-careers",
    ],
    "recruitee": [
        # --- Confirmed Recruitee companies (verified via API) ---
        "adjust",        # Adjust (mobile analytics) - 29 jobs
        "holded",        # Holded (Spanish ERP) - 11 jobs
        "personio",      # Personio (HR software) - 1 job
        # --- Additional Recruitee companies (European tech/SaaS) ---
        "teamviewer",    # TeamViewer (remote access)
        "rewe-digital",  # REWE Digital (German retail tech)
        "aboutyou",      # About You (fashion e-commerce)
        "flixbus",       # FlixBus (intercity bus)
        "idealo",        # Idealo (price comparison)
        "mytheresa",     # Mytheresa (luxury fashion)
        "searchie",      # Searchie (AI content)
        "babbel",        # Babbel (language learning)
        "ecosia",        # Ecosia (green search engine)
        "thermondo",     # Thermondo (heating tech)
        "raisin",        # Raisin (savings marketplace)
        "smava",         # Smava (loan comparison)
        "check24",       # Check24 (comparison portal)
        "homeday",       # Homeday (real estate)
        "clark",         # Clark (insurance)
        "getsafe",       # GetSafe (digital insurance)
        "wefox",         # Wefox (insurance)
        "simplesurance", # Simplesurance (insurance)
        "nuri",          # Nuri (crypto banking)
        "penta",         # Penta (business banking)
        "finiata",       # Finiata (SMB finance)
        "billie",        # Billie (B2B BNPL)
        "moss",          # Moss (expense management)
        "agicap",        # Agicap (cash flow)
        "candis",        # Candis (accounting)
        "spendesk",      # Spendesk (spend management)
        "gorillas",      # Gorillas (quick commerce)
        "flink",         # Flink (quick commerce)
        "relex",         # Relex Solutions (retail planning)
        "commercetools", # commercetools (headless commerce)
        "spryker",       # Spryker (e-commerce)
        "contentful",    # Contentful (CMS)
        "storyblok",     # Storyblok (headless CMS)
        "hygraph",       # Hygraph (GraphQL CMS)
        "sanity",        # Sanity (structured content)
        "prismic",       # Prismic (headless CMS)
        "sitecore",      # Sitecore (DXP)
        "magnolia",      # Magnolia (CMS)
        "kentico",       # Kentico (CMS)
        "bloomreach",    # Bloomreach (commerce)
        "emarsys",       # Emarsys (marketing)
        "braze",         # Braze (customer engagement)
        "insider",       # Insider (growth management)
        "webengage",     # WebEngage (marketing)
        "clevertap",     # CleverTap (analytics)
        "leanplum",      # Leanplum (mobile marketing)
        "airship",       # Airship (mobile engagement)
        "pushwoosh",     # Pushwoosh (push notifications)
        "onesignal",     # OneSignal (messaging)
        "sendbird",      # Sendbird (chat API)
        "stream",        # Stream (chat/feeds)
        "twilio-segment",# Twilio Segment (CDP)
        "mparticle",     # mParticle (CDP)
        "rudderstack",   # RudderStack (CDP)
        "hightouch",     # Hightouch (reverse ETL)
        "census",        # Census (reverse ETL)
        "fivetran",      # Fivetran (data integration)
        "airbyte",       # Airbyte (data integration)
        "stitch",        # Stitch (data pipeline)
        "matillion",     # Matillion (data integration)
        "talend",        # Talend (data integration)
        "informatica",   # Informatica (data management)
        "mulesoft",      # MuleSoft (integration)
        "boomi",         # Boomi (integration)
        "jitterbit",     # Jitterbit (integration)
        "workato",       # Workato (automation)
        "zapier",        # Zapier (automation)
        "make",          # Make (automation)
        "n8n",           # n8n (workflow automation)
        "activepieces",  # Activepieces (automation)
    ],
    # Workday seeds are 'tenant|wdN|site' triples. Verified from public career pages.
    # Add more as you discover them by visiting a company's "Careers" page and
    # looking at the URL once it redirects to *.myworkdayjobs.com.
    "workday": [
        # --- Verified Workday companies (confirmed via API) ---
        "nvidia|wd5|NVIDIAExternalCareerSite",  # NVIDIA - 1780 jobs
        "zoom|wd5|zoom",                         # Zoom - 124 jobs
        "intel|wd1|External",                    # Intel - 715 jobs
        # --- Other Workday companies ---
        "salesforce|wd1|External_Career_Site",
        "cisco|wd5|External",
        "adobe|wd5|external_experienced",
        "vmware|wd1|VMware",
        "intuit|wd12|IntuitCareers",
        "dell|wd1|External",
        "hpe|wd5|Jobsathpe",
        "hp|wd12|ExternalCareerSite",
        "ibm|wd1|IBM",
        "vmware|wd1|VMware_Careers",
        "workday|wd5|Workday",
        "paloaltonetworks|wd1|PaloAltoNetworks",
        "servicenow|wd1|ServiceNow",
        "splunk|wd1|splunk_careers",
        "boozallen|wd1|BAH_Careers_External",
        "accenture|wd103|AccentureCareers",
        "kpmg|wd5|KPMG_Careers",
        "deloitte|wd1|Deloitte_Careers",
        "ey|wd5|EYCareers",
        "pwc|wd3|Global_Experienced_Careers",
        "jpmorganchase|wd5|jpmc",
        "bankofamerica|wd1|Lateral-US",
        "wellsfargo|wd1|Wellsfargojobs",
        "capitalone|wd12|Capital_One",
        "americanexpress|wd1|jobs",
        "citi|wd5|2",
        "morganstanley|wd5|External",
        "goldmansachs|wd103|Apply",
        "visa|wd1|Visa_Careers",
        "mastercard|wd5|CorporateCareers",
        "paypal|wd1|jobs",
        "intuit|wd12|External",
        "walmart|wd5|WalmartExternal",
        "target|wd5|targetcareers",
        "costco|wd5|costcocareers",
        "homedepot|wd1|homedepot",
        "lowes|wd1|Lowes",
        "fedex|wd1|FXE",
        "ups|wd5|UPSJobs",
        "att|wd1|ATTEXTERNAL",
        "verizon|wd12|verizon",
        "tmobile|wd1|External",
        "comcast|wd5|Comcast_Careers",
        "disney|wd5|disneycareer",
        "warnerbros|wd5|global",
        "paramount|wd5|Paramount",
        "nbcuni|wd1|nbcunicareers",
        "ge|wd5|GE_ExternalSite",
        "boeing|wd1|EXTERNAL_CAREERS",
        "lockheedmartin|wd1|LMCareers",
        "raytheon|wd1|REC_RTX_ExtCareers",
        "northropgrumman|wd5|NGCareers",
        "honeywell|wd1|HONEYWELL",
        "3m|wd1|Search",
        "caterpillar|wd5|CaterpillarCareers",
        "johndeere|wd5|JohnDeere",
        "pepsico|wd3|PepsiCoJobs",
        "cocacolacompany|wd1|coca-cola-careers",
        "kraftheinz|wd1|KraftHeinzCareers",
        "kelloggs|wd1|kellogg",
        "generalmills|wd5|generalmills",
        "abbott|wd5|abbottcareers",
        "abbvie|wd1|abbviecareers",
        "pfizer|wd1|PfizerCareers",
        "merck|wd5|External",
        "lilly|wd5|LLY",
        "jnj|wd5|jnjcareers",
        "novartis|wd3|Novartis_Careers",
        "roche|wd3|roche-ext",
        "regeneron|wd1|Regeneron_External",
        "moderna|wd5|M_tx",
        "biogen|wd5|Biogen_Careers",
        "amgen|wd1|Amgen",
        "gilead|wd5|GileadCareers",
        "unitedhealthgroup|wd5|UHG",
        "anthem|wd5|ANTHEMCAREERS",
        "cvshealth|wd5|cvs_health_careers",
        "humana|wd1|Humana_External_Career_Site",
        "kp|wd5|kaiser",
        "exxonmobil|wd5|ExxonMobil",
        "chevron|wd5|jobs",
        "bp|wd3|bpcareers",
        "shell|wd3|shellcareers",
        "ford|wd1|FordCareers",
        "gm|wd5|gmcareers",
        "stellantis|wd1|Stellantis_Careers",
        "tesla|wd12|tesla",  # Note: Tesla uses its own ATS mostly, but some Workday too
        "rivian|wd1|Rivian",
        "lucidmotors|wd1|Lucid_Careers",
        "uber|wd1|UberInternal",  # Uber primarily Greenhouse, some Workday for non-eng
        "lyft|wd5|lyft",
        "snapchat|wd1|snap",  # Snap Inc. uses Workday with tenant=snapchat, board=snap
        # --- Additional verified Workday companies ---
        "nytimes|wd5|NYT",           # New York Times - Workday board
        "sec|wd3|Samsung_Careers",   # Samsung Electronics - 128 jobs
        "qualcomm|wd12|External",    # Qualcomm - verified endpoint
        "twitter|wd5|X",             # Twitter/X - verified endpoint
        "amat|wd1|External",         # Applied Materials
        "kla|wd1|Search",            # KLA Corporation
        "analogdevices|wd1|External", # Analog Devices
        "broadcom|wd1|External",     # Broadcom
        "marvell|wd1|External",      # Marvell Technology
        "xilinx|wd1|External",       # Xilinx (AMD)
        "nxp|wd1|External",          # NXP Semiconductors
        "infineon|wd1|External",     # Infineon Technologies
        "juniper|wd1|External",      # Juniper Networks
        "arista|wd5|External",       # Arista Networks
        "f5|wd1|External",           # F5 Networks
        "ebay|wd5|External",         # eBay
        "doordash|wd5|External",     # DoorDash
        "airbnb|wd5|External",       # Airbnb
        "coinbase|wd5|External",     # Coinbase
        "crowdstrike|wd5|External",  # CrowdStrike
        "okta|wd5|External",         # Okta
        "atlassian|wd5|External",    # Atlassian
        "zendesk|wd5|External",      # Zendesk
        "hubspot|wd5|External",      # HubSpot
        "twilio|wd5|External",       # Twilio
        "hashicorp|wd5|External",    # HashiCorp
        "mongodb|wd5|External",      # MongoDB
        "elastic|wd5|External",      # Elastic
        "confluent|wd5|External",    # Confluent
        "databricks|wd5|External",   # Databricks
        "snowflake|wd5|External",    # Snowflake
        "datadog|wd5|External",      # Datadog
        "cloudflare|wd5|External",   # Cloudflare
    ],
    # Eightfold seeds: just the company subdomain
    "eightfold": [
        "capitalone",
        "bloomberg",
        "booking",
        "cisco",
        "vodafone",
        "tatadigital",
        "vmware",
        "wayfair",
        "h-d",  # Harley Davidson
        "ge",
        "exxonmobil",
        "chevron",
        "att",
        "verizon",
        "comcast",
        "netflix",  # uses Eightfold for some roles
        "ge-healthcare",
        "lvmh",
        "ralphlauren",
        "macys",
        "kohls",
        "nordstrom",
        "gap",
        "limited-brands",
        "tjx",
        "ross-stores",
        "burlington",
        "fivebelow",
        "dollargeneral",
        "dollartree",
        "tracfone",
        "tcs",  # Tata Consultancy
        "infosys",
        "wipro",
        "hcl",
        "techmahindra",
        "ltimindtree",
        "mphasis",
        "persistent",
        "happiestminds",
        "zensar",
        "coforge",
    ],
    # iCIMS seeds: the tenant slug used in careers-{slug}.icims.com.
    # iCIMS skews toward large enterprise / retail / healthcare / finance.
    # These are best-effort — some tenants JS-gate search and will return
    # nothing (that's fine, the run continues). Verify/extend by visiting a
    # company's careers page and checking for an *.icims.com URL.
    "icims": [
        "compass",            # Compass Group
        "sodexo",
        "aramark",
        "marriott",
        "hilton",
        "hyatt",
        "wyndham",
        "choicehotels",
        "panerabread",
        "chipotle",
        "dominos",
        "wendys",
        "dunkinbrands",
        "darden",             # Olive Garden etc.
        "bloominbrands",
        "ulta",
        "sephora",
        "petco",
        "petsmart",
        "tractorsupply",
        "academy",            # Academy Sports
        "dickssportinggoods",
        "kohls",
        "belk",
        "bjs",                # BJ's Wholesale
        "wegmans",
        "publix",
        "albertsons",
        "aldi",
        "sprouts",
        "ahold",              # Ahold Delhaize USA
        "raleys",
        "hyvee",
        "molsoncoors",
        "constellationbrands",
        "keurigdrpepper",
        "tysonfoods",
        "smithfield",
        "perduefarms",
        "landolakes",
        "dole",
        "delmonte",
        "conagra",
        "campbells",
        "mccormick",
        "hersheys",
        "mars",
        "ferrero",
        "nestleusa",
        "danone",
        "kraftheinz",
        "kelloggcompany",
        "generalmillscareers",
        "schwans",
        "hormel",
        "jbsfoods",
        "cargill",
        "adm",                # Archer Daniels Midland
        "bunge",
        "dow",
        "dupont",
        "ppg",
        "sherwin",            # Sherwin-Williams
        "axalta",
        "huntsman",
        "celanese",
        "eastman",
        "lyondellbasell",
        "westlake",
        "olin",
        "ecolab",
        "internationalpaper",
        "westrock",
        "smurfitwestrock",
        "packagingcorp",
        "sonoco",
        "sealedair",
        "averydennison",
        "owenscorning",
        "masonite",
        "fortunebrands",
        "mohawkindustries",
        "shawindustries",
        "armstrongflooring",
        "whirlpool",
        "electrolux",
        "geappliances",
        "trane",
        "carrier",
        "lennox",
        "rheem",
        "watsco",
        "ferguson",
        "wesco",
        "wwgrainger",         # W.W. Grainger
        "fastenal",
        "msc",                # MSC Industrial
        "appliedindustrial",
        "motion",             # Motion Industries
        "dxpenterprises",
        "univar",
        "brenntag",
        "sigmaaldrich",
        "thermofisher",
        "danaher",
        "becton",             # Becton Dickinson
        "stryker",
        "bostonscientific",
        "medtronic",
        "abbott",
        "baxter",
        "edwards",            # Edwards Lifesciences
        "zimmerbiomet",
        "hologic",
        "intuitive",          # Intuitive Surgical
        "resmed",
        "dexcom",
        "cooper",             # Cooper Companies
        "henryschein",
        "pattersondental",
        "mckesson",
        "cardinalhealth",
        "cencora",            # formerly AmerisourceBergen
        "labcorp",
        "questdiagnostics",
        "davita",
        "fresenius",
        "encompass",          # Encompass Health
        "tenethealth",
        "hcahealthcare",
        "commonspirit",
        "ascension",
        "trinity",            # Trinity Health
        "providence",
        "sutterhealth",
        "bannerhealth",
        "intermountain",
        "geisinger",
        "northwell",
        "montefiore",
        "uhsinc",             # Universal Health Services
        "molinahealthcare",
        "centene",
        "elevancehealth",
        "cigna",
        "humana",
        "aetna",
        "metlife",
        "prudential",
        "massmutual",
        "newyorklife",
        "northwesternmutual",
        "guardian",
        "transamerica",
        "principal",
        "lincolnfinancial",
        "voya",
        "ameriprise",
        "raymondjames",
        "lpl",                # LPL Financial
        "edwardjones",
        "fidelity",
        "tdameritrade",
        "schwab",
        "statestreet",
        "bnymellon",
        "northerntrust",
        "pnc",
        "usbank",
        "truist",
        "regions",
        "fifththird",
        "keybank",
        "huntington",
        "citizensbank",
        "mtb",                # M&T Bank
        "comerica",
        "zions",
        "firsthorizon",
        "synovus",
        "discover",
        "synchrony",
        "allyfinancial",
        "navyfederal",
        "usaa",
        "creditacceptance",
        "santanderus",
    ],
    # CareerPuck: modern ATS with a clean public JSON API. Confirmed users
    # include Earnest and Lyft. The full company list is enumerable from
    # CareerPuck's public sitemap — discovery.py harvests it automatically,
    # so this seed is just a starting point.
    "careerpuck": [
        "earnest",
        "lyft",
    ],
    # SmartRecruiters: widely used by mid-to-large companies globally.
    "smartrecruiters": [
        # --- Verified SmartRecruiters companies ---
        "servicenow",    # ServiceNow - 95 jobs (verified)
        "sportradar",    # Sportradar - 22 jobs (verified)
        # --- Other SmartRecruiters companies ---
        "Bosch", "IKEA", "LinkedIn", "Visa", "Zalando", "Delivery-Hero",
        "HelloFresh", "Trivago", "Klarna", "Adyen", "Booking", "Philips",
        "Siemens", "SAP", "Volkswagen", "BMW", "Daimler", "BASF",
        "Allianz", "Deutsche-Bank", "Commerzbank", "ING", "ABN-AMRO",
        "Heineken", "Unilever", "Shell", "Airbus", "Thales",
        "Capgemini", "Atos", "Sopra-Steria", "CGI", "Infosys-BPM",
        "Cognizant", "Wipro", "HCL-Technologies", "Tech-Mahindra",
        "Revolut", "N26", "Monzo", "Starling-Bank", "Tide",
        "Zara", "H-and-M", "Inditex", "Primark", "ASOS",
        "Spotify", "King", "Mojang", "EA", "Ubisoft",
        "Criteo", "Deezer", "BlaBlaCar", "Doctolib", "Qonto",
        "Contentsquare", "Mirakl", "Vestiaire-Collective", "Voodoo",
        "Meero", "Payfit", "Spendesk", "Alan", "Swile",
        "Personio", "Celonis", "Contentful", "Adjust", "Babbel",
        "Wefox", "Raisin", "Solarisbank", "Mambu", "Penta",
        "Tier", "Grover", "Gorillas", "Flink", "Getir",
        "Omio", "FlixBus", "Taxfix", "Clark", "Getsafe",
        "Moonpig", "Cazoo", "Zego", "Marshmallow", "Cleo",
        "Curve", "Freetrade", "Moneybox", "Wagestream", "Lendable",
        "Mews", "Kiwi", "Productboard", "Rossum", "Rohlik",
        "Pipedrive", "Bolt", "Wise", "Skype", "TransferGo",
        "Vinted", "Wolt", "Onfido", "Quantexa", "Tessian",
        "Tractable", "Synthesia", "Wayve", "Improbable", "Darktrace",
    ],
    # Microsoft: custom scraper (Microsoft Research WordPress API)
    "microsoft": ["microsoft"],
    # Jobvite: popular ATS for US mid-market companies.
    "jobvite": [
        "oracle", "sap", "salesforce", "servicenow", "workday",
        "zendesk", "hubspot", "marketo", "eloqua", "pardot",
        "twilio", "sendgrid", "mailchimp", "constantcontact",
        "hootsuite", "sprinklr", "brandwatch", "meltwater",
        "comscore", "nielsen", "kantar", "ipsos", "gfk",
        "accenture", "deloitte", "kpmg", "pwc", "ey",
        "mckinsey", "bcg", "bain", "boozallen", "leidos",
        "saic", "mitre", "rand", "sri", "rti",
        "qualcomm", "broadcom", "marvell", "xilinx", "amd",
        "texasinstruments", "analog-devices", "maxim", "microchip",
        "nxp", "infineon", "stmicroelectronics", "renesas",
        "juniper", "arista", "f5", "fortinet", "paloaltonetworks",
        "crowdstrike", "sentinelone", "cylance", "carbonblack",
        "proofpoint", "mimecast", "barracuda", "sophos", "trend",
    ],
    # Amazon, Apple, and Google: custom ATS scrapers. Use a single sentinel slug.
    "amazon": ["amazon"],
    "apple": ["apple"],
    "google": ["google"],
    # Meta: uses Greenhouse for engineering roles
    # (metacareers.com blocks bots; Greenhouse board is publicly accessible)
    # Rippling: fast-growing ATS used by many startups.
    "rippling": [
        "rippling", "brex", "ramp", "mercury", "pilot",
        "gusto", "justworks", "bamboohr", "lattice", "culture-amp",
        "15five", "betterup", "modernhealth", "lyrahealth",
        "headspace", "calm", "noom", "ro", "hims",
        "faire", "glossier", "allbirds", "warbyparker", "casper",
        "peloton", "mirror", "tonal", "whoop", "ouraring",
        "duolingo", "coursera", "masterclass", "chegg", "udemy",
        "notion", "coda", "airtable", "clickup", "monday",
        "figma", "miro", "loom", "frame", "pitch",
        "linear", "shortcut", "height", "plane", "jira",
    ],
}


def fetch_text(url):
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.text
    except requests.RequestException as e:
        print(f"  ! Failed to fetch {url}: {e}")
    return None


def extract_slugs_from_text(text):
    """Extract ATS slugs from any text containing application URLs."""
    found = {ats: set() for ats in ATS_PATTERNS}
    for ats, patterns in ATS_PATTERNS.items():
        for pattern in patterns:
            for match in pattern.findall(text):
                # Multi-group patterns (Workday) return a tuple; join with '|'
                if isinstance(match, tuple):
                    # Skip if any group is empty
                    if not all(g.strip() for g in match):
                        continue
                    slug = "|".join(g.lower().strip() for g in match)
                else:
                    slug = match.lower().strip().strip("-.")
                # iCIMS: collapse the careers- prefix so careers-marriott and
                # marriott don't both get stored. The fetcher tries both forms.
                if ats == "icims" and slug.startswith("careers-"):
                    slug = slug[len("careers-"):]
                if slug and len(slug) > 1 and not slug.startswith("www"):
                    found[ats].add(slug)
    return found


def follow_redirect_to_ats(url, max_redirects=3):
    """Some Simplify links go through redirector domains. Follow them."""
    try:
        r = requests.head(url, headers={"User-Agent": USER_AGENT},
                         timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return r.url
    except requests.RequestException:
        return None


def bootstrap():
    print("Bootstrapping company list...\n")
    # Include every ATS we have a seed for OR a URL pattern for. CareerPuck is
    # sitemap-driven (no URL-in-text pattern), so it only appears via the seed.
    all_ats_keys = set(ATS_PATTERNS.keys()) | set(CURATED_SEED.keys())
    all_found = {ats: set() for ats in all_ats_keys}

    # Step 1: seed from curated list
    print("Step 1: Loading curated seed list...")
    for ats, slugs in CURATED_SEED.items():
        all_found[ats].update(s.lower() for s in slugs)
        print(f"  {ats}: {len(slugs)} curated slugs")

    # Step 2: pull Simplify READMEs
    print("\nStep 2: Crawling Simplify GitHub repos...")
    seen_readmes = set()
    for url in SIMPLIFY_README_URLS:
        if url in seen_readmes:
            continue
        seen_readmes.add(url)
        print(f"  Fetching {url}")
        text = fetch_text(url)
        if not text:
            continue
        found = extract_slugs_from_text(text)
        for ats, slugs in found.items():
            new_slugs = slugs - all_found[ats]
            all_found[ats].update(slugs)
            if new_slugs:
                print(f"    + {len(new_slugs)} new {ats} slugs")
        time.sleep(0.5)

    # Step 2.5: harvest the CareerPuck sitemap (enumerates all its tenants).
    print("\nStep 2.5: Harvesting CareerPuck sitemap...")
    cp_text = fetch_text("https://app.careerpuck.com/sitemap.xml")
    if cp_text:
        cp_pattern = re.compile(
            r"https://app\.careerpuck\.com/job-board/([a-z0-9][a-z0-9\-]*)",
            re.IGNORECASE)
        cp_slugs = {m.lower().strip().strip("-.") for m in cp_pattern.findall(cp_text)}
        cp_slugs = {s for s in cp_slugs if len(s) > 1}
        new_cp = cp_slugs - all_found["careerpuck"]
        all_found["careerpuck"].update(cp_slugs)
        print(f"  Found {len(cp_slugs)} CareerPuck boards ({len(new_cp)} new)")
    else:
        print("  (sitemap unreachable — using curated seed only)")

    # Step 3: write companies.json (v2 schema), merging with any existing file
    # so we never clobber discovered companies or their health metadata.
    now = datetime.now(timezone.utc).isoformat()

    existing = {}
    if OUT_PATH.exists():
        try:
            for e in json.loads(OUT_PATH.read_text()):
                existing[(e["ats"], e["slug"])] = e
        except (json.JSONDecodeError, KeyError):
            existing = {}

    companies = []
    seen_keys = set()
    for ats in sorted(all_found.keys()):
        for slug in sorted(all_found[ats]):
            key = (ats, slug)
            seen_keys.add(key)
            if key in existing:
                # Keep existing metadata (source, health), it's already known.
                companies.append(existing[key])
            else:
                companies.append({
                    "slug": slug,
                    "ats": ats,
                    "source": "curated",
                    "added_at": now,
                    "last_validated_at": None,
                    "miss_streak": 0,
                    "last_job_count": None,
                })

    # Preserve any previously-discovered companies not in the seed lists.
    for key, e in existing.items():
        if key not in seen_keys:
            companies.append(e)

    OUT_PATH.write_text(json.dumps(companies, indent=2))
    print(f"\nWrote {len(companies)} companies to {OUT_PATH}")
    for ats in sorted(all_found.keys()):
        print(f"  {ats}: {len(all_found[ats])}")
    discovered = sum(1 for c in companies if c.get("source") == "discovered")
    if discovered:
        print(f"  (preserved {discovered} previously-discovered companies)")


if __name__ == "__main__":
    bootstrap()
