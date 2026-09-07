from app.db import SessionLocal, WebhookEvent

db = SessionLocal()

events = db.query(WebhookEvent).all()

for e in events:
    print(
        e.id,
        e.delivery_id,
        e.event_type,
        e.action,
        e.issue_number,
        e.timestamp
    )

db.close()