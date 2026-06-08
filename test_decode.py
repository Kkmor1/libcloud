import json

def test_raw_decode():
    s = """
    {
        "a": {"key": "value"},
        "b": {"key2": "value2"}
    }
    """
    idx = s.find('"b"')
    idx = s.find('{', idx)
    decoder = json.JSONDecoder()
    obj, end_idx = decoder.raw_decode(s, idx)
    print("Decoded:", obj)

test_raw_decode()
