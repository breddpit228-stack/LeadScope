from tests.test_core import (
    test_evidence_validation_rejects_untraceable_signal,
    test_scoring_is_offer_relative_and_explainable,
    test_quality_gate_requires_evidence,
    test_signal_ranking_penalizes_old_irrelevant_partnership,
)

if __name__ == '__main__':
    test_evidence_validation_rejects_untraceable_signal()
    test_scoring_is_offer_relative_and_explainable()
    test_quality_gate_requires_evidence()
    test_signal_ranking_penalizes_old_irrelevant_partnership()
    print('4/4 core tests passed')
