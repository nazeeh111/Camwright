import base64,copy,http.client,io,json,threading,unittest,zipfile
from camwright.server import make_server
from camwright.project import identity
from .test_sizing import example,selected_options


class SizingHTTPTests(unittest.TestCase):
    def test_actual_source_bound_explore_select_and_cad_handoff(self):
        server=make_server(0);thread=threading.Thread(target=server.serve_forever);thread.start()
        def post(path,payload):
            c=http.client.HTTPConnection('127.0.0.1',server.server_address[1],timeout=35)
            c.request('POST',path,json.dumps(payload),{'Host':server.expected_host,'Origin':server.expected_origin,'Content-Type':'application/json'})
            r=c.getresponse();status=r.status;headers=dict(r.getheaders());data=r.read();c.close();return status,headers,data
        try:
            source=example();options={'base_radii':['20','25','30'],'roller_radii':['4','5','6'],'max_candidates':1}
            status,_,data=post('/api/explore',{'project':source,'options':options});self.assertEqual(status,200)
            first=json.loads(data);self.assertEqual(first['status'],'unfinished');self.assertFalse(first['minimum_within_grid'])
            status,_,data=post('/api/explore',{'project':source,'options':{**options,'max_candidates':64}});self.assertEqual(status,200)
            report=json.loads(data);self.assertTrue(report['complete']);self.assertTrue(report['minimum_within_grid']);self.assertEqual(report['evaluated'],9)
            status,_,data=post('/api/select',{'project':source,'project_id':identity(source),'options':selected_options(report,1,0)})
            self.assertEqual(status,200);selected=json.loads(data);self.assertEqual(selected['project']['roller_radius'],'4')
            status,headers,data=post('/api/export',{'project':selected['project'],'project_id':selected['project_id']});self.assertEqual(status,200)
            self.assertEqual(headers['X-Camwright-CAD-Status'],'pass')
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                self.assertIn('cam.dxf',archive.namelist());self.assertEqual(json.loads(archive.read('camwright-project.json')),selected['project'])
            changed=copy.deepcopy(source);changed['maximum_pressure_slope']='0.49'
            status,_,data=post('/api/select',{'project':changed,'project_id':identity(changed),'options':selected_options(report,1,0)})
            self.assertEqual(status,409);self.assertEqual(json.loads(data)['error']['code'],'stale_sizing')
            status,_,data=post('/api/select',{'project':source,'project_id':identity(source),'options':selected_options(report,0,0)})
            self.assertEqual(status,409);self.assertEqual(json.loads(data)['error']['code'],'selection_refused')
            self.assertNotIn('zip_base64',json.loads(data))
        finally:
            server.shutdown();server.calculator.close();server.server_close();thread.join(3)
