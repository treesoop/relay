from central_api.ranking import context_match_score, combine_score


def test_context_match_full_overlap():
    score = context_match_score(
        skill_context={"languages": ["python"], "libraries": ["stripe-python>=8.0"]},
        query_languages=["python"],
        query_libraries=["stripe-python>=8.0"],
    )
    assert score == 1.0


def test_context_match_partial_overlap():
    score = context_match_score(
        skill_context={"languages": ["python"], "libraries": ["a", "b"]},
        query_languages=["python"],
        query_libraries=["a", "c"],
    )
    # languages 1/1 = 1.0; libraries 1/3 intersect-over-union; average
    assert 0 < score < 1


def test_context_match_empty_query_is_neutral():
    # With no query context, we don't penalize — every skill scores 1.0 on context.
    score = context_match_score(
        skill_context={"languages": ["python"], "libraries": ["x"]},
        query_languages=[],
        query_libraries=[],
    )
    assert score == 1.0


def test_combine_score_formula():
    score = combine_score(similarity=0.9, confidence=0.8, context_match=0.5)
    # 0.9*0.5 + 0.8*0.3 + 0.5*0.2 = 0.45 + 0.24 + 0.10 = 0.79
    assert abs(score - 0.79) < 1e-6


def test_combine_score_monotone_in_similarity():
    a = combine_score(similarity=0.5, confidence=0.5, context_match=0.5)
    b = combine_score(similarity=0.8, confidence=0.5, context_match=0.5)
    assert b > a
