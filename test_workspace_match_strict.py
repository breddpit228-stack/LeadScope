from src.workspace_match_strict import apply_strict_match


def base(score=83, kind='primary', industry_points=36):
    return {
        'score': score,
        'label': 'Strong profile match',
        'matched': ['Primary industry · Fintech', 'Location · Poland', 'B2B'],
        'gaps': [],
        'components': [],
        'tier': 'best',
        'industry_points': industry_points,
        'industry_relation': {
            'kind': kind,
            'label': 'Primary industry · Fintech' if kind == 'primary' else 'Serves Fintech clients',
            'points': industry_points,
            'evidence': ['fintech'],
        },
    }


WORKSPACE = {
    'industry': 'Fintech',
    'region': 'Poland',
    'audience': 'B2B',
    'company_size': '201–500',
    'keywords': '',
}


def main():
    unknown_size_profile = {
        'description': 'Payments software for businesses and finance teams.',
        'company_type': 'Fintech', 'category': 'Fintech', 'audience': 'B2B',
        'country': 'Poland', 'city': 'Warsaw', 'team_size_public': '',
    }
    r = apply_strict_match(base(score=90, industry_points=40), unknown_size_profile, WORKSPACE, {})
    assert r['tier'] == 'broader', r
    assert r['score'] <= 69, r
    assert r['label'] == 'Promising but incomplete', r
    assert any(x['key'] == 'size' and x['status'] == 'unknown' for x in r['requirements']), r
    assert 'Company size ?' in r['matched'], r

    retail_bank = {
        'description': 'A modern retail bank providing personal banking, loans and financial products for individual clients.',
        'company_type': 'Fintech', 'category': 'Fintech', 'audience': 'Unknown',
        'country': 'Poland', 'city': 'Warsaw', 'team_size_public': '300',
    }
    r = apply_strict_match(base(score=90, industry_points=40), retail_bank, WORKSPACE, {'team_size_public': '300'})
    assert r['tier'] == 'broader', r
    assert r['score'] <= 49, r
    assert any(x['key'] == 'audience' and x['status'] == 'mismatch' and x['value'] == 'B2C' for x in r['requirements']), r
    assert 'Business model ×' in r['matched'], r

    strong = {
        'description': 'B2B payments and accounting software for companies and finance teams.',
        'company_type': 'Fintech', 'category': 'Fintech', 'audience': 'B2B',
        'country': 'Poland', 'city': 'Warsaw', 'team_size_public': '350',
    }
    r = apply_strict_match(base(score=90, kind='primary', industry_points=40), strong, WORKSPACE, {'team_size_public': '350'})
    assert r['tier'] == 'best', r
    assert r['score'] == 90, r
    assert r['required_complete'] is True, r
    assert all(x['status'] == 'match' for x in r['requirements']), r

    service = {
        'description': 'Custom software development partner for fintech clients and retail companies.',
        'company_type': 'Professional services', 'category': 'Professional services', 'audience': 'B2B',
        'country': 'Poland', 'city': 'Warsaw', 'team_size_public': '300',
    }
    r = apply_strict_match(base(score=70, kind='serves', industry_points=8), service, WORKSPACE, {'team_size_public': '300'})
    assert r['tier'] == 'broader', r
    assert r['score'] <= 59, r
    assert any(x['key'] == 'industry' and x['status'] == 'partial' for x in r['requirements']), r

    # A stale/seed taxonomy label alone must not make an unrelated company a strong
    # Fintech match. 36/40 is the base matcher's taxonomy-only primary score.
    stale_taxonomy = {
        'description': 'Satellite radar intelligence for infrastructure monitoring and decision makers.',
        'company_type': 'Technology / company', 'category': 'Fintech', 'audience': 'B2B',
        'country': 'Poland', 'city': 'Warsaw', 'team_size_public': '300',
    }
    r = apply_strict_match(base(score=93, kind='primary', industry_points=36), stale_taxonomy, WORKSPACE, {'team_size_public': '300'})
    assert r['tier'] == 'broader', r
    assert r['score'] <= 59, r
    assert any(x['key'] == 'industry' and x['status'] == 'partial' for x in r['requirements']), r
    assert 'Taxonomy suggests Fintech' in next(x['reason'] for x in r['requirements'] if x['key'] == 'industry'), r

    print('Strict workspace match tests OK')


if __name__ == '__main__':
    main()
