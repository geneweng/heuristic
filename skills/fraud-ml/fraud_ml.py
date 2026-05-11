from schemas import EntityContext, Transaction


def score(txn: Transaction, ctx: EntityContext) -> dict:
    return {"prob": 0.0, "top_features": []}
