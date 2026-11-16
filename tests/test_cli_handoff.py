import base64,copy,io,json,os,subprocess,sys,tempfile,threading,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from camwright.cli import write_exclusive
from camwright.engine import calculate
from camwright.project import identity
from camwright.runtime import Calculator
from .test_sizing import example


def command(*args):return subprocess.run([sys.executable,'-m','camwright',*map(str,args)],capture_output=True,text=True,timeout=40)


class CLIHandoffTests(unittest.TestCase):
    def test_real_cli_explore_select_export_replay_and_stale_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.json';source.write_text(json.dumps(example()));report=root/'grid.json';chosen=root/'chosen.json';output=root/'profile.zip'
            r=command('explore',source,'--base-radii','20,25,30','--roller-radii','4,5,6','--out',report)
            self.assertEqual(r.returncode,0,r.stderr)
            data=json.loads(report.read_text());self.assertTrue(data['minimum_within_grid']);self.assertEqual(data['evaluated'],9)
            r=command('select',report,'--base-index','1','--roller-index','0','--out',chosen);self.assertEqual(r.returncode,0,r.stderr)
            p=json.loads(chosen.read_text());self.assertEqual((p['base_radius'],p['roller_radius']),('25','4'))
            r=command('select',report,'--out',root/'recommended.json');self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads((root/'recommended.json').read_text()),p)
            r=command('export',chosen,'--out',output);self.assertEqual(r.returncode,0,r.stderr)
            r=command('replay',output);self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout)['status'],'verified-replay')
            saved=output.read_bytes();r=command('export',chosen,'--out',output);self.assertEqual(r.returncode,2);self.assertEqual(output.read_bytes(),saved)
            changed=example();changed['maximum_pressure_slope']='0.49';source.write_text(json.dumps(changed))
            r=command('select',report,'--project',source,'--base-index','1','--roller-index','0','--out',root/'stale.json')
            self.assertEqual(r.returncode,3);self.assertEqual(json.loads(r.stdout)['error']['code'],'stale_sizing');self.assertFalse((root/'stale.json').exists())
            # Recomputed archives cannot trust forged geometry or model claims.
            corrupt=root/'corrupt.zip'
            with zipfile.ZipFile(io.BytesIO(saved)) as archive,zipfile.ZipFile(corrupt,'w') as altered:
                for item in archive.infolist():altered.writestr(item,archive.read(item)+(b'corrupt' if item.filename=='cam.dxf' else b''))
            self.assertEqual(command('replay',corrupt).returncode,2)
            for raw in ('[]','{"schema":1,"schema":2}','NaN','['*1100+']'*1100):
                bad=root/'bad.json';bad.write_text(raw)
                r=command('select',bad,'--base-index','0','--roller-index','0','--out',root/'bad-project.json')
                self.assertEqual(r.returncode,2,r.stderr);self.assertNotIn('Traceback',r.stderr)

    def test_detached_identity_and_failure_atomic_publication(self):
        p=example();expected=identity(p)
        from camwright import evaluation
        original=evaluation.geometry.check_design
        def mutate(private,**kwargs):
            p['base_radius']='20'
            return original(private,**kwargs)
        with patch('camwright.evaluation.geometry.check_design',mutate):result=calculate('export',p,expected)
        self.assertEqual(result['project_id'],expected)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(result['zip_base64']))) as archive:
            self.assertEqual(json.loads(archive.read('camwright-project.json'))['base_radius'],'25')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'out'
            with patch('camwright.cli.os.fsync',side_effect=OSError('late sync failure')):
                with self.assertRaises(OSError):write_exclusive(target,b'complete')
            self.assertEqual(list(root.iterdir()),[])
            write_exclusive(target,b'complete')
            with self.assertRaises(FileExistsError):write_exclusive(target,b'other')
            self.assertEqual(target.read_bytes(),b'complete')

    def test_publication_cleanup_and_descriptor_admission(self):
        from camwright.cli import read_regular,main
        import contextlib
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'published';err=io.StringIO()
            with patch('pathlib.Path.unlink',side_effect=PermissionError('cleanup denied')) as unlink,contextlib.redirect_stderr(err),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['example','--out',str(target)]),0)
            self.assertEqual(unlink.call_count,1)
            self.assertEqual(json.loads(target.read_bytes())['base_radius'],'25')
            self.assertIn('published_with_staging_cleanup_failure',err.getvalue())
            stages=list(root.glob('.camwright-*'));self.assertEqual(len(stages),1)
            before=target.read_bytes()
            with self.assertRaises(FileExistsError):write_exclusive(target,b'other')
            self.assertEqual(target.read_bytes(),before);self.assertTrue(stages[0].exists())
            fifo=root/'fifo';os.mkfifo(fifo)
            for args in [('check',fifo),('replay',fifo),('select',fifo,'--out',root/'out')]:
                started=time.monotonic();r=command(*args)
                self.assertEqual(r.returncode,2,r.stderr);self.assertLess(time.monotonic()-started,3)
                self.assertIn('regular file',r.stderr)
            source=root/'source';source.write_bytes(b'original');original=os.fstat
            def swap(fd):
                info=original(fd);source.rename(root/'old');source.write_bytes(b'replacement');return info
            with patch('camwright.cli.os.fstat',swap):self.assertEqual(read_regular(source,100,'Test'),b'original')
            with self.assertRaises(ValueError):read_regular(source,2,'Test')
            with patch('camwright.cli.os.link',side_effect=PermissionError('publication denied')) as link:
                with self.assertRaisesRegex(PermissionError,'publication denied'):write_exclusive(root/'denied',b'x')
            self.assertEqual(link.call_count,1);self.assertFalse((root/'denied').exists())

    def test_real_explorer_worker_ownership_cancel_and_retry(self):
        calculator=Calculator();p=example();answer=[]
        options={'base_radii':[str(x) for x in range(20,28)],'roller_radii':[str(x) for x in range(2,10)],'max_candidates':64}
        thread=threading.Thread(target=lambda:answer.append(calculator.run('explore',p,options=options)));thread.start()
        try:
            until=time.time()+3
            while calculator.active is None and time.time()<until:time.sleep(.001)
            self.assertIsNotNone(calculator.active)
            self.assertEqual(calculator.run('check',p)['error']['code'],'busy')
            self.assertTrue(calculator.cancel(identity(p)));thread.join(5)
            self.assertFalse(thread.is_alive());self.assertEqual(answer[0]['error']['code'],'cancelled')
            self.assertEqual(calculator.run('check',p)['result']['status'],'pass')
        finally:calculator.close();thread.join(5)
