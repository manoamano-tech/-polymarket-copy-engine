from src.watcher import fingerprint

def test_fingerprint_is_stable():
    row={"transactionHash":"0x1","asset":"123","side":"BUY","price":0.5,"size":10,"timestamp":1}
    assert fingerprint(row)==fingerprint(dict(row))

def test_different_fill_has_different_fingerprint():
    a={"transactionHash":"0x1","asset":"123","side":"BUY","price":0.5,"size":10,"timestamp":1}
    b=dict(a); b["size"]=11
    assert fingerprint(a)!=fingerprint(b)
