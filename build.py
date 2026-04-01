import json
import os
import re
import requests
from dateutil import parser as dateparser
from datetime import timezone

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO  = os.environ.get('GITHUB_REPO')

HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json',
}

def get_issues():
    """Fetch ALL issues from GitHub (open and closed)."""
    issues = []
    page   = 1
    while True:
        url = (
            f'https://api.github.com/repos/{GITHUB_REPO}/issues'
            f'?state=all&per_page=100&page={page}'
        )
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            print(f'Error fetching issues: {resp.status_code} - {resp.text}')
            break
        data = resp.json()
        if not data:
            break
        # Skip pull requests
        issues.extend([i for i in data if 'pull_request' not in i])
        page += 1
    return issues

def get_labels(issue):
    """Get list of label names from issue."""
    return [l['name'].lower() for l in issue.get('labels', [])]

def parse_field(body, field):
    """
    Extract a field value from issue body.
    Looks for 'Field: value' format.
    """
    if not body:
        return ''
    pattern = rf'^{field}:\s*(.+)$'
    match = re.search(pattern, body, re.MULTILINE | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ''

def extract_image_url(raw):
    """
    Given a raw Image field value, extract a plain HTTPS URL.
    Handles:
      - Plain URL:          https://example.com/img.jpg
      - Markdown image:     ![alt](https://example.com/img.jpg)
      - HTML img tag:       <img src="https://..." ...>
    Returns a plain URL string or empty string.
    """
    if not raw:
        return ''
    raw = raw.strip()

    # Markdown image: ![alt](url)
    md_match = re.search(r'!\[.*?\]\((https://[^)\s]+)\)', raw)
    if md_match:
        return md_match.group(1)

    # HTML img tag: <img src="url" ...>
    html_match = re.search(r'<img[^>]+src=["\']?(https://[^"\'>\s]+)', raw)
    if html_match:
        return html_match.group(1)

    # Plain URL
    if raw.startswith('https://') or raw.startswith('http://'):
        return raw

    return ''

def detect_type(body):
    """
    Detect content type purely from the issue body fields.
    No labels needed — uses unique fields per template:
      video   → has URL + Duration
      link    → has URL only
      article → has --- content separator
    """
    url      = parse_field(body, 'URL')
    duration = parse_field(body, 'Duration')

    if url and duration:
        return 'video'
    if url:
        return 'link'
    if '---' in (body or ''):
        return 'article'

    return 'link'

def is_hidden(issue):
    """
    Check if an issue should be hidden from the site.
    Checks BOTH the label (in case it works) AND a 'Hidden: true'
    line in the body (reliable, label-independent).
    """
    labels = get_labels(issue)
    if 'hidden' in labels:
        return True

    body = issue.get('body', '') or ''
    if parse_field(body, 'Hidden').lower() in ('true', 'yes', '1'):
        return True

    return False

def parse_content(body):
    """
    Extract markdown content after the first --- separator.
    Strips unfilled template fields and placeholder text.
    """
    if not body:
        return ''

    parts = body.split('---', 1)
    if len(parts) < 2:
        return markdown_to_html(body.strip())

    md = parts[1].strip()

    cleaned = []
    for line in md.split('\n'):
        stripped = line.strip()

        # Skip empty template fields like "Image:", "URL:", "Duration:"
        if re.match(r'^[A-Za-z ]+:\s*$', stripped):
            continue

        # Skip known GitHub issue template placeholder texts
        if stripped in (
            'Write your article content here in markdown.',
            'You can drag and drop images directly into this editor.',
            'No file chosen',
        ):
            continue

        cleaned.append(line)

    return markdown_to_html('\n'.join(cleaned).strip())

def markdown_to_html(md):
    """Simple markdown to HTML converter."""
    if not md:
        return ''

    lines   = md.split('\n')
    html    = []
    in_list = False
    in_pre  = False
    in_ol   = False

    for line in lines:

        # Code blocks
        if line.strip().startswith('```'):
            if in_pre:
                html.append('</code></pre>')
                in_pre = False
            else:
                if in_list:
                    html.append('</ul>')
                    in_list = False
                if in_ol:
                    html.append('</ol>')
                    in_ol = False
                html.append('<pre><code>')
                in_pre = True
            continue

        if in_pre:
            html.append(line)
            continue

        # Close lists if needed
        if in_list and not line.strip().startswith('- ') and not line.strip().startswith('* '):
            html.append('</ul>')
            in_list = False

        if in_ol and not re.match(r'^\d+\.', line.strip()):
            html.append('</ol>')
            in_ol = False

        # Headings
        if line.startswith('# '):
            html.append(f'<h1>{inline_md(line[2:])}</h1>')
        elif line.startswith('## '):
            html.append(f'<h2>{inline_md(line[3:])}</h2>')
        elif line.startswith('### '):
            html.append(f'<h3>{inline_md(line[4:])}</h3>')
        elif line.startswith('#### '):
            html.append(f'<h4>{inline_md(line[5:])}</h4>')

        # Blockquote
        elif line.startswith('> '):
            html.append(f'<blockquote><p>{inline_md(line[2:])}</p></blockquote>')

        # Unordered list
        elif line.strip().startswith('- ') or line.strip().startswith('* '):
            if not in_list:
                html.append('<ul>')
                in_list = True
            item = line.strip()[2:]
            html.append(f'<li>{inline_md(item)}</li>')

        # Ordered list
        elif re.match(r'^\d+\.', line.strip()):
            if not in_ol:
                html.append('<ol>')
                in_ol = True
            item = re.sub(r'^\d+\.\s*', '', line.strip())
            html.append(f'<li>{inline_md(item)}</li>')

        # Horizontal rule
        elif line.strip() in ('---', '***', '___'):
            html.append('<hr>')
        # YouTube embed — bare URL on its own line
        elif re.match(r'^https?://(www\.)?(youtube\.com/watch\?v=|youtu\.be/)', line.strip()):
            vid_id = extract_youtube_id(line.strip())
            if vid_id:
                html.append(f'''<div class="video-embed">
        <iframe src="https://www.youtube.com/embed/{vid_id}"
            frameborder="0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowfullscreen loading="lazy"></iframe>
        </div>''')
            else:
                html.append(f'<p>{inline_md(line)}</p>')

        # Empty line — skip to avoid blank gaps
        elif line.strip() == '':
            continue

        # Paragraph
        else:
            html.append(f'<p>{inline_md(line)}</p>')

    # Close any open tags
    if in_list:
        html.append('</ul>')
    if in_ol:
        html.append('</ol>')
    if in_pre:
        html.append('</code></pre>')

    return '\n'.join(html)

def inline_md(text):
    """Process inline markdown: bold, italic, code, links, images."""
    if not text:
        return ''

    # GitHub image uploads: ![alt](url)
    text = re.sub(
        r'!\[([^\]]*)\]\(([^)]+)\)',
        r'<img src="\2" alt="\1" loading="lazy">',
        text
    )

    # Links: [text](url)
    text = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        text
    )

    # Bold: **text**
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)

    # Italic: *text*
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)

    # Inline code: `code`
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    return text

def extract_youtube_id(url):
    """Extract YouTube video ID from URL."""
    if not url:
        return ''
    patterns = [
        r'(?:youtube\.com/watch\?v=)([^&\s]+)',
        r'(?:youtu\.be/)([^?\s]+)',
        r'(?:youtube\.com/embed/)([^?\s]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ''

def issue_to_item(issue):
    """Convert a GitHub issue to a content item."""
    body    = issue.get('body', '') or ''
    title   = issue.get('title', '').strip()
    date    = issue.get('created_at', '')
    item_id = str(issue['number'])

    # Parse date
    try:
        dt        = dateparser.parse(date)
        dt_utc    = dt.astimezone(timezone.utc)
        timestamp = int(dt_utc.timestamp() * 1000)
        date_iso  = dt_utc.isoformat()
    except Exception:
        timestamp = 0
        date_iso  = date

    item_type   = detect_type(body)
    description = parse_field(body, 'Description')
    image       = extract_image_url(parse_field(body, 'Image'))

    item = {
        'id':          item_id,
        'type':        item_type,
        'title':       title,
        'description': description,
        'image':       image,
        'date':        date_iso,
        'timestamp':   timestamp,
    }

    if item_type == 'article':
        item['content'] = parse_content(body)

    elif item_type == 'link':
        item['url'] = parse_field(body, 'URL')

    elif item_type == 'video':
        url               = parse_field(body, 'URL')
        item['url']       = url
        item['youtubeId'] = extract_youtube_id(url)
        item['duration']  = parse_field(body, 'Duration')

    return item

def main():
    print(f'Fetching issues from {GITHUB_REPO}...')
    issues = get_issues()
    print(f'Found {len(issues)} issues')

    items = []
    for issue in issues:
        try:
            # Skip hidden posts — checks label AND body field
            if is_hidden(issue):
                print(f'  – skipped  #{issue.get("number")} (hidden)')
                continue

            item = issue_to_item(issue)
            items.append(item)
            print(f'  ✓ [{item["type"]}] #{issue["number"]} {item["title"][:50]}')
        except Exception as e:
            print(f'  ✗ Error processing issue #{issue.get("number")}: {e}')

    # Sort newest first
    items.sort(key=lambda x: x['timestamp'], reverse=True)

    # ── Merge with legacy content ──────────────────────────
    os.makedirs('data', exist_ok=True)
    existing = []
    try:
        with open('data/content.json', 'r', encoding='utf-8') as f:
            existing = json.load(f)
        print(f'Found {len(existing)} existing entries in content.json')
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Keep legacy entries whose IDs are not pure integers
    github_ids = {item['id'] for item in items}
    legacy     = [e for e in existing if not e['id'].isdigit() and e['id'] not in github_ids]

    if legacy:
        print(f'Keeping {len(legacy)} legacy entries')

    merged = items + legacy
    merged.sort(key=lambda x: x['timestamp'], reverse=True)

    with open('data/content.json', 'w', encoding='utf-8') as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    print(f'\nSaved {len(merged)} items to data/content.json')
    print(f'  → {len(items)} from GitHub issues')
    print(f'  → {len(legacy)} legacy entries preserved')

if __name__ == '__main__':
    main()