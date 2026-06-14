# points_service/points_api.py
from flask import Blueprint, request, jsonify
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from core.models.points import Base, UserPoints, Stake, Proposal, Vote, RewardLog, ProposalStatus, VoteChoice
from datetime import datetime, timedelta
import uuid
import os

points_bp = Blueprint('points', __name__, url_prefix='/api/points')

# Database setup
def get_db_session():
    db_path = os.path.join(os.getcwd(), 'data', 'points.db')
    engine = create_engine(f'sqlite:///{db_path}')
    Session = sessionmaker(bind=engine)
    return Session()

def get_user_points(session, user_id):
    user = session.query(UserPoints).filter_by(user_id=user_id).first()
    if not user:
        user = UserPoints(user_id=user_id, balance=0, lifetime_earned=0)
        session.add(user)
        session.commit()
    return user

# ------------------ Balance ------------------
@points_bp.route('/balance', methods=['GET'])
def balance():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    try:
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid user_id'}), 400

    session = get_db_session()
    user = get_user_points(session, user_uuid)
    session.close()
    return jsonify({
        'balance': user.balance,
        'lifetime_earned': user.lifetime_earned,
        'last_claim': user.last_claim.isoformat() if user.last_claim else None
    })

# ------------------ Stake ------------------
@points_bp.route('/stake', methods=['POST'])
def stake():
    data = request.get_json()
    user_id = data.get('user_id')
    amount = data.get('amount')
    days = data.get('days', 30)
    if not user_id or not amount or amount <= 0:
        return jsonify({'error': 'user_id and positive amount required'}), 400
    try:
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid user_id'}), 400

    session = get_db_session()
    user = get_user_points(session, user_uuid)
    if user.balance < amount:
        session.close()
        return jsonify({'error': 'Insufficient balance'}), 400

    apy = 5.0 + (days // 30) * 1.0
    locked_until = datetime.utcnow() + timedelta(days=days)

    stake = Stake(user_id=user_uuid, amount=amount, locked_until=locked_until, apy=apy)
    user.balance -= amount
    log = RewardLog(user_id=user_uuid, amount=-amount, reason=f"Staked {amount} points for {days} days")
    session.add(stake)
    session.add(log)
    session.commit()

    stake_id = str(stake.id)          # <-- ADDED
    session.close()

    return jsonify({
        'message': f'Staked {amount} points until {locked_until}',
        'apy': apy,
        'stake_id': stake_id          # <-- ADDED
    })

# ------------------ Unstake ------------------
@points_bp.route('/unstake', methods=['POST'])
def unstake():
    data = request.get_json()
    user_id = data.get('user_id')
    stake_id = data.get('stake_id')
    if not user_id or not stake_id:
        return jsonify({'error': 'user_id and stake_id required'}), 400
    try:
        user_uuid = uuid.UUID(user_id)
        stake_uuid = uuid.UUID(stake_id)
    except:
        return jsonify({'error': 'invalid UUID'}), 400

    session = get_db_session()
    stake = session.query(Stake).filter_by(id=stake_uuid, user_id=user_uuid).first()
    if not stake:
        session.close()
        return jsonify({'error': 'Stake not found'}), 404
    if stake.locked_until > datetime.utcnow():
        session.close()
        return jsonify({'error': 'Stake is still locked'}), 400

    locked_days = (stake.locked_until - stake.created_at).days
    reward = stake.amount * (stake.apy / 100) * (locked_days / 365)
    total_return = stake.amount + reward

    user = get_user_points(session, user_uuid)
    user.balance += total_return
    user.lifetime_earned += reward
    session.delete(stake)
    log = RewardLog(user_id=user_uuid, amount=reward, reason=f"Unstaked {stake.amount} points, earned {reward} reward")
    session.add(log)
    session.commit()
    session.close()
    return jsonify({'message': f'Unstaked {stake.amount} points + {reward} reward', 'total': total_return})

# ------------------ History ------------------
@points_bp.route('/history', methods=['GET'])
def history():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    try:
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid user_id'}), 400

    session = get_db_session()
    logs = session.query(RewardLog).filter_by(user_id=user_uuid).order_by(RewardLog.timestamp.desc()).limit(50).all()
    session.close()
    return jsonify([{
        'amount': log.amount,
        'reason': log.reason,
        'timestamp': log.timestamp.isoformat()
    } for log in logs])

# ------------------ Proposals ------------------
@points_bp.route('/governance/proposals', methods=['GET'])
def list_proposals():
    session = get_db_session()
    proposals = session.query(Proposal).filter(Proposal.ends_at > datetime.utcnow()).all()
    session.close()
    return jsonify([{
        'id': str(p.id),
        'title': p.title,
        'description': p.description,
        'creator_id': str(p.creator_id),
        'ends_at': p.ends_at.isoformat(),
        'voting_power_yes': p.voting_power_yes,
        'voting_power_no': p.voting_power_no
    } for p in proposals])

@points_bp.route('/governance/proposals', methods=['POST'])
def create_proposal():
    data = request.get_json()
    user_id = data.get('creator_id')
    title = data.get('title')
    description = data.get('description')
    duration_hours = data.get('duration_hours', 72)
    if not user_id or not title or not description:
        return jsonify({'error': 'creator_id, title, description required'}), 400
    try:
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid user_id'}), 400

    ends_at = datetime.utcnow() + timedelta(hours=duration_hours)
    proposal = Proposal(title=title, description=description, creator_id=user_uuid, ends_at=ends_at)
    session = get_db_session()
    session.add(proposal)
    session.commit()
    proposal_id = str(proposal.id)   # <-- ADDED
    session.close()
    return jsonify({'message': 'Proposal created', 'id': proposal_id}), 201

@points_bp.route('/governance/vote', methods=['POST'])
def vote():
    data = request.get_json()
    user_id = data.get('user_id')
    proposal_id = data.get('proposal_id')
    choice = data.get('choice')  # 'yes' or 'no'
    if not user_id or not proposal_id or choice not in ('yes', 'no'):
        return jsonify({'error': 'user_id, proposal_id, choice (yes/no) required'}), 400
    try:
        user_uuid = uuid.UUID(user_id)
        proposal_uuid = uuid.UUID(proposal_id)
    except:
        return jsonify({'error': 'invalid UUID'}), 400

    session = get_db_session()
    proposal = session.query(Proposal).filter_by(id=proposal_uuid).first()
    if not proposal or proposal.ends_at < datetime.utcnow():
        session.close()
        return jsonify({'error': 'Proposal not active'}), 400

    existing = session.query(Vote).filter_by(proposal_id=proposal_uuid, user_id=user_uuid).first()
    if existing:
        session.close()
        return jsonify({'error': 'Already voted'}), 400

    stakes = session.query(Stake).filter_by(user_id=user_uuid).all()
    voting_power = sum(s.amount for s in stakes)
    if voting_power <= 0:
        session.close()
        return jsonify({'error': 'You need to stake points to vote'}), 400

    vote = Vote(proposal_id=proposal_uuid, user_id=user_uuid,
                choice=VoteChoice.YES if choice == 'yes' else VoteChoice.NO,
                voting_power=voting_power)
    if choice == 'yes':
        proposal.voting_power_yes += voting_power
    else:
        proposal.voting_power_no += voting_power
    session.add(vote)

    user = get_user_points(session, user_uuid)
    user.balance += 5
    user.lifetime_earned += 5
    log = RewardLog(user_id=user_uuid, amount=5, reason=f"Voted on proposal {proposal_id}")
    session.add(log)
    session.commit()
    session.close()
    return jsonify({'message': 'Vote recorded', 'voting_power': voting_power})

# ------------------ Treasury Status ------------------
@points_bp.route('/treasury/status', methods=['GET'])
def treasury_status():
    session = get_db_session()
    total_supply = session.query(func.sum(UserPoints.balance)).scalar() or 0
    total_staked = session.query(func.sum(Stake.amount)).scalar() or 0
    active_proposals = session.query(Proposal).filter(Proposal.ends_at > datetime.utcnow()).count()
    session.close()
    return jsonify({
        'total_supply': total_supply,
        'total_staked': total_staked,
        'active_proposals': active_proposals
    })

@points_bp.route('/branches/map', methods=['GET'])
def branch_map():
    branches = []
    for b in os.listdir('.tvc/refs/heads/'):
        commit_hash = open(f'.tvc/refs/heads/{b}').read().strip()
        tree = tvc._get_tree_from_commit(commit_hash)
        file_count = len(tree) if tree else 0
        branches.append({'name': b, 'commit': commit_hash, 'file_count': file_count, 'current': b == tvc._get_current_branch()})
    return jsonify(branches)