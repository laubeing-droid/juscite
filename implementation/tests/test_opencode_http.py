import sys
import unittest
from pathlib import Path
from urllib.error import URLError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"python"))
from opencode_http import Client, TransportError
from legal_entry import call, NotConnected

class Response:
    def __init__(self,raw):self.raw=raw
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self):return self.raw

class Fake:
    def __init__(self,raw=b'{"version":"2.0.28"}',error=None):self.raw=raw;self.error=error;self.requests=[]
    def open(self,req,timeout):
        self.requests.append(req)
        if self.error:raise self.error
        return Response(self.raw)

class WiringTests(unittest.TestCase):
    def test_exact_version_rejects_v1(self):
        with self.assertRaises(TransportError):Client("http://127.0.0.1:43127",opener=Fake(b'{"version":"1.19.0"}')).verify_version()
    def test_mutation_failure_unknown_not_retried(self):
        f=Fake(error=URLError("offline"));c=Client("http://127.0.0.1:43127",opener=f)
        with self.assertRaises(TransportError) as e:c.prompt("ses/1",{"id":"msg-1","text":"测试"})
        self.assertTrue(e.exception.uncertain);self.assertEqual(len(f.requests),1)
    def test_get_failure_not_mutation_unknown(self):
        with self.assertRaises(TransportError) as e:Client("http://localhost:43127",opener=Fake(error=URLError("offline"))).session("a")
        self.assertFalse(e.exception.uncertain)
    def test_interrupt_never_resumes(self):
        f=Fake();Client("http://localhost:43127",opener=f).interrupt("ses/1")
        self.assertTrue(f.requests[0].full_url.endswith("/ses%2F1/interrupt?resume=false"))
    def test_prompt_id_required_for_reconciliation(self):
        f=Fake()
        with self.assertRaises(ValueError):Client("http://localhost:43127",opener=f).prompt("s",{"text":"x"})
        self.assertEqual(f.requests,[])
    def test_remote_plaintext_and_url_secrets_rejected(self):
        for url in ["http://example.com", "https://user:pass@example.com", "https://example.com/?key=a"]:
            with self.assertRaises(ValueError):Client(url)
    def test_missing_assets_do_not_success_stub(self):
        for method in ["harness.execute","anonymizer.scrub","case.search","jc.read_run"]:
            with self.assertRaises(NotConnected):call(method,{}, {})
    def test_post_invalid_json_preserves_unknown(self):
        with self.assertRaises(TransportError) as e:Client("http://localhost:43127",opener=Fake(b'not json')).prompt("s",{"id":"msg-2","text":"x"})
        self.assertTrue(e.exception.uncertain)
    def test_server_info_bad_shape_is_protocol_error(self):
        with self.assertRaises(TransportError) as e:Client("http://localhost:43127",opener=Fake(b'{"data":[]}')).verify_version()
        self.assertEqual(e.exception.code,"protocol_response_invalid")

if __name__=="__main__":unittest.main()
