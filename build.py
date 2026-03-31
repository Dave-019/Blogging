import json
import os
import re
import sys
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
    """Fetch all open issues from GitHub."""
    issues = []
    page   = 1
    while True:
        url = (
            f'https://api.github.com/repos/{GITHUB_REPO}/issues'
            f'?state=open&per_page=100&page={page}'
        )
        resp = requests.get(url, headers=HEADERS)
        if resp.status_code != 200:
            print(f'Error fetching issues: {resp.status_code}')
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

def parse_content(body):
    """
    Extract markdown content after the --- separator.
    Converts markdown to simple HTML.
    """
    if not body:
        return ''
    parts = body.split('---', 1)
    if len(parts) < 2:
        return ''
    md = parts[1].strip()
    return markdown_to_html(md)

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

        # Empty line
        elif line.strip() == '':
            html.append('')

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
    labels  = get_labels(issue)
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

    # Determine type from labels
    if 'article' in labels:
        item_type = 'article'
    elif 'link' in labels:
        item_type = 'link'
    elif 'video' in labels:
        item_type = 'video'
    else:
        item_type = 'link'

    # Common fields
    description = parse_field(body, 'Description')
    image       = parse_field(body, 'Image')

    # Clean up GitHub image markdown if pasted as markdown
    img_match = re.search(r'!\[.*?\]\((https://[^)]+)\)', image)
    if img_match:
        image = img_match.group(1)

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
        url              = parse_field(body, 'URL')
        item['url']      = url
        item['youtubeId'] = extract_youtube_id(url)
        item['duration'] = parse_field(body, 'Duration')

    return item

def main():
    print(f'Fetching issues from {GITHUB_REPO}...')
    issues = get_issues()
    print(f'Found {len(issues)} issues')

    items = []
    for issue in issues:
        try:
            item = issue_to_item(issue)
            items.append(item)
            print(f'  ✓ [{item["type"]}] {item["title"][:50]}')
        except Exception as e:
            print(f'  ✗ Error processing issue #{issue.get("number")}: {e}')

    # Sort newest first
    items.sort(key=lambda x: x['timestamp'], reverse=True)

    # Save
    os.makedirs('data', exist_ok=True)
    with open('data/content.json', 'w', encoding='utf-8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    print(f'\nSaved {len(items)} items to data/content.json')

if __name__ == '__main__':
    main()