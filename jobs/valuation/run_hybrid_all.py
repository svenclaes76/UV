from app.database import db
from app.services.hybrid_valuation_service import run_hybrid_for_company

def get_all_company_ids():
    with db.cursor() as cur:
        cur.execute("SELECT id FROM companies")
        return [row[0] for row in cur.fetchall()]

def run_all():
    ids = get_all_company_ids()
    for cid in ids:
        print(f"Running Hybrid valuation for company {cid}")
        run_hybrid_for_company(cid)

if __name__ == "__main__":
    run_all()
