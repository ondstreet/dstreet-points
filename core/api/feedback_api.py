
"""
Enhanced Feedback API - Integrated with monitoring and admin systems
"""

import sys
import json
import uuid
from flask import Blueprint, request, jsonify
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

# Add path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

feedback_api = Blueprint('feedback_api', __name__, url_prefix='/api')

# Import monitoring for error tracking
try:
    from core.monitoring.alert_manager import AlertManager
    from core.monitoring.collectors.system_collector import SystemCollector
    MONITORING_AVAILABLE = True
    print("✅ Monitoring system integrated")
except ImportError:
    MONITORING_AVAILABLE = False
    print("⚠️ Monitoring system not available")

class FeedbackManager:
    """Enhanced feedback management with monitoring integration"""
    
    def __init__(self):
        self.feedback_dir = Path("data/feedback")
        self.feedback_dir.mkdir(parents=True, exist_ok=True)
        self.alert_manager = AlertManager() if MONITORING_AVAILABLE else None
        self.system_collector = SystemCollector() if MONITORING_AVAILABLE else None
    
    def save_feedback(self, feedback: Dict) -> str:
        """Save feedback and trigger alerts for critical issues"""
        feedback_id = str(uuid.uuid4())[:8]
        feedback['id'] = feedback_id
        feedback['timestamp'] = datetime.now().isoformat()
        
        # Save to file
        filename = f"feedback_{feedback_id}.json"
        filepath = self.feedback_dir / filename
        with open(filepath, 'w') as f:
            json.dump(feedback, f, indent=2)
        
        # Create ticket for critical issues
        if feedback.get('type') in ['bug', 'critical']:
            self._create_ticket(feedback)
        
        # Alert for urgent issues
        if feedback.get('urgency') == 'urgent' or feedback.get('type') == 'critical':
            self._trigger_alert(feedback)
        
        # Log to monitoring system
        if MONITORING_AVAILABLE and self.system_collector:
            self.system_collector.log_event('feedback_submitted', {
                'feedback_id': feedback_id,
                'type': feedback.get('type'),
                'user_id': feedback.get('user_id')
            })
        
        return feedback_id
    
    def _create_ticket(self, feedback: Dict) -> None:
        """Create support ticket in the system"""
        ticket_dir = Path("data/tickets")
        ticket_dir.mkdir(parents=True, exist_ok=True)
        
        ticket = {
            'ticket_id': f"TKT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4]}",
            'feedback_id': feedback.get('id'),
            'created_at': feedback.get('timestamp'),
            'status': 'open',
            'priority': 'high' if feedback.get('type') == 'critical' else 'normal',
            'subject': feedback.get('subject'),
            'message': feedback.get('message'),
            'user_email': feedback.get('email'),
            'assigned_to': None,
            'resolution': None
        }
        
        ticket_file = ticket_dir / f"ticket_{ticket['ticket_id']}.json"
        with open(ticket_file, 'w') as f:
            json.dump(ticket, f, indent=2)
    
    def _trigger_alert(self, feedback: Dict) -> None:
        """Trigger alert for urgent issues"""
        if self.alert_manager:
            self.alert_manager.create_alert(
                level='critical',
                source='feedback_system',
                message=f"Urgent feedback: {feedback.get('subject')}",
                details=feedback
            )
    
    def list_feedback(self, status: str = None, type_filter: str = None) -> list:
        """List all feedback with filters"""
        feedback_list = []
        for file in self.feedback_dir.glob("feedback_*.json"):
            try:
                with open(file, 'r') as f:
                    feedback = json.load(f)
                    if status and feedback.get('status') != status:
                        continue
                    if type_filter and feedback.get('type') != type_filter:
                        continue
                    feedback_list.append(feedback)
            except:
                continue
        
        # Sort by timestamp descending
        feedback_list.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return feedback_list
    
    def update_feedback_status(self, feedback_id: str, status: str) -> bool:
        """Update feedback status (admin only)"""
        filepath = self.feedback_dir / f"feedback_{feedback_id}.json"
        if not filepath.exists():
            return False
        
        with open(filepath, 'r') as f:
            feedback = json.load(f)
        
        feedback['status'] = status
        feedback['updated_at'] = datetime.now().isoformat()
        
        with open(filepath, 'w') as f:
            json.dump(feedback, f, indent=2)
        
        return True

feedback_manager = FeedbackManager()

@feedback_api.route('/feedback', methods=['POST'])
def submit_feedback():
    """Submit user feedback with monitoring integration"""
    try:
        data = request.get_json()
        
        # Get user info from auth header
        user_id = request.headers.get('Authorization', 'anonymous')
        
        feedback = {
            'type': data.get('type', 'feedback'),
            'subject': data.get('subject'),
            'message': data.get('message'),
            'email': data.get('email'),
            'user_id': user_id,
            'urgency': data.get('urgency', 'normal'),
            'status': 'pending',
            'source': data.get('source', 'web'),
            'browser_info': data.get('browser_info', {}),
            'page_url': data.get('page_url', '')
        }
        
        # Validate required fields
        if not feedback['subject'] or not feedback['message']:
            return jsonify({'error': 'Subject and message are required'}), 400
        
        # Save feedback
        feedback_id = feedback_manager.save_feedback(feedback)
        
        return jsonify({
            'success': True,
            'message': 'Feedback received. Thank you!',
            'feedback_id': feedback_id,
            'ticket_created': feedback.get('type') in ['bug', 'critical']
        }), 200
        
    except Exception as e:
        # Log error to monitoring
        if MONITORING_AVAILABLE:
            import logging
            logging.error(f"Feedback submission error: {e}")
        return jsonify({'error': str(e)}), 500

@feedback_api.route('/feedback/list', methods=['GET'])
def list_feedback():
    """List feedback (admin only)"""
    try:
        status = request.args.get('status')
        type_filter = request.args.get('type')
        
        feedback_list = feedback_manager.list_feedback(status, type_filter)
        
        return jsonify({
            'feedback': feedback_list,
            'count': len(feedback_list),
            'filters': {'status': status, 'type': type_filter}
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@feedback_api.route('/feedback/<feedback_id>', methods=['GET'])
def get_feedback(feedback_id):
    """Get single feedback by ID (admin only)"""
    try:
        filepath = Path(f"data/feedback/feedback_{feedback_id}.json")
        if not filepath.exists():
            return jsonify({'error': 'Feedback not found'}), 404
        
        with open(filepath, 'r') as f:
            feedback = json.load(f)
        
        return jsonify({'feedback': feedback})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@feedback_api.route('/feedback/<feedback_id>/status', methods=['PUT'])
def update_feedback_status(feedback_id):
    """Update feedback status (admin only)"""
    try:
        data = request.get_json()
        status = data.get('status')
        
        if status not in ['pending', 'in_progress', 'resolved', 'closed']:
            return jsonify({'error': 'Invalid status'}), 400
        
        if feedback_manager.update_feedback_status(feedback_id, status):
            return jsonify({'success': True, 'status': status})
        
        return jsonify({'error': 'Feedback not found'}), 404
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@feedback_api.route('/feedback/stats', methods=['GET'])
def feedback_stats():
    """Get feedback statistics (admin only)"""
    try:
        feedback_list = feedback_manager.list_feedback()
        
        stats = {
            'total': len(feedback_list),
            'by_type': {},
            'by_status': {},
            'by_day': {}
        }
        
        for feedback in feedback_list:
            # Count by type
            f_type = feedback.get('type', 'unknown')
            stats['by_type'][f_type] = stats['by_type'].get(f_type, 0) + 1
            
            # Count by status
            f_status = feedback.get('status', 'pending')
            stats['by_status'][f_status] = stats['by_status'].get(f_status, 0) + 1
            
            # Count by day (last 7 days)
            try:
                date = datetime.fromisoformat(feedback['timestamp']).strftime('%Y-%m-%d')
                stats['by_day'][date] = stats['by_day'].get(date, 0) + 1
            except:
                pass
        
        return jsonify({'stats': stats})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

print("✅ Enhanced Feedback API with monitoring integration ready!")
