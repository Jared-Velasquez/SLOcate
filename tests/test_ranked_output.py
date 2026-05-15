import pickle

from tracerca.ranked_output import parse_ranked_output


def test_reads_from_pkl(tmp_path):
    p = tmp_path / "ranked.pkl"
    with p.open("wb") as f:
        pickle.dump({"Ours-noise=0": ["ts-order-service", "ts-station-service"]}, f)
    assert parse_ranked_output("", p) == ["ts-order-service", "ts-station-service"]
