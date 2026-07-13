import urllib.request
import json
import os
import datetime
import re

USERNAME = "scemworks"
env_file = ".env"

# 1. Load Environment Variables
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                parts = line.strip().split('=', 1)
                if len(parts) == 2:
                    os.environ[parts[0]] = parts[1].strip("'\" ")

token = os.environ.get("GH_PAT")
if not token:
    print("Error: GH_PAT is missing. Please add it to your .env file or GitHub Secrets.")
    exit(1)

# 2. GraphQL Query Definition
# We fetch basic profile info, total PRs/Issues, language stats, and the contribution calendar.
# To get exact lifetime commits, we would query each year, but for simplicity we fetch the current year
# and use totalCommitContributions for the last year. However, the user wants lifetime commits.
# We will query the REST API for public lifetime commits or use GraphQL to fetch all years dynamically.

def run_graphql_query(query, variables):
    req = urllib.request.Request("https://api.github.com/graphql", method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    data = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data=data) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"GraphQL Error: {e}")
        if hasattr(e, 'read'):
            print(e.read().decode())
        return None

# Fetch creation date to know how many years to query
init_query = """
query($username: String!) {
  user(login: $username) {
    createdAt
  }
}
"""
init_res = run_graphql_query(init_query, {"username": USERNAME})
created_at_str = init_res['data']['user']['createdAt']
created_year = int(created_at_str[:4])
current_year = datetime.datetime.now().year

# Dynamically construct query for all years
years_queries = ""
for y in range(created_year, current_year + 1):
    from_date = f"{y}-01-01T00:00:00Z"
    to_date = f"{y}-12-31T23:59:59Z"
    years_queries += f"""
    year_{y}: contributionsCollection(from: "{from_date}", to: "{to_date}") {{
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {{
        totalContributions
        weeks {{
          contributionDays {{
            contributionCount
            date
          }}
        }}
      }}
    }}
    """

full_query = f"""
query($username: String!) {{
  user(login: $username) {{
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, orderBy: {{field: STARGAZERS, direction: DESC}}) {{
      nodes {{
        stargazers {{ totalCount }}
        languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{
          edges {{ size node {{ color name }} }}
        }}
      }}
    }}
    {years_queries}
  }}
}}
"""

print("Fetching full GitHub stats via GraphQL...")
data = run_graphql_query(full_query, {"username": USERNAME})
user_data = data['data']['user']

# 3. Calculate Stats
total_stars = 0
languages = {}
total_lang_size = 0

for repo in user_data['repositories']['nodes']:
    total_stars += repo['stargazers']['totalCount']
    for lang_edge in repo['languages']['edges']:
        name = lang_edge['node']['name']
        color = lang_edge['node']['color']
        size = lang_edge['size']
        if name not in languages:
            languages[name] = {"size": 0, "color": color}
        languages[name]['size'] += size
        total_lang_size += size

# Sort languages by size
sorted_langs = sorted(languages.items(), key=lambda item: item[1]['size'], reverse=True)
top_langs = sorted_langs[:5] # Top 5

# Aggregate lifetime contributions
total_commits = 0
total_private_commits = 0
total_prs = 0
total_issues = 0
contributions_last_year = 0

# Track all contribution days for streaks
all_days = []

for y in range(created_year, current_year + 1):
    year_data = user_data[f'year_{y}']
    total_commits += year_data['totalCommitContributions']
    total_private_commits += year_data['restrictedContributionsCount']
    total_prs += year_data['totalPullRequestContributions']
    total_issues += year_data['totalIssueContributions']
    
    for week in year_data['contributionCalendar']['weeks']:
        for day in week['contributionDays']:
            all_days.append({
                "date": day['date'],
                "count": day['contributionCount']
            })

# Fix missing days or duplicates by sorting
all_days.sort(key=lambda d: d['date'])

# Calculate streaks
current_streak = 0
longest_streak = 0
temp_streak = 0
total_contributions = 0

today_str = datetime.datetime.now().strftime("%Y-%m-%d")
yesterday_str = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
is_current_streak_active = False

for day in all_days:
    total_contributions += day['count']
    if day['count'] > 0:
        temp_streak += 1
        longest_streak = max(longest_streak, temp_streak)
        if day['date'] == today_str or day['date'] == yesterday_str:
            is_current_streak_active = True
    else:
        # Check if we should reset current streak
        if day['date'] < yesterday_str:
            temp_streak = 0
        elif day['date'] == yesterday_str and day['count'] == 0:
             # If yesterday had 0, streak is broken unless today has contributions (handled next iteration)
             temp_streak = 0

# Assign current streak
current_streak = temp_streak if is_current_streak_active else 0

total_lifetime_commits = total_commits + total_private_commits

# Rank Calculation
score = total_commits * 1 + total_prs * 5 + total_issues * 3 + total_stars * 10
rank = "C"
percentage = 30
if score > 1000:
    rank = "B"
    percentage = 50
if score > 5000:
    rank = "A"
    percentage = 70
if score > 10000:
    rank = "A+"
    percentage = 85
if score > 20000:
    rank = "S"
    percentage = 100

# 4. Generate SVG Content
svg_width = 800
gap = 30

# Calculate heights dynamically
block1_height = 190
block2_height = 190

# Calculate language rows
num_langs = len(top_langs)
cols = 3
rows = (num_langs + cols - 1) // cols
block3_height = 160 + (rows * 40)

svg_height = block1_height + gap + block2_height + gap + block3_height + 20 # 20 padding at bottom

# Ring math
circumference = 2 * 3.14159 * 35 # r=35
dashoffset = circumference - (circumference * (percentage / 100))

# Streak ring math
streak_pct = min((current_streak / max(longest_streak, 1)) * 100, 100)
streak_circumference = 2 * 3.14159 * 35
streak_dashoffset = streak_circumference - (streak_circumference * (streak_pct / 100))

# Language bar SVG components
lang_bars = ""
lang_labels = ""
x_offset = 0
bar_width = 720

# To prevent division by zero
if total_lang_size == 0: total_lang_size = 1

# Terminal neon color palette for distinct, vibrant language colors
neon_colors = ["#ff5f57", "#ffbd2e", "#28c840", "#58a6ff", "#d2a8ff", "#ff7b72", "#79c0ff", "#f2cc60", "#a5d6ff"]

for idx, (lang_name, lang_data) in enumerate(top_langs):
    pct = (lang_data['size'] / total_lang_size) * 100
    width = (pct / 100) * bar_width
    
    # Use a vibrant terminal color instead of GitHub's default
    display_color = neon_colors[idx % len(neon_colors)]
    
    lang_bars += f'<rect x="{x_offset}" y="0" width="{width}" height="12" fill="{display_color}" />\n'
    x_offset += width
    
    # Label
    col = idx % cols
    row = idx // cols
    lx = col * 240
    ly = 50 + (row * 35)
    lang_labels += f'''
    <g transform="translate({lx}, {ly})">
        <circle cx="6" cy="-1" r="6" fill="{display_color}" />
        <text x="20" y="4" font-family="'JetBrains Mono', monospace" font-size="14" fill="#8b949e">{lang_name} {pct:.1f}%</text>
    </g>
    '''

def get_terminal_header(width, height):
    return f"""
    <rect x="0" y="0" width="{width}" height="{height}" rx="12" ry="12" fill="#1c2128" />
    <rect x="0" y="0" width="{width}" height="38" rx="12" ry="12" fill="url(#headerGrad)" />
    <rect x="0" y="20" width="{width}" height="18" fill="url(#headerGrad)" />
    <circle cx="22" cy="19" r="6" fill="#ff5f57"/>
    <circle cx="42" cy="19" r="6" fill="#ffbd2e"/>
    <circle cx="62" cy="19" r="6" fill="#28c840"/>
    <rect x="0" y="38" width="{width}" height="{height - 38}" rx="12" ry="12" fill="url(#termBg)" />
    <rect x="0" y="0" width="{width}" height="{height}" rx="12" ry="12" fill="none" stroke="#1f6feb" stroke-width="1.5" opacity="0.6"/>
"""

svg_template = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}" width="{svg_width}" height="{svg_height}">
  <defs>
    <linearGradient id="termBg" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#0d1117;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#0a0e13;stop-opacity:1" />
    </linearGradient>
    <linearGradient id="headerGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#21262d;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#161b22;stop-opacity:1" />
    </linearGradient>
    <filter id="shadow" x="-5%" y="-5%" width="110%" height="115%">
      <feDropShadow dx="0" dy="4" stdDeviation="8" flood-color="#000000" flood-opacity="0.6"/>
    </filter>
    <style>
      .title {{ font-family: 'JetBrains Mono', monospace; font-size: 16px; font-weight: bold; fill: #e6edf3; }}
      .label {{ font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: bold; fill: #58a6ff; }}
      .colon {{ font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: bold; fill: #8b949e; }}
      .value {{ font-family: 'JetBrains Mono', monospace; font-size: 14px; font-weight: bold; fill: #e6edf3; }}
      .highlight {{ fill: #e6edf3; font-family: 'JetBrains Mono', monospace; font-size: 28px; font-weight: bold; text-anchor: middle; }}
      /* Animation styles */
      @keyframes slideUpFade {{
        from {{ opacity: 0; transform: translateY(20px); }}
        to {{ opacity: 1; transform: translateY(0); }}
      }}
      .animated-block {{
        opacity: 0;
        animation: slideUpFade 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
      }}
      /* Neofetch takes ~2.65s to finish, so we start after that */
      .block-1 {{ animation-delay: 2.8s; }}
      .block-2 {{ animation-delay: 3.1s; }}
      .block-3 {{ animation-delay: 3.4s; }}
    </style>
  </defs>

  <!-- BLOCK 1: GitHub Stats -->
  <g transform="translate(0, 0)" filter="url(#shadow)">
    <g class="animated-block block-1">
    {get_terminal_header(svg_width, block1_height)}
    <text x="30" y="70" class="title"><tspan fill="#3fb950">Mohammed Shadin</tspan><tspan fill="#8b949e">'s </tspan><tspan fill="#58a6ff">GitHub Stats</tspan></text>
    
    <text x="30" y="105"><tspan class="label">Total Stars Earned</tspan><tspan class="colon">    : </tspan><tspan class="value">{total_stars}</tspan></text>
    <text x="30" y="130"><tspan class="label">Total Commits</tspan><tspan class="colon">         : </tspan><tspan class="value">{total_lifetime_commits} </tspan><tspan fill="#8b949e" font-size="12">(Inc. Private)</tspan></text>
    <text x="30" y="155"><tspan class="label">Total PRs</tspan><tspan class="colon">             : </tspan><tspan class="value">{total_prs}</tspan></text>
    <text x="360" y="105"><tspan class="label">Total Issues</tspan><tspan class="colon">          : </tspan><tspan class="value">{total_issues}</tspan></text>

    <!-- Rank Badge -->
    <g transform="translate(680, 115)">
      <circle cx="0" cy="0" r="40" fill="none" stroke="#21262d" stroke-width="8" />
      <circle cx="0" cy="0" r="40" fill="none" stroke="#3fb950" stroke-width="8" stroke-dasharray="{2 * 3.14159 * 40}" stroke-dashoffset="{(2 * 3.14159 * 40) - ((2 * 3.14159 * 40) * (percentage / 100))}" transform="rotate(-90)" />
      <text x="0" y="10" font-family="'JetBrains Mono', monospace" font-size="32" font-weight="bold" fill="#e6edf3" text-anchor="middle">{rank}</text>
    </g>
    </g>
  </g>

  <!-- BLOCK 2: Streaks -->
  <g transform="translate(0, {block1_height + gap})" filter="url(#shadow)">
    <g class="animated-block block-2">
    {get_terminal_header(svg_width, block2_height)}
    <text x="400" y="24" text-anchor="middle" fill="#8b949e" font-size="13" font-family="'JetBrains Mono', monospace">streak_stats.sh</text>
    <text x="30" y="70" class="title">GitHub Streak Stats</text>
    
    <!-- Total Contributions -->
    <g transform="translate(160, 120)">
        <text x="0" y="0" class="highlight">{total_contributions}</text>
        <text x="0" y="30" class="streak-label">Total Contributions</text>
        <text x="0" y="55" class="streak-label" font-size="12">{created_year} - Present</text>
    </g>

    <!-- Current Streak -->
    <g transform="translate(400, 120)">
        <circle cx="0" cy="-15" r="40" fill="none" stroke="#21262d" stroke-width="6" />
        <circle cx="0" cy="-15" r="40" fill="none" stroke="#f0883e" stroke-width="6" stroke-dasharray="{2 * 3.14159 * 40}" stroke-dashoffset="{(2 * 3.14159 * 40) - ((2 * 3.14159 * 40) * (streak_pct / 100))}" transform="rotate(-90 0 -15)" />
        <text x="0" y="-5" class="highlight" font-size="32">{current_streak}</text>
        <text x="0" y="50" class="streak-label" fill="#f0883e" font-weight="bold" font-size="16">Current Streak</text>
    </g>

    <!-- Longest Streak -->
    <g transform="translate(640, 120)">
        <text x="0" y="0" class="highlight">{longest_streak}</text>
        <text x="0" y="30" class="streak-label">Longest Streak</text>
    </g>
    </g>
  </g>

  <!-- BLOCK 3: Languages -->
  <g transform="translate(0, {block1_height + block2_height + (gap * 2)})" filter="url(#shadow)">
    <g class="animated-block block-3">
    {get_terminal_header(svg_width, block3_height)}
    <text x="400" y="24" text-anchor="middle" fill="#8b949e" font-size="13" font-family="'JetBrains Mono', monospace">languages.sh</text>
    <text x="30" y="65" class="title">Most Used Languages</text>
    
    <g transform="translate(40, 95)">
        <!-- Stacked Bar -->
        <clipPath id="bar-clip">
            <rect x="0" y="0" width="{bar_width}" height="12" rx="6" />
        </clipPath>
        <g clip-path="url(#bar-clip)">
            {lang_bars}
        </g>
        
        <!-- Language Labels -->
        <g transform="translate(0, 30)">
            {lang_labels}
        </g>
    </g>
    </g>
  </g>

</svg>"""

with open("github_advanced_stats.svg", "w", encoding="utf-8") as f:
    f.write(svg_template)

import time
import re
try:
    timestamp = int(time.time())
    with open("README.md", "r", encoding="utf-8") as f:
        readme_content = f.read()
    
    readme_content = re.sub(r'github_advanced_stats\.svg\?v=\d+', f'github_advanced_stats.svg?v={timestamp}', readme_content)
    
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
except Exception as e:
    print("Could not update README.md", e)

print("Successfully generated github_advanced_stats.svg!")

