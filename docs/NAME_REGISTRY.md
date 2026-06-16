# $STORE Name Registry – Complete Documentation

A decentralised, points‑based name registry that allows users to register human‑readable names, pay a lease in $STORE points, and optionally point them to a resource (URL, IPFS hash, etc.). It includes expiry, renewal, transfer, verification, and a full frontend dashboard.

## Features

- **Register a name** (3‑20 alphanumeric + underscore) for 1–10 years at 100 points per year.
- **Renew** an owned name before expiry.
- **Transfer** ownership to another user (fee 10 points).
- **Resolve** a name to owner ID, expiry, and resource.
- **List all names** owned by a user.
- **Set a resource** (URL, IPFS, etc.) for a name.
- **Redirect endpoint** to serve the resource.
- **Admin verification** to mark names as verified (trademark protection).
- **Expiry cron job** – daily deactivation of expired names.
- **Dashboard UI** – availability check, registration, owned names, resolver widget.

## Database Model

Table: `name_registry`

| Column           | Type      | Description |
|------------------|-----------|-------------|
| id               | UUID      | Primary key |
| name             | String(50)| Unique, index |
| owner_id         | UUID      | Foreign key to `user_points.user_id` |
| registered_at    | DateTime  | When first registered |
| expires_at       | DateTime  | Lease end date |
| active           | Boolean   | Whether the name is still valid |
| cost_points      | Integer   | Total points paid (registration + renewals) |
| resource         | Text      | Optional URL, IPFS hash, etc. |
| verified         | Boolean   | Admin‑verified (trademark) |

## API Endpoints

Base URL: `/api/points/names`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/check/<name>` | Check availability and cost per year. |
| POST   | `/register`     | Register a name (costs points). |
| POST   | `/renew`        | Extend expiry (costs points). |
| POST   | `/transfer`     | Transfer to another user (fee 10 points). |
| GET    | `/resolve/<name>` | Get owner info, expiry, resource. |
| GET    | `/owned/<user_id>` | List names owned by a user. |
| POST   | `/resource/<name>` | Set/update the resource (requires ownership). |
| GET    | `/redirect/<name>` | Redirect to the resource. |
| POST   | `/verify/<name>`  | Admin verification (requires `X-Admin-Key`). |

### Example Requests

```bash
# Check availability
curl http://127.0.0.1:5000/api/points/names/check/alice

# Register (requires 100 points per year)
curl -X POST http://127.0.0.1:5000/api/points/names/register \
  -H "Content-Type: application/json" \
  -d '{"user_id":"your-uuid","name":"alice","years":1}'

# Set resource
curl -X POST http://127.0.0.1:5000/api/points/names/resource/alice \
  -H "Content-Type: application/json" \
  -d '{"user_id":"your-uuid","resource":"https://example.com"}'

# Resolve
curl http://127.0.0.1:5000/api/points/names/resolve/alice
Frontend Integration
Add to templates/points_dashboard.html:

html
<div class="card">
    <h2>🏷️ Name Registry</h2>
    <div>
        <input type="text" id="checkNameInput" placeholder="Check availability">
        <button onclick="checkAvailability()">Check</button>
        <span id="availabilityResult"></span>
    </div>
    <div>
        <input type="text" id="registerName" placeholder="Name">
        <input type="number" id="registerYears" value="1" min="1" max="10">
        <button onclick="registerName()">Register (costs points)</button>
    </div>
    <div>
        <button onclick="listMyNames()">List My Names</button>
        <pre id="myNamesList"></pre>
    </div>
</div>
Corresponding JavaScript (add to existing <script>):

javascript
async function checkAvailability() {
    const name = document.getElementById('checkNameInput').value.trim();
    if (!name) return;
    const res = await fetch(`/api/points/names/check/${name}`);
    const data = await res.json();
    const div = document.getElementById('availabilityResult');
    if (res.ok && data.available)
        div.innerHTML = `✅ Available! Cost: ${data.cost_per_year} points/year`;
    else if (res.ok && !data.available)
        div.innerHTML = `❌ Taken until ${new Date(data.expires_at).toLocaleDateString()}`;
    else
        div.innerHTML = `❌ ${data.error}`;
}

async function registerName() {
    const userId = getUserId(); // implement getUserId() to read from input
    const name = document.getElementById('registerName').value.trim();
    const years = parseInt(document.getElementById('registerYears').value);
    if (!name) return;
    const res = await fetch('/api/points/names/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, name, years })
    });
    const data = await res.json();
    if (res.ok) alert(`Registered ${name} until ${new Date(data.expires_at).toLocaleDateString()}`);
    else alert(data.error);
    listMyNames();
}

async function listMyNames() {
    const userId = getUserId();
    const res = await fetch(`/api/points/names/owned/${userId}`);
    const names = await res.json();
    const pre = document.getElementById('myNamesList');
    pre.innerHTML = names.map(n => `${n.name} (expires ${new Date(n.expires_at).toLocaleDateString()})`).join('\n');
}
Cron Job – Expiry Handler
Create scripts/name_expiry.py:

python
#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from points_service.points_api import get_db_session
from core.models.community import NameRegistry
from datetime import datetime

def expire_names():
    session = get_db_session()
    now = datetime.utcnow()
    expired = session.query(NameRegistry).filter(NameRegistry.expires_at < now, NameRegistry.active == True).all()
    for name in expired:
        name.active = False
        print(f"Expired name: {name.name} (owner {name.owner_id})")
    session.commit()
    session.close()

if __name__ == "__main__":
    expire_names()
Add to crontab (runs daily at 2 AM):

cron
# Name expiry – daily at 2 AM
0 2 * * * cd /Users/dixiejones/ToonGen/ToonedOutFrames && python3 scripts/name_expiry.py >> logs/name_expiry.log 2>&1
Admin Verification
To mark a name as verified (e.g., after trademark claim), use:

bash
curl -X POST http://127.0.0.1:5000/api/points/names/verify/alice \
  -H "X-Admin-Key: your-secret-admin-key"
Set your-secret-admin-key in the code (points_service/points_api.py).

Custom Domain Extension
The system uses a global domain extension (e.g., .dstreet). Change DOMAIN_EXTENSION in points_service/points_api.py to your preferred TLD.

python
DOMAIN_EXTENSION = ".dst" 
Testing
Run the test script:

bash
python3 tests/test_name_registry.py
Expected output (if name already registered, it skips gracefully):

text
✅ Check availability works
⚠️ Name already registered (skip test)
✅ Resolve works
✅ List owned works
🎉 Name registry tests completed
Checklist
A Python script check_name_registry.py is provided to verify completeness. Run it to see a percentage breakdown.

Future Enhancements
Add a dispute resolution UI.

Allow users to choose their own extension (multi‑TLD).

Integrate with a blockchain for permanent ownership.

Support wildcard DNS and HTTP gateways.

Your name registry is now production‑ready.
For any issues, check the logs (logs/name_expiry.log, logs/mining.log, etc.) or review the API documentation. 
