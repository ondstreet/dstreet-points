# web/api/community_api.py
"""
Community API - Link submissions, voting, and knowledge base.
"""

from flask import Blueprint, request, jsonify
from core.unified_system.search_engine import search_engine
from core.modes.mode_manager import mode_manager
from core.content.web_scraper import scrape_and_update_context
import logging
from datetime import datetime
from core.content.link_moderator import LinkModerator

logger = logging.getLogger(__name__)

community_bp = Blueprint('community', __name__, url_prefix='/api/community')
moderator = LinkModerator()

@community_bp.route('/link/submit', methods=['POST'])
def submit_link():
    """
    Submit a community link with safety checks and user permission validation.
    """
    data = request.get_json()
    user_id = data.get('user_id')
    url = data.get('url')
    title = data.get('title')
    description = data.get('description', '')
    tags = data.get('tags', [])

    if not user_id or not url:
        return jsonify({'error': 'user_id and url required'}), 400

    # ------------------------------------------------------------------
    # 1. Check user permission (paid tier / trust level)
    # ------------------------------------------------------------------
    can_submit, reason = moderator.check_user_can_submit(user_id)
    if not can_submit and reason == "requires_moderation":
        # Queue for manual review (no automatic publishing)
        queue_link(user_id, url, title, description, tags)
        return jsonify({
            'success': True,
            'moderated': True,
            'message': 'Link submitted for review. It will appear once approved.'
        })
    elif not can_submit:
        return jsonify({
            'error': 'You need a higher trust level or subscription to submit links.',
            'reason': reason
        }), 403

    # ------------------------------------------------------------------
    # 2. Scrape the URL to get metadata (if title missing)
    # ------------------------------------------------------------------
    if not title:
        scraped = scrape_and_update_context(user_id, url, mode_manager)
        title = scraped.get('title', url)
        if not description and scraped.get('description'):
            description = scraped.get('description')

    # ------------------------------------------------------------------
    # 3. Moderate the content (NSFW, toxicity, CSAM, unsafe URL)
    # ------------------------------------------------------------------
    # Collect any image URLs from the scraped content (if available)
    image_urls = scraped.get('og_image', []) if 'scraped' in locals() else []
    safety = moderator.moderate_link(url, title, description, image_urls)

    if not safety['approved']:
        if 'csam_detected' in safety['issues']:
            # Immediate block and report (legal requirement)
            moderator.report_to_authorities(user_id, url)
            return jsonify({'error': 'Content blocked and reported.'}), 400
        elif 'unsafe_url' in safety['issues']:
            return jsonify({'error': 'This URL is known to be unsafe.'}), 400
        else:
            return jsonify({
                'error': 'Content failed safety checks.',
                'issues': safety['issues']
            }), 400

    # ------------------------------------------------------------------
    # 4. Generate unique ID and store the link
    # ------------------------------------------------------------------
    link_id = hashlib.md5(f"{url}_{datetime.now().isoformat()}".encode()).hexdigest()[:12]

    link_data = {
        'id': link_id,
        'url': url,
        'title': title,
        'description': description,
        'tags': tags,
        'submitted_by': user_id,
        'votes': 0,
        'vote_count': 0,
        'created_at': datetime.now().isoformat(),
        'type': 'community_link',
        'moderated': False,          # auto-approved
        'approved_at': datetime.now().isoformat()
    }

    # Index in search engine
    search_engine.index_community_link(
        link_id=link_id,
        url=url,
        title=title,
        description=description,
        tags=tags
    )

    # Store in JSON for vote tracking
    links_file = Path("data/community_links.json")
    if links_file.exists():
        with open(links_file, 'r') as f:
            links = json.load(f)
    else:
        links = []
    links.append(link_data)
    with open(links_file, 'w') as f:
        json.dump(links, f, indent=2)

    return jsonify({'success': True, 'link': link_data})


# ------------------------------------------------------------------
# Helper: Queue link for manual review (for free / untrusted users)
# ------------------------------------------------------------------
def queue_link(user_id, url, title, description, tags):
    """Store link in a moderation queue instead of publishing immediately."""
    queue_file = Path("data/moderation/pending_links.json")
    queue_file.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        'user_id': user_id,
        'url': url,
        'title': title,
        'description': description,
        'tags': tags,
        'submitted_at': datetime.now().isoformat(),
        'status': 'pending'
    }

    if queue_file.exists():
        with open(queue_file, 'r') as f:
            queue = json.load(f)
    else:
        queue = []
    queue.append(entry)
    with open(queue_file, 'w') as f:
        json.dump(queue, f, indent=2)
        
@community_bp.route('/link/vote', methods=['POST'])
def vote_link():
    """
    Upvote or downvote a community link.
    Body: { "user_id": "...", "link_id": "...", "vote": "up" or "down" }
    """
    data = request.get_json()
    user_id = data.get('user_id')
    link_id = data.get('link_id')
    vote = data.get('vote')  # 'up' or 'down'

    if not user_id or not link_id or vote not in ['up', 'down']:
        return jsonify({'error': 'user_id, link_id, and vote (up/down) required'}), 400

    from pathlib import Path
    import json

    links_file = Path("data/community_links.json")
    if not links_file.exists():
        return jsonify({'error': 'No links found'}), 404

    with open(links_file, 'r') as f:
        links = json.load(f)

    link = None
    for l in links:
        if l['id'] == link_id:
            link = l
            break

    if not link:
        return jsonify({'error': 'Link not found'}), 404

    # Track user votes to prevent double voting
    votes_file = Path("data/user_votes.json")
    if votes_file.exists():
        with open(votes_file, 'r') as f:
            user_votes = json.load(f)
    else:
        user_votes = {}

    user_key = f"{user_id}_{link_id}"
    previous_vote = user_votes.get(user_key)

    # Adjust vote count
    if vote == 'up':
        if previous_vote == 'up':
            # Remove vote
            link['votes'] -= 1
            link['vote_count'] -= 1
            del user_votes[user_key]
        elif previous_vote == 'down':
            # Switch from down to up (+2 net)
            link['votes'] += 2
            # vote_count unchanged (still one vote)
            user_votes[user_key] = 'up'
        else:
            # New upvote
            link['votes'] += 1
            link['vote_count'] += 1
            user_votes[user_key] = 'up'
    else:  # down
        if previous_vote == 'down':
            # Remove vote
            link['votes'] += 1  # remove the -1 (so +1)
            link['vote_count'] -= 1
            del user_votes[user_key]
        elif previous_vote == 'up':
            # Switch from up to down (-2 net)
            link['votes'] -= 2
            user_votes[user_key] = 'down'
        else:
            # New downvote
            link['votes'] -= 1
            link['vote_count'] += 1
            user_votes[user_key] = 'down'

    # Save updated links and votes
    with open(links_file, 'w') as f:
        json.dump(links, f, indent=2)
    with open(votes_file, 'w') as f:
        json.dump(user_votes, f, indent=2)

    return jsonify({
        'success': True,
        'link_id': link_id,
        'votes': link['votes'],
        'vote_count': link['vote_count']
    })


@community_bp.route('/links', methods=['GET'])
def get_links():
    """Get all community links, optionally sorted by votes."""
    sort_by = request.args.get('sort', 'votes')  # votes, newest
    from pathlib import Path
    import json

    links_file = Path("data/community_links.json")
    if not links_file.exists():
        return jsonify({'links': []})

    with open(links_file, 'r') as f:
        links = json.load(f)

    if sort_by == 'votes':
        links.sort(key=lambda x: x.get('votes', 0), reverse=True)
    elif sort_by == 'newest':
        links.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    return jsonify({'links': links})
