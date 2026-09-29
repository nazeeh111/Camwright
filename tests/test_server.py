import http.client
import io
import json
import threading
import unittest
import zipfile

from camwright.project import identity
from camwright.server import make_server
from .test_project import example


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.calculator.close()
        cls.server.server_close()
        cls.thread.join(2)

    def request(self, method, path, payload=None, headers=None, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
        values = {"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}",
                  "Content-Type": "application/json"}
        values.update(headers or {})
        connection.request(method, path, body=body, headers=values)
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_host_origin_content_type_path_and_size_guards(self):
        for method,path,payload,headers,expected in [
            ("GET","/",None,{"Host":"attacker.test"},403),
            ("POST","/api/check",{"project":example()},{"Origin":"http://attacker.test"},403),
            ("POST","/api/check",{"project":example()},{"Origin":""},403),
            ("POST","/api/check",{"project":example()},{"Content-Type":"text/plain"},415),
            ("GET","/../../README.md",None,{},404),
            ("GET","/geometry.py",None,{},404),
            ("POST","/api/check",{"project":example(),"path":"/tmp/x"},{},400)]:
            self.assertEqual(expected,self.request(method,path,payload,headers)[0])
        self.assertEqual(413,self.request("POST","/api/check",raw=b" "*32769)[0])
        self.assertEqual(400,self.request("POST","/api/validate",raw=b'{"project":{},"project":{}}')[0])

    def test_real_http_check_and_zip_only_for_current_project(self):
        project=example()
        status,_,raw=self.request("POST","/api/check",{"project":project})
        result=json.loads(raw)
        self.assertEqual(200,status)
        self.assertEqual("pass",result["result"]["status"])
        self.assertEqual(identity(project),result["project_id"])
        status,headers,raw=self.request("POST","/api/export",{"project":project,"project_id":identity(project)})
        self.assertEqual(200,status)
        self.assertEqual("application/zip",headers["Content-Type"])
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            self.assertEqual(project,json.loads(bundle.read("camwright-project.json")))
        project["base_radius"]="20"
        self.assertEqual(409,self.request("POST","/api/export",{"project":project,"project_id":identity(example())})[0])
        status,_,raw=self.request("POST","/api/export",{"project":project,"project_id":identity(project)})
        self.assertEqual(409,status)
        self.assertEqual("fail",json.loads(raw)["status"])
