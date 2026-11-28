from agent_verdict.selection import oracle_value, paired_mean_diff, pick_value, random_value, trust


def test_trust_orders_verdicts():
    sure_yes = trust({"success": True, "confidence": "high"})
    unsure_yes = trust({"success": True, "confidence": "medium"})
    unsure_no = trust({"success": False, "confidence": "low"})
    sure_no = trust({"success": False, "confidence": "high"})
    assert sure_yes > unsure_yes > unsure_no > sure_no


def test_pick_shares_ties_fairly():
    assert pick_value([(3, True), (1, False), (-3, False)]) == 1.0
    assert pick_value([(3, True), (3, False)]) == 0.5        # a tie is worth the average
    assert pick_value([(-3, False), (-1, True)]) == 1.0       # least-bad wins
    assert random_value([(0, True), (0, False), (0, False), (0, False)]) == 0.25
    assert oracle_value([(0, False), (0, True)]) == 1.0 and oracle_value([(0, False)]) == 0.0


def test_paired_mean_diff():
    d = paired_mean_diff([1.0] * 40 + [0.0] * 60, [0.0] * 100, n_boot=300)
    assert abs(d["diff"] - 0.4) < 1e-9 and d["significant"]
    same = paired_mean_diff([1.0, 0.0] * 20, [1.0, 0.0] * 20, n_boot=100)
    assert same["diff"] == 0 and not same["significant"]
