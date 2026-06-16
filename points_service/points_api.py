from flask import Blueprint, request, jsonify
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from core.models.points import Base, UserPoints, Stake, Proposal, Vote, RewardLog, ProposalStatus, VoteChoice
from core.models.community import NameRegistry
from datetime import datetime, timedelta
import uuid
import os
import re

points_bp = Blueprint('points', __name__, url_prefix='/api/points')

DOMAIN_EXTENSION = ".dst"

# Reserved names blocklist
RESERVED_NAMES = {
    'google', 'facebook', 'meta', 'instagram', 'whatsapp', 'twitter', 'x', 'tiktok',
    'youtube', 'microsoft', 'apple', 'amazon', 'netflix', 'linkedin', 'snapchat',
    'reddit', 'pinterest', 'discord', 'telegram', 'signal', 'wechat', 'line',
    'github', 'gitlab', 'bitbucket', 'stackoverflow', 'medium', 'wordpress',
    'binance', 'coinbase', 'kraken', 'gemini', 'crypto', 'bitcoin', 'ethereum',
    'solana', 'ripple', 'cardano', 'dogecoin', 'litecoin', 'tether', 'usdc',
    'metamask', 'phantom', 'trustwallet', 'ledger', 'trezor', 'uniswap',
    'pancakeswap', 'opensea', 'blur', 'looksrare', 'rarible', 'foundation',
    'paypal', 'stripe', 'square', 'venmo', 'cashapp', 'wise', 'revolut',
    'admin', 'administrator', 'root', 'support', 'help', 'security', 'moderator',
    'mod', 'owner', 'ceo', 'founder', 'official', 'system', 'service', 'info',
    'contact', 'abuse', 'legal', 'privacy', 'terms', 'dmca', 'copyright',
    'trademark', 'patent', 'law', 'attorney', 'lawyer', 'court', 'police', 'fbi',
    'cia', 'nsa', 'homeland', 'irs', 'treasury', 'whitehouse', 'congress',
    'localhost', 'example', 'test', 'demo', 'sandbox', 'staging', 'prod',
    'production', 'development', 'internal', 'private', 'public', 'api',
    'dashboard', 'login', 'signup', 'register', 'account', 'profile', 'settings',
    'billing', 'payment', 'checkout', 'cart', 'order', 'invoice',
    # Add offensive terms if you wish
    'dstreet', 'digitalstreet', 'toonedoutframes', 'toonoutframes', 'store',
}

def is_reserved(name):
    return name.lower() in RESERVED_NAMES

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

@points_bp.route('/username/<identifier>', methods=['GET'])
def get_user_by_username(identifier):
    session = get_db_session()
    try:
        user_uuid = uuid.UUID(identifier)
        user = session.query(UserPoints).filter_by(user_id=user_uuid).first()
    except:
        user = session.query(UserPoints).filter_by(username=identifier).first()
    if not user:
        session.close()
        return jsonify({'error': 'User not found'}), 404
    session.close()
    return jsonify({'user_id': str(user.user_id), 'username': user.username, 'balance': user.balance})

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
    stake_id = str(stake.id)
    session.close()
    return jsonify({
        'message': f'Staked {amount} points until {locked_until}',
        'apy': apy,
        'stake_id': stake_id
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

# ------------------ Username management ------------------
@points_bp.route('/username', methods=['POST'])
def set_username():
    data = request.get_json()
    user_id = data.get('user_id')
    username = data.get('username')
    if not user_id or not username:
        return jsonify({'error': 'user_id and username required'}), 400
    try:
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid user_id'}), 400
    session = get_db_session()
    user = get_user_points(session, user_uuid)
    existing = session.query(UserPoints).filter(UserPoints.username == username, UserPoints.user_id != user.user_id).first()
    if existing:
        session.close()
        return jsonify({'error': 'Username already taken'}), 409
    user.username = username
    session.commit()
    session.close()
    return jsonify({'message': 'Username set', 'username': username}), 200

@points_bp.route('/resolve/<identifier>', methods=['GET'])
def resolve_user(identifier):
    session = get_db_session()
    try:
        user_uuid = uuid.UUID(identifier)
        user = session.query(UserPoints).filter_by(user_id=user_uuid).first()
    except:
        user = session.query(UserPoints).filter_by(username=identifier).first()
    if not user:
        session.close()
        return jsonify({'error': 'User not found'}), 404
    session.close()
    return jsonify({'user_id': str(user.user_id), 'username': user.username, 'balance': user.balance})

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

# ------------------ Governance ------------------
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
    proposal_id = str(proposal.id)
    session.close()
    return jsonify({'message': 'Proposal created', 'id': proposal_id}), 201

@points_bp.route('/governance/vote', methods=['POST'])
def vote():
    data = request.get_json()
    user_id = data.get('user_id')
    proposal_id = data.get('proposal_id')
    choice = data.get('choice')
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

# ---------- Name Registry ----------
@points_bp.route('/names/check/<name>', methods=['GET'])
def check_name_availability(name):
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', name):
        return jsonify({'error': 'Name must be 3-20 alphanumeric characters or underscores'}), 400
    session = get_db_session()
    existing = session.query(NameRegistry).filter_by(name=name, active=True).first()
    if existing and existing.expires_at > datetime.utcnow():
        session.close()
        return jsonify({'available': False, 'expires_at': existing.expires_at.isoformat()})
    cost_per_year = 100
    session.close()
    return jsonify({'available': True, 'cost_per_year': cost_per_year})

@points_bp.route('/names/register', methods=['POST'])
def register_name():
    data = request.get_json()
    user_id = data.get('user_id')
    name = data.get('name')
    years = int(data.get('years', 1))
    expiry_date = expires_at.strftime('%Y-%m-%d')
    lease_message = f"Name registered. You own '{name}{DOMAIN_EXTENSION}' until {expiry_date}. Renew before expiry to keep it. After expiry, the name becomes available to others."


    if not user_id or not name:
        return jsonify({'error': 'user_id and name required'}), 400
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', name):
        return jsonify({'error': 'Name must be 3-20 alphanumeric characters or underscores'}), 400
    if years < 1 or years > 10:
        return jsonify({'error': 'Years must be between 1 and 10'}), 400
    if is_reserved(name):
        return jsonify({'error': 'This name is reserved and cannot be registered'}), 403

    try:
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid user_id'}), 400

    session = get_db_session()
    existing = session.query(NameRegistry).filter_by(name=name, active=True).first()
    if existing and existing.expires_at > datetime.utcnow():
        session.close()
        return jsonify({'error': 'Name already registered'}), 409

    cost_per_year = 100
    total_cost = cost_per_year * years
    user = get_user_points(session, user_uuid)
    if user.balance < total_cost:
        session.close()
        return jsonify({'error': f'Insufficient points. Need {total_cost} points'}), 400

    user.balance -= total_cost
    user.lifetime_earned += total_cost
    expires_at = datetime.utcnow() + timedelta(days=365 * years)

    if existing:
        existing.active = True
        existing.owner_id = user_uuid
        existing.expires_at = expires_at
        existing.cost_points = total_cost
        existing.verified = False   # re‑registration resets verification
    else:
        registry = NameRegistry(
            name=name,
            owner_id=user_uuid,
            expires_at=expires_at,
            cost_points=total_cost,
            verified=False           # explicitly set
        )
        session.add(registry)

    log = RewardLog(user_id=user_uuid, amount=-total_cost, reason=f"Registered name '{name}' for {years} years")
    session.add(log)
    session.commit()
    session.close()

    return jsonify({
        'message': lease_message,
        'name': name,
        'domain': f"{name}{DOMAIN_EXTENSION}",
        'expires_at': expires_at.isoformat()
    }), 201

@points_bp.route('/names/dispute', methods=['POST'])
def dispute_name():
    """
    Allow a trademark owner to dispute a name registration.
    Body: { "name": "alice", "claimant_email": "legal@example.com", "evidence": "trademark number XYZ" }
    """
    data = request.get_json()
    name = data.get('name')
    claimant_email = data.get('claimant_email')
    evidence = data.get('evidence')
    if not name or not claimant_email:
        return jsonify({'error': 'name and claimant_email required'}), 400
    
    session = get_db_session()
    registry = session.query(NameRegistry).filter_by(name=name, active=True).first()
    if not registry or registry.expires_at < datetime.utcnow():
        session.close()
        return jsonify({'error': 'Name not found or expired'}), 404
    
    # In production, store the dispute in a new table (e.g., `name_disputes`).
    # For now, write to a JSON log file.
    import json
    dispute_record = {
        'name': name,
        'claimant_email': claimant_email,
        'evidence': evidence,
        'current_owner': str(registry.owner_id),
        'registered_at': registry.registered_at.isoformat(),
        'disputed_at': datetime.utcnow().isoformat()
    }
    disputes_dir = 'data/disputes'
    os.makedirs(disputes_dir, exist_ok=True)
    dispute_file = os.path.join(disputes_dir, f"{name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")
    with open(dispute_file, 'w') as f:
        json.dump(dispute_record, f, indent=2)
    session.close()
    
    # Optional: send email notification to admin
    print(f"📧 Dispute filed for name '{name}' by {claimant_email}. Evidence: {evidence}")
    
    return jsonify({'message': 'Dispute recorded. An administrator will review it.'}), 201

@points_bp.route('/names/verify/<name>', methods=['POST'])
def verify_name(name):
    # Simple admin check – replace with proper auth later
    admin_key = request.headers.get('X-Admin-Key')
    if admin_key != 'your-secret-admin-key':
        return jsonify({'error': 'Unauthorized'}), 401
    
    session = get_db_session()
    registry = session.query(NameRegistry).filter_by(name=name, active=True).first()
    if not registry or registry.expires_at < datetime.utcnow():
        session.close()
        return jsonify({'error': 'Name not found or expired'}), 404
    registry.verified = True
    session.commit()
    session.close()
    return jsonify({'message': f'Name {name} verified'}), 200

@points_bp.route('/names/renew', methods=['POST'])
def renew_name():
    data = request.get_json()
    user_id = data.get('user_id')
    name = data.get('name')
    years = int(data.get('years', 1))
    if not user_id or not name:
        return jsonify({'error': 'user_id and name required'}), 400
    try:
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid user_id'}), 400
    if years < 1 or years > 10:
        return jsonify({'error': 'Years must be between 1 and 10'}), 400
    session = get_db_session()
    registry = session.query(NameRegistry).filter_by(name=name, active=True).first()
    if not registry or registry.expires_at < datetime.utcnow():
        session.close()
        return jsonify({'error': 'Name not found or expired'}), 404
    if registry.owner_id != user_uuid:
        session.close()
        return jsonify({'error': 'You do not own this name'}), 403
    cost_per_year = 100
    total_cost = cost_per_year * years
    user = get_user_points(session, user_uuid)
    if user.balance < total_cost:
        session.close()
        return jsonify({'error': f'Insufficient points. Need {total_cost} points'}), 400
    user.balance -= total_cost
    user.lifetime_earned += total_cost
    registry.expires_at += timedelta(days=365 * years)
    registry.cost_points += total_cost
    log = RewardLog(user_id=user_uuid, amount=-total_cost, reason=f"Renewed name '{name}' for {years} years")
    session.add(log)
    session.commit()
    session.close()
    return jsonify({'message': 'Name renewed', 'name': name, 'new_expiry': registry.expires_at.isoformat()})

@points_bp.route('/names/transfer', methods=['POST'])
def transfer_name():
    data = request.get_json()
    name = data.get('name')
    from_user_id = data.get('from_user_id')
    to_user_id = data.get('to_user_id')
    if not all([name, from_user_id, to_user_id]):
        return jsonify({'error': 'name, from_user_id, to_user_id required'}), 400
    try:
        from_uuid = uuid.UUID(from_user_id)
        to_uuid = uuid.UUID(to_user_id)
    except:
        return jsonify({'error': 'invalid user_id'}), 400
    session = get_db_session()
    registry = session.query(NameRegistry).filter_by(name=name, active=True).first()
    if not registry or registry.expires_at < datetime.utcnow():
        session.close()
        return jsonify({'error': 'Name not found or expired'}), 404
    if registry.owner_id != from_uuid:
        session.close()
        return jsonify({'error': 'You do not own this name'}), 403
    transfer_fee = 10
    from_user = get_user_points(session, from_uuid)
    if from_user.balance < transfer_fee:
        session.close()
        return jsonify({'error': f'Insufficient points for transfer fee ({transfer_fee})'}), 400
    from_user.balance -= transfer_fee
    registry.owner_id = to_uuid
    log = RewardLog(user_id=from_uuid, amount=-transfer_fee, reason=f"Transferred name '{name}' to {to_uuid}")
    session.add(log)
    session.commit()
    session.close()
    return jsonify({'message': 'Name transferred', 'name': name, 'new_owner': str(to_uuid)})

@points_bp.route('/names/resolve/<name>', methods=['GET'])
def resolve_name(name):
    session = get_db_session()
    registry = session.query(NameRegistry).filter_by(name=name, active=True).first()
    if not registry or registry.expires_at < datetime.utcnow():
        session.close()
        return jsonify({'error': 'Name not found or expired'}), 404
    owner = session.query(UserPoints).filter_by(user_id=registry.owner_id).first()
    session.close()
    return jsonify({
        'name': registry.name,
        'domain': f"{registry.name}{DOMAIN_EXTENSION}",
        'owner_id': str(registry.owner_id),
        'username': owner.username if owner else None,
        'expires_at': registry.expires_at.isoformat(),
        'resource': registry.resource
    })


@points_bp.route('/names/resource/<name>', methods=['POST'])
def set_name_resource(name):
    """Set a resource (URL, IPFS, etc.) for a owned name."""
    data = request.get_json()
    user_id = data.get('user_id')
    resource = data.get('resource')
    if not user_id or not resource:
        return jsonify({'error': 'user_id and resource required'}), 400
    try:
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid user_id'}), 400
    session = get_db_session()
    registry = session.query(NameRegistry).filter_by(name=name, active=True).first()
    if not registry or registry.expires_at < datetime.utcnow():
        session.close()
        return jsonify({'error': 'Name not found or expired'}), 404
    if registry.owner_id != user_uuid:
        session.close()
        return jsonify({'error': 'You do not own this name'}), 403
    registry.resource = resource
    session.commit()
    session.close()
    return jsonify({
        'message': f'Resource for {name}{DOMAIN_EXTENSION} updated',
        'resource': resource
    }), 200

@points_bp.route('/names/redirect/<name>', methods=['GET'])
def redirect_domain(name):
    """Redirect to the resource associated with a name."""
    session = get_db_session()
    registry = session.query(NameRegistry).filter_by(name=name, active=True).first()
    session.close()
    if not registry or registry.expires_at < datetime.utcnow():
        return "Domain not found or expired", 404
    if registry.resource:
        if registry.resource.startswith(('http://', 'https://', 'ipfs://', 'ipns://')):
            return redirect(registry.resource)
        else:
            return f"Resource for {name}{DOMAIN_EXTENSION}: {registry.resource}", 200
    return f"No resource set for {name}{DOMAIN_EXTENSION}", 200

@points_bp.route('/names/owned/<user_id>', methods=['GET'])
def list_owned_names(user_id):
    try:
        user_uuid = uuid.UUID(user_id)
    except:
        return jsonify({'error': 'invalid user_id'}), 400
    session = get_db_session()
    names = session.query(NameRegistry).filter_by(owner_id=user_uuid, active=True).filter(NameRegistry.expires_at > datetime.utcnow()).all()
    session.close()
    return jsonify([{
        'name': n.name,
        'registered_at': n.registered_at.isoformat(),
        'expires_at': n.expires_at.isoformat(),
        'cost_points': n.cost_points
    } for n in names])
