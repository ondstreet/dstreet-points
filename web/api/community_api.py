from flask import Blueprint, request, jsonify
from sqlalchemy import func
from points_service.points_api import get_db_session, get_user_points
from core.models.community import BugReport, Bounty, UserCommunityStats, BugStatus, BountyStatus
from datetime import datetime
import uuid

community_bp = Blueprint('community', __name__, url_prefix='/api/community')

def update_user_stats(session, user_id):
    """Recalc or update user stats for community."""
    stats = session.query(UserCommunityStats).filter_by(user_id=user_id).first()
    if not stats:
        stats = UserCommunityStats(user_id=user_id)
        session.add(stats)
    # Count bugs reported by user
    reported = session.query(BugReport).filter_by(user_id=user_id).count()
    # Count bugs fixed by user
    fixed = session.query(BugReport).filter_by(fixed_by=user_id, status=BugStatus.FIXED).count()
    # Bounties claimed and completed
    claimed = session.query(Bounty).filter_by(claimed_by=user_id).count()
    completed = session.query(Bounty).filter_by(claimed_by=user_id, status=BountyStatus.COMPLETED).count()
    stats.bugs_reported = reported
    stats.bugs_fixed = fixed
    stats.bounties_claimed = claimed
    stats.bounties_completed = completed
    # Reputation could be sum of bounty points earned
    # For simplicity, we'll update on bounty completion separately
    session.commit()
    return stats

# ---------- Bug Reports ----------
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
    # Check if user exists in points system (create if not)
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
    # Update stats
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
    if not bug:
        session.close()
        return jsonify({'error': 'Bug not found'}), 404
    if bug.status != BugStatus.OPEN:
        session.close()
        return jsonify({'error': f'Bug already {bug.status.value}'}), 400
    # Optionally require the user to have enough points or just allow
    bug.status = BugStatus.CLAIMED
    bug.fixed_by = user_uuid
    session.commit()
    # Update stats
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
    if not bug:
        session.close()
        return jsonify({'error': 'Bug not found'}), 404
    if bug.status != BugStatus.CLAIMED or bug.fixed_by != user_uuid:
        session.close()
        return jsonify({'error': 'Bug not claimed by you or not claimed'}), 400
    bug.status = BugStatus.FIXED
    bug.resolved_at = datetime.utcnow()
    # Award bounty points to the fixer
    if bug.bounty_points > 0:
        user = get_user_points(session, user_uuid)
        user.balance += bug.bounty_points
        user.lifetime_earned += bug.bounty_points
        from core.models.points import RewardLog  # adjust import if needed
        log = RewardLog(user_id=user_uuid, amount=bug.bounty_points, reason=f"Bounty for fixing bug {bug.id}")
        session.add(log)
    session.commit()
    update_user_stats(session, user_uuid)
    session.close()
    return jsonify({'message': 'Bug resolved, bounty awarded'}), 200

# ---------- Bounties ----------
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
    # Check if creator has enough points (if points_reward > 0)
    session = get_db_session()
    user = get_user_points(session, creator_uuid)
    points_reward = int(data['points_reward'])
    if points_reward < 0:
        session.close()
        return jsonify({'error': 'points_reward must be non-negative'}), 400
    if user.balance < points_reward:
        session.close()
        return jsonify({'error': 'Insufficient points to create this bounty'}), 400
    # Reserve points by deducting them? Or deduct only when claimed/completed? We'll deduct at creation.
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
    # Award points to the claimer (points already deducted from creator, now add to claimer)
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

# ---------- User Stats ----------
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