from bot import pick_winner, CFG

def _cfg(tmp):
    CFG["games"] = {"A":2,"B":3,"C":1}

def test_threshold_met(tmp_path):
    _cfg(CFG)
    t,g = pick_winner({"Mon 1":2},{"A":2,"B":0,"C":0})
    assert g == "A"

def test_fallback(tmp_path):
    _cfg(CFG)
    t,g = pick_winner({"Mon 1":2},{"A":1,"B":1,"C":0})
    assert g == "A"          # top votes even if threshold fails

def test_tiebreak(tmp_path):
    _cfg(CFG)
    t,g = pick_winner({"Mon 1":2},
                      {"A":3,"B":3,"C":0})
    assert g == "A"          # alphabetical tiebreak
