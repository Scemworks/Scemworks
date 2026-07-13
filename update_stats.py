import re
import urllib.request
import json

USERNAME = "scemworks"

# 1. Fetch user data from GitHub API
url = f"https://api.github.com/users/{USERNAME}"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        repos = data.get("public_repos", 5)
        followers = data.get("followers", 8)
        following = data.get("following", 13)
except Exception as e:
    print(f"Error fetching user data: {e}")
    exit(1)

# 2. Fetch total stars (iterate through repos)
stars = 0
try:
    repos_url = f"https://api.github.com/users/{USERNAME}/repos?per_page=100"
    req_repos = urllib.request.Request(repos_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req_repos) as response:
        repos_data = json.loads(response.read().decode())
        for repo in repos_data:
            stars += repo.get("stargazers_count", 0)
except Exception as e:
    print(f"Error fetching repos: {e}")
    pass

# 3. Read SVG file
svg_path = "neofetch.svg"
try:
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()
except FileNotFoundError:
    print(f"Error: {svg_path} not found.")
    exit(1)

# 4. Update stats using regex
# Repos
svg_content = re.sub(
    r'(<text x="440" y="320" class="info-9">.*?<tspan fill="#f0883e">)\d+(</tspan><tspan fill="#e6edf3"> public</tspan></text>)',
    rf'\g<1>{repos}\g<2>',
    svg_content
)

# Follow
svg_content = re.sub(
    r'(<text x="440" y="342" class="info-10">.*?<tspan fill="#e6edf3">)\d+ followers, \d+ following(</tspan></text>)',
    rf'\g<1>{followers} followers, {following} following\g<2>',
    svg_content
)

# Stars
svg_content = re.sub(
    r'(<text x="440" y="364" class="info-11">.*?<tspan fill="#f0883e">)\d+(</tspan><tspan fill="#e6edf3"> total</tspan></text>)',
    rf'\g<1>{stars}\g<2>',
    svg_content
)

# 5. Write back to SVG
with open(svg_path, "w", encoding="utf-8") as f:
    f.write(svg_content)

# 6. Update README.md to bypass GitHub caching
import time
readme_path = "README.md"
try:
    with open(readme_path, "r", encoding="utf-8") as f:
        readme_content = f.read()
    
    timestamp = int(time.time())
    # Regex to replace existing query param if it exists, or append one if it doesn't
    readme_content = re.sub(
        r'(<img\s+src="\./neofetch\.svg)(?:\?v=\d+)?(")',
        rf'\g<1>?v={timestamp}\g<2>',
        readme_content
    )
    
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    print(f"Updated README.md image cache with timestamp {timestamp}")
except Exception as e:
    print(f"Error updating README.md: {e}")

print(f"Successfully updated SVG! Repos: {repos}, Followers: {followers}, Following: {following}, Stars: {stars}")
