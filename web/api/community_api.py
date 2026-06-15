# web/api/community_api.py
"""
Community API – link submissions, voting, knowledge base,
and bug tracking / bounties / user stats.
"""

import hashlib
import json
import logging
from pathlib import Path
from datetime import datetime
import uuid

from flask import Blueprint, request, jsonify
from sqlalchemy import func

# Link submission modules
from core.unified_system.search_engine import search_engine
from core.modes.mode_manager import mode_manager
from core.content.web_scraper import scrape_and_update_context
from core.content.link_moderator import LinkModerator

# Points / community models
from points_service.points_api import get_db_session, get_user_points
from core.models.community import BugReport, Bounty, UserCommunityStats, BugStatus, BountyStatus

logger = logging.getLogger(__name__)
community_bp = Blueprint('community', __name__, url_prefix='/api/community')
moderator = LinkModerator()

# ------------------------------------------------------------------
# Link submission & voting (existing)
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

    can_submit, reason = moderator.check_user_can_submit(user_id)
    if not can_submit and reason == "requires_moderation":
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

    if not title:
        scraped = scrape_and_update_context(user_id, url, mode_manager)
        title = scraped.get('title', url)
        if not description and scraped.get('description'):
            description = scraped.get('description')

    image_urls = scraped.get('og_image', []) if 'scraped' in locals() else []
    safety = moderator.moderate_link(url, title, description, image_urls)

    if not safety['approved']:
        if 'csam_detected' in safety['issues']:
            moderator.report_to_authorities(user_id, url)
            return jsonify({'error': 'Content blocked and reported.'}), 400
        elif 'unsafe_url' in safety['issues']:
            return jsonify({'error': 'This URL is known to be unsafe.'}), 400
        else:
            return jsonify({
                'error': 'Content failed safety checks.',
                'issues': safety['issues']
            }), 400

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
        'moderated': False,
        'approved_at': datetime.now().isoformat()
    }

    search_engine.index_community_link(
        link_id=link_id,
        url=url,
        title=title,
        description=description,
        tags=tags
    )

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

@community_bp.route('/link/vote', methods=['POST'])
def vote_link():
    """
    Upvote or downvote a community link.
    Body: { "user_id": "...", "link_id": "...", "vote": "up" or "down" }
    """
    data = request.get_json()
    user_id = data.get('user_id')
    link_id = data.get('link_id')
    vote = data.get('vote')

    if not user_id or not link_id or vote not in ['up', 'down']:
        return jsonify({'error': 'user_id, link_id, and vote (up/down) required'}), 400

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

    votes_file = Path("data/user_votes.json")
    if votes_file.exists():
        with open(votes_file, 'r') as f:
            user_votes = json.load(f)
    else:
        user_votes = {}

    user_key = f"{user_id}_{link_id}"
    previous_vote = user_votes.get(user_key)

    if vote == 'up':
        if previous_vote == 'up':
            link['votes'] -= 1
            link['vote_count'] -= 1
            del user_votes[user_key]
        elif previous_vote == 'down':
            link['votes'] += 2
            user_votes[user_key] = 'up'
        else:
            link['votes'] += 1
            link['vote_count'] += 1
            user_votes[user_key] = 'up'
    else:  # down
        if previous_vote == 'down':
            link['votes'] += 1
            link['vote_count'] -= 1
            del user_votes[user_key]
        elif previous_vote == 'up':
            link['votes'] -= 2
            user_votes[user_key] = 'down'
        else:
            link['votes'] -= 1
            link['vote_count'] += 1
            user_votes[user_key] = 'down'

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
    sort_by = request.args.get('sort', 'votes')
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

# ------------------------------------------------------------------
# Bug tracking & bounties (new)
# ------------------------------------------------------------------

def update_user_stats(session, user_id):
    """Recalc or update user stats for community."""
    stats = session.query(UserCommunityStats).filter_by(user_id=user_id).first()
    if not stats:
        stats = UserCommunityStats(user_id=user_id)
        session.add(stats)
    reported = session.query(BugReport).filter_by(user_id=user_id).count()
    fixed = session.query(BugReport).filter_by(fixed_by=user_id, status=BugStatus.FIXED).count()
    claimed = session.query(Bounty).filter_by(claimed_by=user_id).count()
    completed = session.query(Bounty).filter_by(claimed_by=user_id, status=BountyStatus.COMPLETED).count()
    stats.bugs_reported = reported
    stats.bugs_fixed = fixed
    stats.bounties_claimed = claimed
    stats.bounties_completed = completed
    session.commit()
    return stats

@community_bp.route('/bugs', methods=['GET'])
def list_bugs():
    session = get_db_session()
    bugs = session.query(BugReport).order_by(BugReport.created_at.desc()).all()
    session.close()
    return jsonify([{
        'id': str(b.id),
        'title': b.title,
        'description': b.description,
        'status': b.status.value,
        'severity': b.severity,
        'bounty_points': b.bounty_points,
        'created_at': b.created_at.isoformat(),
        'fixed_by': str(b.fixed_by) if b.fixed_by else None,
        'reporter_id': str(b.user_id)
    } for b in bugs])

@community_bp.route('/bugs', methods=['POST'])
def create_bug():
    data = request.get_json()
    required = ['user_id', 'title', 'description']
    if not all(k in data for k in required):
        return jsonify({'error': 'missing fields'}), 400
    try:
        user_uuid = uuid.UUID(data['user_id'])
    except:
        return jsonify({'error': 'invalid user_id'}), 400
    session = get_db_session()
    get_user_points(session, user_uuid)
    bug = BugReport(
        user_id=user_uuid,
        title=data['title'],
        description=data['description'],
        severity=data.get('severity', 'normal'),
        bounty_points=data.get('bounty_points', 0),
        error_report_path=data.get('error_report_path')
    )
    session.add(bug)
    session.commit()
    update_user_stats(session, user_uuid)
    session.close()
    return jsonify({'message': 'Bug report created', 'id': str(bug.id)}), 201

@community_bp.route('/bugs/<bug_id>/claim', methods=['POST'])
def claim_bug(bug_id):
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    try:
        bug_uuid = uuid.UUID(bug_id)
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid UUID'}), 400
    session = get_db_session()
    bug = session.query(BugReport).filter_by(id=bug_uuid).first()
    if not bug or bug.status != BugStatus.OPEN:
        session.close()
        return jsonify({'error': 'Bug not found or not open'}), 404
    bug.status = BugStatus.CLAIMED
    bug.fixed_by = user_uuid
    session.commit()
    update_user_stats(session, user_uuid)
    session.close()
    return jsonify({'message': 'Bug claimed'}), 200

@community_bp.route('/bugs/<bug_id>/resolve', methods=['POST'])
def resolve_bug(bug_id):
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    try:
        bug_uuid = uuid.UUID(bug_id)
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid UUID'}), 400
    session = get_db_session()
    bug = session.query(BugReport).filter_by(id=bug_uuid).first()
    if not bug or bug.status != BugStatus.CLAIMED or bug.fixed_by != user_uuid:
        session.close()
        return jsonify({'error': 'Bug not claimed by you or not claimable'}), 400
    bug.status = BugStatus.FIXED
    bug.resolved_at = datetime.utcnow()
    if bug.bounty_points > 0:
        user = get_user_points(session, user_uuid)
        user.balance += bug.bounty_points
        user.lifetime_earned += bug.bounty_points
        from core.models.points import RewardLog
        log = RewardLog(user_id=user_uuid, amount=bug.bounty_points, reason=f"Bounty for fixing bug {bug.id}")
        session.add(log)
    session.commit()
    update_user_stats(session, user_uuid)
    session.close()
    return jsonify({'message': 'Bug resolved, bounty awarded'}), 200

@community_bp.route('/bounties', methods=['GET'])
def list_bounties():
    session = get_db_session()
    bounties = session.query(Bounty).filter_by(status=BountyStatus.OPEN).order_by(Bounty.created_at.desc()).all()
    session.close()
    return jsonify([{
        'id': str(b.id),
        'title': b.title,
        'description': b.description,
        'points_reward': b.points_reward,
        'creator_id': str(b.creator_id),
        'created_at': b.created_at.isoformat()
    } for b in bounties])

@community_bp.route('/bounties', methods=['POST'])
def create_bounty():
    data = request.get_json()
    required = ['creator_id', 'title', 'description', 'points_reward']
    if not all(k in data for k in required):
        return jsonify({'error': 'missing fields'}), 400
    try:
        creator_uuid = uuid.UUID(data['creator_id'])
    except:
        return jsonify({'error': 'invalid creator_id'}), 400
    points_reward = int(data['points_reward'])
    if points_reward < 0:
        return jsonify({'error': 'points_reward must be non-negative'}), 400
    session = get_db_session()
    user = get_user_points(session, creator_uuid)
    if user.balance < points_reward:
        session.close()
        return jsonify({'error': 'Insufficient points to create bounty'}), 400
    user.balance -= points_reward
    bounty = Bounty(
        creator_id=creator_uuid,
        title=data['title'],
        description=data['description'],
        points_reward=points_reward,
        status=BountyStatus.OPEN
    )
    session.add(bounty)
    session.commit()
    update_user_stats(session, creator_uuid)
    session.close()
    return jsonify({'message': 'Bounty created', 'id': str(bounty.id)}), 201

@community_bp.route('/bounties/<bounty_id>/claim', methods=['POST'])
def claim_bounty(bounty_id):
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    try:
        bounty_uuid = uuid.UUID(bounty_id)
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid UUID'}), 400
    session = get_db_session()
    bounty = session.query(Bounty).filter_by(id=bounty_uuid).first()
    if not bounty or bounty.status != BountyStatus.OPEN:
        session.close()
        return jsonify({'error': 'Bounty not found or not open'}), 404
    bounty.status = BountyStatus.CLAIMED
    bounty.claimed_by = user_uuid
    bounty.claimed_at = datetime.utcnow()
    session.commit()
    update_user_stats(session, user_uuid)
    session.close()
    return jsonify({'message': 'Bounty claimed'}), 200

@community_bp.route('/bounties/<bounty_id>/complete', methods=['POST'])
def complete_bounty(bounty_id):
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    try:
        bounty_uuid = uuid.UUID(bounty_id)
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid UUID'}), 400
    session = get_db_session()
    bounty = session.query(Bounty).filter_by(id=bounty_uuid).first()
    if not bounty or bounty.status != BountyStatus.CLAIMED or bounty.claimed_by != user_uuid:
        session.close()
        return jsonify({'error': 'Bounty not claimed by you or not claimable'}), 400
    user = get_user_points(session, user_uuid)
    user.balance += bounty.points_reward
    user.lifetime_earned += bounty.points_reward
    from core.models.points import RewardLog
    log = RewardLog(user_id=user_uuid, amount=bounty.points_reward, reason=f"Completed bounty: {bounty.title}")
    session.add(log)
    bounty.status = BountyStatus.COMPLETED
    bounty.completed_at = datetime.utcnow()
    session.commit()
    update_user_stats(session, user_uuid)
    session.close()
    return jsonify({'message': 'Bounty completed, points awarded'}), 200

@community_bp.route('/stats/<user_id>', methods=['GET'])
def get_user_stats(user_id):
    try:
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid user_id'}), 400
    session = get_db_session()
    stats = session.query(UserCommunityStats).filter_by(user_id=user_uuid).first()
    if not stats:
        stats = UserCommunityStats(user_id=user_uuid)
    session.close()
    return jsonify({
        'bugs_reported': stats.bugs_reported,
        'bugs_fixed': stats.bugs_fixed,
        'bounties_claimed': stats.bounties_claimed,
        'bounties_completed': stats.bounties_completed,
        'reputation_score': stats.reputation_score,
        'level': stats.level,
        'badges': stats.badges
    })
