def reciprocal_rank_fusion(vector_results, keyword_results, k=60):
    scores = {}
    for rank, r in enumerate(vector_results):  # already sorted best-first
        scores[r.product_id] = scores.get(r.product_id, 0) + 1 / (k + rank)
    for rank, r in enumerate(keyword_results):
        scores[r.product_id] = scores.get(r.product_id, 0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)