"""Exercise local opener callbacks, redirects, and ownership without networking."""
import _urllib_request_rs as native
import gc
from email.message import Message
import unittest
from urllib import error, request
import weakref


class Response:
    def __init__(self, code=200, location=None):
        self.code = code
        self.msg = "Found" if code == 302 else "OK"
        self.headers = Message()
        if location is not None:
            self.headers["Location"] = location
        self.closed = False

    def info(self):
        return self.headers

    def read(self):
        return b"local response"

    def close(self):
        self.closed = True


class LocalDirector(request.OpenerDirector):
    def __init__(self, transport):
        super().__init__()
        self.transport = transport

    def _open(self, req, data=None):
        return self.transport(req, data)


class CoreRequestCallbackTests(unittest.TestCase):
    def setUp(self):
        self.assertIs(request._rust_request, native)

    def test_request_replacement_proxy_auth_and_response_ownership(self):
        old_requests, old_responses, opened = [], [], []

        class ProxyProcessor(request.BaseHandler):
            handler_order = 400

            def http_request(self, req):
                old_requests.append(weakref.ref(req))
                replacement = request.Request(req.full_url, req.data)
                replacement.timeout = req.timeout
                replacement.set_proxy("proxy.invalid:8080", "http")
                return replacement

        class ResponseProcessor(request.BaseHandler):
            handler_order = 600

            def http_response(self, req, response):
                old_responses.append(weakref.ref(response))
                return Response()

        def transport(req, data):
            opened.append((req.host, req.selector, req.timeout,
                           req.get_header("Authorization"), req.data, data))
            return Response()

        passwords = request.HTTPPasswordMgrWithPriorAuth()
        passwords.add_password(None, "http://origin.invalid/", "alice", "secret",
                               is_authenticated=True)
        director = LocalDirector(transport)
        director.add_handler(ProxyProcessor())
        director.add_handler(request.HTTPBasicAuthHandler(passwords))
        director.add_handler(ResponseProcessor())
        result = director.open("http://origin.invalid/path", b"payload", timeout=7)
        self.assertIsInstance(result, Response)
        self.assertEqual(opened, [("proxy.invalid:8080", "http://origin.invalid/path",
                                  7, "Basic YWxpY2U6c2VjcmV0", b"payload", b"payload")])
        self.assertEqual(len(old_requests), 1)
        self.assertEqual(len(old_responses), 1)
        self.assertIsNone(old_requests[0]())
        self.assertIsNone(old_responses[0]())

    def redirect_director(self, target):
        urls, responses = [], []

        def transport(req, data):
            urls.append(req.full_url)
            response = Response(302, target) if len(urls) == 1 else Response()
            responses.append(weakref.ref(response))
            return response

        director = LocalDirector(transport)
        director.add_handler(request.HTTPRedirectHandler())
        director.add_handler(request.HTTPErrorProcessor())
        return director, urls, responses

    def test_redirect_reenters_local_rust_dispatch(self):
        director, urls, responses = self.redirect_director("/finish")
        result = director.open("http://origin.invalid/start", timeout=3)
        self.assertEqual(result.code, 200)
        self.assertEqual(urls, ["http://origin.invalid/start",
                                "http://origin.invalid/finish"])
        self.assertIsNone(responses[0]())
        self.assertIs(responses[1](), result)

    def test_disallowed_redirect_never_reaches_transport(self):
        director, urls, _ = self.redirect_director("file:///forbidden-target")
        with self.assertRaises(error.HTTPError) as caught:
            director.open("http://origin.invalid/start")
        self.assertEqual(caught.exception.code, 302)
        self.assertIn("not allowed", str(caught.exception))
        self.assertEqual(urls, ["http://origin.invalid/start"])

    def test_iteration_failure_preserves_exception_and_releases_request(self):
        failure = RuntimeError("processor iteration failed")
        borrowed = []

        class Processor:
            def http_request(self, req):
                borrowed.append(weakref.ref(req))
                return req

        class Processors:
            def __iter__(self):
                yield Processor()
                raise failure

        def transport(req, data):
            raise AssertionError("failed processors reached transport")

        director = LocalDirector(transport)
        director.process_request["http"] = Processors()
        try:
            director.open("http://origin.invalid/path")
        except RuntimeError as caught:
            self.assertIs(caught, failure)
        else:
            self.fail("processor iteration failure was swallowed")
        failure.__traceback__ = None
        gc.collect()
        self.assertEqual(len(borrowed), 1)
        self.assertIsNone(borrowed[0]())

    def test_truth_failure_precedes_request_construction(self):
        failure = RuntimeError("string classification failed")
        constructed = []

        class Classification:
            def __bool__(self):
                raise failure

        def constructor(*args):
            constructed.append(args)
            raise AssertionError("failed classification constructed a request")

        with self.assertRaises(RuntimeError) as caught:
            native.open(None, "http://origin.invalid/path", None, 3,
                        constructor, Classification())
        self.assertIs(caught.exception, failure)
        self.assertEqual(constructed, [])


if __name__ == "__main__":
    unittest.main()
