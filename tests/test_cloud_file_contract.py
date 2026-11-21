import base64
import hashlib
import json
import threading
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from core.web.storage import RescsStorage
from tests.test_linux_desktop_contract import Remote, RemoteError, owner
from tests.test_linux_desktop_contract import server as server


@pytest.fixture
def rescs_backend():
    files={};content_reads=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,data,status=200):
            raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            assert self.headers['X-API-Key']=='backend-test-key'
            raw=self.rfile.read(int(self.headers['Content-Length']))
            parts=BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\n\r\n').encode()+raw)
            values={p.get_param('name',header='content-disposition'):p for p in parts.iter_parts()}
            data=values['upload'].get_payload(decode=True);identity=str(len(files)+1)
            meta={'id':identity,'owner':values['owner'].get_content().strip(),'filename':values['upload'].get_filename(),
                  'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'tags':[values['tags'].get_content().strip()]}
            files[identity]=(meta,data);self.reply(meta,201)
        def do_GET(self):
            parsed=urlparse(self.path);query=parse_qs(parsed.query)
            if parsed.path=='/api/v1/files':
                rows=[m for m,d in files.values() if m['owner']==query['owner'][0] and (not query.get('tags') or query['tags'][0] in m['tags'])]
                offset=int(query.get('offset',['0'])[0]);limit=int(query.get('limit',['100'])[0])
                self.reply({'items':rows[offset:offset+limit],'total':len(rows),'limit':limit,'offset':offset});return
            identity=parsed.path.split('/')[4]
            meta,data=files[identity]
            if parsed.path.endswith('/content'):
                content_reads.append(identity);self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            else:self.reply(meta)
        def do_DELETE(self):
            files.pop(self.path.split('/')[4]);self.reply({})
    backend=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=backend.serve_forever,daemon=True);thread.start()
    yield 'http://127.0.0.1:'+str(backend.server_address[1]),files,content_reads
    backend.shutdown();backend.server_close();thread.join(3)


def test_real_file_transfer_contract_account_scope_and_retry_idempotence(server,rescs_backend):
    gateway,admin=server;profile=owner(gateway,admin)
    url,files,reads=rescs_backend;gateway.storage=RescsStorage(url,'backend-test-key')
    body={'name':'notes.txt','upload_id':'1'*32,'base64':base64.b64encode(b'private cloud bytes').decode()}
    meta=admin.request('POST','/api/files',body)
    assert admin.request('POST','/api/files',body)['id']==meta['id'] and len(files)==1
    result=admin.request('GET','/api/files/'+meta['id'])
    assert base64.b64decode(result['base64'])==b'private cloud bytes'
    admin.request('POST','/api/profiles',{'username':'other','password':'other-password-123','name':'Other'})
    other=Remote(admin.url);other.login('other','other-password-123')
    assert other.request('GET','/api/files')['items']==[]
    before=len(reads)
    with pytest.raises(RemoteError) as error:other.request('GET','/api/files/'+meta['id'])
    assert error.value.status==403 and len(reads)==before
    admin.request('POST','/api/files/'+meta['id']+'/delete')
    assert admin.request('GET','/api/files')['items']==[]
    assert profile['id'] in meta['owner'];other.close()
