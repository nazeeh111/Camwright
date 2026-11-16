"""Installed data-only design/check/select/export/replay operations."""
import argparse
import base64
from fractions import Fraction
import io
import json
import math
from pathlib import Path
import os
import stat
import tempfile
import sys
import zipfile

from .project import MAX_BODY, parse_json, validate_project, identity
from .runtime import Calculator
from .sizing import request as sizing_request


def read_regular(path, maximum, label):
    """Capture one bounded regular-file descriptor, without blocking on a FIFO."""
    if not hasattr(os, 'O_NONBLOCK'):
        raise ValueError('Nonblocking file admission is unavailable on this platform')
    descriptor=os.open(path,os.O_RDONLY|os.O_NONBLOCK)
    try:
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):raise ValueError(f'{label} must be a regular file')
        if info.st_size>maximum:raise ValueError(f'{label} exceeds byte limit {maximum}')
        chunks=[];size=0
        while size<=maximum:
            chunk=os.read(descriptor,min(65536,maximum+1-size))
            if not chunk:break
            chunks.append(chunk);size+=len(chunk)
        if size>maximum:raise ValueError(f'{label} exceeds byte limit {maximum}')
        return b''.join(chunks)
    finally:os.close(descriptor)


def read_project(path):
    project=parse_json(read_regular(path,MAX_BODY,'Project'));validate_project(project)
    return project


def write_exclusive(path,data):
    path=Path(path);temporary=None;published=False
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.camwright-',delete=False) as stream:
            temporary=Path(stream.name);stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.link(temporary,path);published=True
    finally:
        if temporary is not None:
            try:temporary.unlink(missing_ok=True)
            except OSError as exc:
                if published:
                    print(json.dumps({'warning':'published_with_staging_cleanup_failure',
                        'published':str(path),'staging':str(temporary),'detail':str(exc)}),file=sys.stderr)
                else:
                    # Preserve the original publication failure and identify owned residue.
                    print(json.dumps({'warning':'staging_cleanup_failure',
                        'staging':str(temporary),'detail':str(exc)}),file=sys.stderr)


def report_bytes(value):return (json.dumps(value,indent=2,allow_nan=False)+'\n').encode()


def replay(path,calculator):
    raw=read_regular(path,8*1024*1024,'Archive')
    expected={'cam.csv','pitch.csv','cam.svg','pitch.svg','cam.dxf','pitch.dxf','camwright-project.json','checks.json','export.json'}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos=archive.infolist()
        if {i.filename for i in infos} not in (expected, expected-{'cam.dxf','pitch.dxf'}) or len(infos)!=len({i.filename for i in infos}) or any(i.flag_bits&1 or i.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED) for i in infos) or sum(i.file_size for i in infos)>16*1024*1024:
            raise ValueError('Unsupported or oversized geometry archive')
        saved={i.filename:archive.read(i) for i in infos}
    project=parse_json(saved['camwright-project.json']);validate_project(project)
    current=calculator.run('export',project,identity(project))
    if 'error' in current:raise ValueError(current['error']['message'])
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(current['zip_base64']))) as fresh:
        actual={i.filename:fresh.read(i) for i in fresh.infolist()}
    if actual!=saved:raise ValueError('Archive differs from fresh checks or certified geometry')
    return {'status':'verified-replay','project_id':identity(project),'files':sorted(saved),
            'scope':'Current implementation and supported geometric model only; not fabrication approval.'}


def main(argv):
    parser=argparse.ArgumentParser(prog='camwright')
    sub=parser.add_subparsers(dest='command',required=True)
    sample=sub.add_parser('example',help='create the bundled editable exact project');sample.add_argument('--out',type=Path)
    check=sub.add_parser('check');check.add_argument('project',type=Path)
    export=sub.add_parser('export');export.add_argument('project',type=Path);export.add_argument('--out',type=Path,required=True)
    explore=sub.add_parser('explore');explore.add_argument('project',type=Path)
    explore.add_argument('--base-radii',required=True,help='comma-separated exact mm radii')
    explore.add_argument('--roller-radii',required=True,help='comma-separated exact mm radii')
    explore.add_argument('--max-candidates',type=int,default=64);explore.add_argument('--out',type=Path)
    select=sub.add_parser('select');select.add_argument('report',type=Path);select.add_argument('--project',type=Path)
    select.add_argument('--base-index',type=int);select.add_argument('--roller-index',type=int);select.add_argument('--out',type=Path,required=True)
    verify=sub.add_parser('replay');verify.add_argument('archive',type=Path)
    args=parser.parse_args(argv);calculator=Calculator()
    try:
        if args.command=='example':
            result=read_project(Path(__file__).with_name('examples')/'accepted.json')
            if args.out:write_exclusive(args.out,report_bytes(result))
        elif args.command=='replay':result=replay(args.archive,calculator)
        elif args.command=='select':
            raw=read_regular(args.report,2*1024*1024,'Sizing report')
            # Unlike project numbers, result metadata contains finite JSON floats.
            def unique(pairs):
                out={}
                for k,v in pairs:
                    if k in out:raise ValueError('Duplicate report key')
                    out[k]=v
                return out
            def finite(text):
                value=float(text)
                if not math.isfinite(value):raise ValueError('Nonfinite report')
                return value
            report=json.loads(raw,object_pairs_hook=unique,parse_float=finite,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite report')))
            if type(report) is not dict or report.get('schema')!='camwright.sizing-result' or type(report.get('version')) is not int or report['version']!=1:raise ValueError('Unsupported sizing report')
            req=report['request'];source=read_project(args.project) if args.project else req['project']
            options={k:req[k] for k in ('base_radii','roller_radii','request_id')}
            if args.base_index is None and args.roller_index is None:
                choice=report.get('selection')
                if type(choice) is not dict:raise ValueError('No passing candidate was recorded; choose valid indices after a new exploration')
                i,j=choice['base_index'],choice['roller_index']
            elif args.base_index is None or args.roller_index is None:
                raise ValueError('Supply both candidate indices or neither')
            else:i,j=args.base_index,args.roller_index
            options.update(base_index=i,roller_index=j)
            result=calculator.run('select',source,identity(source),options)
            if 'error' not in result:write_exclusive(args.out,report_bytes(result['project']))
        else:
            source=read_project(args.project)
            if args.command=='explore':
                options={'base_radii':args.base_radii.split(','),'roller_radii':args.roller_radii.split(','),'max_candidates':args.max_candidates}
                sizing_request(source,options)
                result=calculator.run('explore',source,options=options)
                if 'error' not in result and args.out:write_exclusive(args.out,report_bytes(result))
            else:
                result=calculator.run(args.command,source,identity(source) if args.command=='export' else None)
                if args.command=='export' and 'error' not in result:write_exclusive(args.out,base64.b64decode(result.pop('zip_base64')))
        print(json.dumps(result,allow_nan=False))
        return 3 if 'error' in result or result.get('status')=='unfinished' or (args.command=='export' and result.get('summary',{}).get('cad_status')!='pass') else 0
    except (ValueError,KeyError,TypeError,OSError,RecursionError,OverflowError,zipfile.BadZipFile) as exc:
        parser.exit(2,f'camwright: {exc}\n')
    except KeyboardInterrupt:
        print("camwright: interrupted; check the destination because complete publication may already have finished",file=sys.stderr)
        return 130
    finally:calculator.close()
