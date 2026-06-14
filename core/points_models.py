# Add this at the end of core/points_models.py
def award_points_for_commit(user_id: str, message: str, final_score: int = None):
    """Award points to a user for a TVC commit."""
    from flask import current_app
    from datetime import datetime
    
    # Use default 10 points; can scale with final_score if available
    points = final_score // 10 if final_score else 10
    
    with current_app.app_context():
        user = UserPoints.query.filter_by(user_id=user_id).first()
        if not user:
            user = UserPoints(user_id=user_id, balance=0, lifetime_earned=0)
            db.session.add(user)
        user.balance += points
        user.lifetime_earned += points
        log = RewardLog(
            user_id=user_id,
            amount=points,
            reason=f"Commit: {message[:50]}",
            transaction_type=TransactionType.MINT
        )
        db.session.add(log)
        db.session.commit()
    return points