"""Authenticated C.O.R.E. web workspace; backend agents stay independent."""
from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..version import __version__ as CORE_VERSION
from .accounts import Accounts
from .events import EventBus, TicketStore
from .library import Library
from .services import CATALOG, Services
from .storage import RecordConflict, RescsStorage
from .ws import WebSocketServer, available as ws_available

MAX_BODY = 256 * 1024


class LimitedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self,*args,**kwargs):
        self.slots=threading.BoundedSemaphore(16)
        super().__init__(*args,**kwargs)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            try:request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:pass
            self.shutdown_request(request);return
        try:super().process_request(request,address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()


class Gateway:
    def __init__(self, app=None, *, directory=None, port=8780):
        self.app, self.port = app, int(port)
        self.data = Path(directory or os.environ.get("CORE_WEB_DATA", "var/web")).resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data / "gateway.json"
        self.lock = threading.RLock()
        parent = Path(__file__).resolve().parents[3]
        self.config = {"rescs_url": "http://127.0.0.1:8081", "rescs_key": secrets.token_urlsafe(32),
                       "public_origin": "", "roots": {k: str(parent/v[2]) for k,v in CATALOG.items()}, "links": {},
                       "models": {"asis":"", "ascs":"", "tiviss":""}, "profile_models": {}}
        if self.config_path.exists(): self.config.update(json.loads(self.config_path.read_text()))
        self.config["public_origin"] = os.environ.get("CORE_PUBLIC_ORIGIN", self.config["public_origin"]).rstrip("/")
        self.validate_origin(self.config["public_origin"])
        self.save_config()
        self.accounts = Accounts(self.data)
        self.library = Library(self.data)
        self.admin_attempts = defaultdict(deque)
        self.setup_key = secrets.token_urlsafe(32)
        self.storage = RescsStorage(self.config["rescs_url"], self.config["rescs_key"])
        self.services = Services(self.data, self.config["roots"], self.config["rescs_key"], self.config["models"])
        self.services.profile_models = self.config.get("profile_models", {})
        self.attempts = defaultdict(deque)
        self.device_attempts = defaultdict(deque)
        self.registrations = defaultdict(deque)
        self.events = EventBus()
        self.tickets = TicketStore()
        self.ws_port = int(os.environ.get("CORE_WS_PORT", "8781"))
        self.ws_available = ws_available()
        self.ws_running = False
        self.idempotency = {}

    @staticmethod
    def validate_origin(origin):
        if not origin: return
        p = urlparse(origin)
        if p.scheme != "https" or not p.hostname or p.username or p.password or p.path or p.query or p.fragment:
            raise ValueError("The public origin must be an HTTPS origin without a path.")

    def save_config(self):
        import tempfile
        with self.lock:
            fd, path = tempfile.mkstemp(prefix="gateway-", suffix=".json", dir=self.data)
            with os.fdopen(fd, "w") as file: json.dump(self.config, file, indent=2)
            Path(path).replace(self.config_path)

    @staticmethod
    def token(headers):
        cookie = SimpleCookie()
        try: cookie.load(headers.get("Cookie", ""))
        except Exception: return ""
        return cookie["core_session"].value if "core_session" in cookie else ""

    def cookie(self, token, public=False, expired=False):
        return f"core_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if expired else 43200}" + ("; Secure" if public else "")

    def dispatch(self, method, path, body, headers, remote="127.0.0.1"):
        route = urlparse(path).path
        query = parse_qs(urlparse(path).query)
        token = self.token(headers)
        user = self.accounts.session(token)
        public = headers.get("Host", "") == urlparse(self.config["public_origin"]).netloc
        if method == "GET" and route == "/api/health":
            return 200, {
                "service": "CORE", "api": 1, "version": CORE_VERSION, "status": "ready",
                "ws": bool(self.ws_available),
                "capabilities": [
                    "conditional_records_v1", "folders_sharing_trash_v1", "admin_reauth_v1",
                    "ws_ticket_v1", "session_renewal_v1", "device_credentials_v1",
                    "device_management_v1", "job_idempotency_v1",
                ],
            }, None
        if method == 'GET' and route == '/api/ready':
            try:
                self.storage.request('GET','/health/ready')
                return 200, {'status':'ready','storage':'ready'}, None
            except ConnectionError:
                return 503, {'status':'degraded','storage':'unavailable'}, None
        if method == "GET" and route == "/api/setup": return 200, {"setup_required": self.accounts.empty()}, None
        if method == "POST" and route == "/api/setup":
            if not hmac.compare_digest(str(body.get("setup_key", "")), self.setup_key) or not self.setup_key:
                raise PermissionError("Enter the setup key printed by the host launcher.")
            user = self.accounts.create(body.get("username"), body.get("password"), body.get("name"), first=True)
            self.setup_key = ""
            self.accounts.audit(user["id"], "setup")
            return 201, {"created": True}, None
        if method == "POST" and route == "/api/register":
            with self.lock:
                attempts = self.registrations[remote]
                while attempts and time.time()-attempts[0] > 3600: attempts.popleft()
                if len(attempts) >= 3: raise PermissionError("Too many registration attempts. Try again later.")
                attempts.append(time.time())
                pending = self.accounts.register(body.get("username"), body.get("password"), body.get("name"))
            self.accounts.audit(pending["id"], "access_requested")
            return 202, {"status":"pending", "message":"Access requested. Wait for owner approval before signing in."}, None
        if method == "POST" and route == "/api/login":
            with self.lock:
                attempts = self.attempts[remote]
                while attempts and time.time()-attempts[0] > 900: attempts.popleft()
                if len(attempts) >= 5: raise PermissionError("Too many attempts. Try again in 15 minutes.")
                attempts.append(time.time())
            session, csrf, user = self.accounts.login(body.get("username"), body.get("password"))
            with self.lock: self.attempts[remote].clear()
            result = {"profile": user, "csrf": csrf}
            if body.get("remember_device"):
                device = self.accounts.issue_device(
                    user["id"], body.get("device_name"), body.get("device_type", "desktop"),
                    body.get("platform", ""),
                )
                result["device_credential"] = device["credential"]
                result["device"] = {key: device[key] for key in ("device_id", "device_name", "device_type", "platform")}
            self.accounts.audit(user["id"], "login")
            return 200, result, self.cookie(session, public)
        if method == "POST" and route == "/api/login/device":
            with self.lock:
                attempts = self.device_attempts[remote]
                while attempts and time.time()-attempts[0] > 900: attempts.popleft()
                if len(attempts) >= 8: raise PermissionError("Too many attempts. Try again in 15 minutes.")
                attempts.append(time.time())
            row = self.accounts.device_login(body.get("credential"))
            session, csrf, user = self.accounts.issue_session(row)
            with self.lock: self.device_attempts[remote].clear()
            self.accounts.audit(user["id"], "device_login")
            return 200, {"profile": user, "csrf": csrf}, self.cookie(session, public)
        if user is None: raise PermissionError("Sign in to C.O.R.E.")
        if method != "GET" and not hmac.compare_digest(str(headers.get("X-Core-CSRF", "")), user["csrf"]):
            raise PermissionError("Session verification failed. Reload the page.")
        if method == "GET" and route == "/api/me":
            return 200, {"profile": {k:v for k,v in user.items() if k not in ("csrf", "admin_until")}, "csrf": user["csrf"]}, None
        if method == "POST" and route == "/api/logout":
            self.accounts.logout(token)
            return 200, {"signed_out": True}, self.cookie("", public, True)
        if method == "POST" and route == "/api/password":
            self.accounts.change_password(user["id"],body.get("current_password"),body.get("new_password"))
            self.accounts.audit(user["id"],"password_changed")
            self.events.publish([user["id"]], {"type": "session.revoked", "reason": "password_changed",
                                               "message": "The password changed. Sign in again."})
            return 200, {"password_changed": True, "sign_in_required": True}, self.cookie("",public,True)
        if method == "POST" and route == "/api/session/renew":
            renewed = self.accounts.renew_session(token)
            if renewed is None:
                raise PermissionError("This session has expired. Sign in again.")
            return 200, renewed, None
        if method == "POST" and route == "/api/ws-ticket":
            if not self.ws_available:
                raise ConnectionError("This CORE-HOST does not have the event channel enabled.")
            return 200, self.tickets.issue(user["id"]), None
        if user.get("password_change_required"):
            raise PermissionError("Change your temporary password before using the portal.")
        if route == "/api/devices" and method == "GET":
            everyone = query.get("all", ["0"])[0] == "1"
            if everyone and user["role"] != "owner":
                raise PermissionError("Host owner access is required.")
            devices = self.accounts.devices(None if everyone else user["id"])
            return 200, {"devices": devices}, None
        if route.startswith("/api/devices/"):
            parts = route.strip("/").split("/")
            if len(parts) != 4 or parts[3] != "revoke" or method != "POST":
                raise ValueError("Invalid device route.")
            target = self.accounts.revoke_device(parts[2], None if user["role"] == "owner" else user["id"])
            self.accounts.audit(user["id"], "device_revoked", {"device": parts[2]})
            self.events.publish([target], {"type": "session.revoked", "reason": "device_revoked",
                                           "device_id": parts[2], "message": "This device was revoked by the account owner."})
            return 200, {"revoked": True}, None
        if route == "/api/reauth" and method == "POST":
            if user['role']!='owner':raise PermissionError("Host owner access is required.")
            with self.lock:
                attempts=self.admin_attempts[user['id']]
                while attempts and time.time()-attempts[0]>900:attempts.popleft()
                if len(attempts)>=5:raise PermissionError("Too many password attempts. Try again in 15 minutes.")
                attempts.append(time.time())
                self.accounts.reauthenticate(token,body.get('password'))
                attempts.clear()
            self.accounts.audit(user['id'],'admin_unlocked')
            return 200, {'unlocked_seconds':300}, None
        if route in ('/api/settings','/api/access','/api/profiles','/api/audit','/api/quotas') or (route=='/api/jobs' and method=='POST' and body.get('service') in ('ascs','tiviss','rescs')):
            if user['role']!='owner':raise PermissionError("Host owner access is required.")
            if user.get('admin_until',0)<=time.time():raise PermissionError("Re-enter your password to unlock administration for five minutes.")
        if route=='/api/quotas':
            if method=='GET':return 200, {'quotas':[{'id':p['id'],'username':p['username'],'bytes':self.library.quota(p['id'])} for p in self.accounts.profiles()]}, None
            if method=='POST':
                target=self.accounts.account_id(body.get('username'))
                self.library.set_quota(target,body.get('bytes'))
                self.accounts.audit(user['id'],'quota_changed',{'profile':target})
                return 200, {'saved':True}, None
        if route=='/api/folders':
            if method=='GET':return 200, self.library.folders(user['id']), None
            if method=='POST':return 201, self.library.create_folder(user['id'],body.get('name')), None
        if route=='/api/shares' and method=='POST':
            recipient=self.accounts.account_id(body.get('username'))
            action=body.get('action','grant')
            if action not in ('grant','revoke'):raise ValueError('Choose grant or revoke.')
            self.library.share(user['id'],body.get('folder'),recipient,action=='revoke')
            self.accounts.audit(user['id'],'share_'+action)
            return 200, {'saved':True}, None
        if route == "/api/services" and method == "GET":
            catalog = self.services.catalog()
            return 200, {"pi_mode":bool(self.services.pi_policy),"services": catalog if user["role"] == "owner" else [x for x in catalog if x["id"] in ("asis","rescs")], "links": self.config["links"] if user["role"] == "owner" else {}}, None
        if route=='/api/ai-status' and method=='GET':
            if user['role']!='owner':raise PermissionError('Host owner access is required.')
            policy=self.services.pi_policy
            if not policy:return 200, {'enabled':False}, None
            models={**self.config['models'],**self.config.get('profile_models',{}).get(user['id'],{})}
            with self.services.lock:jobs=list(self.services.jobs.values())
            return 200, {'enabled':True,'models':{service:policy.evaluate(models.get(service,''),service) for service in ('asis','ascs')},
                'active_jobs':sum(j.status=='running' for j in jobs),
                'queued_jobs':sum(j.status=='queued' for j in jobs),'coding_mode':'generation only'}, None
        if route == "/api/status" and method == "GET":
            return 200, {"host_running": bool(self.app and self.app.is_running), "web": "online",
                         "storage": "RESCS", "storage_owner": self.storage.scope(user["id"])[0]}, None
        if route == "/api/chats" and method == "GET":
            home = self.data / "profiles" / user["id"] / "chats"
            chats = []
            if home.exists():
                for path in sorted(home.glob("*.json"),key=lambda p:p.stat().st_mtime,reverse=True)[:50]:
                    row = json.loads(path.read_text())
                    chats.append({"id":row["id"],"service":row["service"],"prompt":row.get("prompt","")[:8000],
                                  "output":"".join(e["text"] for e in row["events"] if e["kind"]=="output")[-20000:]})
            return 200, {"chats":chats}, None
        if route == "/api/files":
            if method == "GET":
                return 200, self.library.listing(self.storage,user['id'],offset=int(query.get('offset',['0'])[0]),
                    folder=query.get('folder',[None])[0],trash=query.get('trash',['0'])[0]=='1',
                    shared=query.get('shared',['0'])[0]=='1',search=query.get('search',[''])[0]), None
            if method == "POST":
                import base64
                data = base64.b64decode(body.get("base64",""),validate=True)
                with self.lock:
                    folder=body.get('folder','');self.library.folder(user['id'],folder)
                    meta = self.storage.upload(user['id'],body.get('name'),data,body.get('upload_id',''),quota_bytes=self.library.quota(user['id']))
                    # A retry cannot silently move a previous upload into a shared folder.
                    if not self.library.entry(meta['id']):self.library.attach(user['id'],meta['id'],folder)
                return 201, meta, None
        if route.startswith("/api/files/"):
            parts=route.strip('/').split('/')
            if len(parts) not in (3,4):raise ValueError('Invalid file route.')
            file_id=parts[2]
            if method=='GET' and (len(parts)==3 or parts[3]=='preview'):
                with self.lock:
                    owner=self.library.resolve(self.storage,user['id'],file_id)
                    # Preview is returned as bytes in JSON, never executed as HTML.
                    return 200, self.storage.download(owner,file_id), None
            if method=='POST' and len(parts)==4:
                action={'delete':'trash'}.get(parts[3],parts[3])
                with self.lock:self.library.change(self.storage,user['id'],file_id,action,body.get('folder',''))
                self.accounts.audit(user['id'],'file_'+action)
                return 200, {'saved':True,'deleted':action=='trash'}, None
        if route == "/api/records":
            scope = body.get("service", "workspace") if method == "POST" else query.get("service", ["workspace"])[0]
            if user["role"] != "owner" and scope not in ("workspace","asis"): raise PermissionError("Members have messaging and personal cloud storage only.")
            if method == "GET": return 200, self.storage.records(user["id"], query.get("service", ["workspace"])[0],
                limit=int(query.get("limit", ["100"])[0]), offset=int(query.get("offset", ["0"])[0])), None
            if method == "POST":
                with self.lock:
                    if user["role"] != "owner":
                        page = self.storage.records(user["id"],scope,limit=1)
                        if page["total"] >= 1000 and self.storage.current_record(user["id"],body.get("key"),scope) is None:
                            raise ValueError("This personal record scope has reached its 1000-record quota.")
                    if "expected_revision" in body:
                        saved = self.storage.conditional_save(user["id"], body.get("key"), body.get("value"), body.get("service", "workspace"), body["expected_revision"])
                    else:
                        saved = self.storage.save(user["id"], body.get("key"), body.get("value"), body.get("service", "workspace"))
                self.accounts.audit(user["id"], "record_saved")
                return 200, saved, None
        if route == "/api/jobs" and method == "POST":
            if body.get("service") == "rescs" and self.storage.endpoint != "http://127.0.0.1:8081":
                raise ValueError("Managed RESCS uses http://127.0.0.1:8081. Keep the configured backend running independently or explicitly change Settings before managed startup.")
            key = headers.get("Idempotency-Key") or headers.get("idempotency-key") or ""
            job_key = None
            if key:
                if not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", str(key)):
                    raise ValueError("The Idempotency-Key must be 8–128 safe characters.")
                job_key = (user["id"], str(key))
                with self.lock:
                    cached = self.idempotency.get(job_key)
                    if cached:
                        return 202, self.services.get(cached, user).view(), None
                    if job_key in self.idempotency:
                        raise ValueError("This request is already starting. Poll its job shortly.")
                    self.idempotency[job_key] = None
            try:
                result = self.services.start(body.get("service"), user, body.get("prompt", ""), body.get("mode", "plan"), persist=body.get("persist", True))
            except Exception:
                if job_key is not None:
                    with self.lock: self.idempotency.pop(job_key, None)
                raise
            if job_key is not None:
                with self.lock:
                    self.idempotency[job_key] = result["id"]
                    if len(self.idempotency) > 2048:
                        for stale in list(self.idempotency)[:1024]:
                            self.idempotency.pop(stale, None)
            self.accounts.audit(user["id"], "service_requested", {"service": body.get("service"), "job": result["id"]})
            return 202, result, None
        if route.startswith("/api/jobs/"):
            job_id = route.split("/")[3]
            job = self.services.get(job_id, user)
            if method == "GET": return 200, job.view(int(query.get("after", ["0"])[0])), None
            if method == "POST" and route.endswith("/stop"): return 200, self.services.stop(job_id, user), None
            if method == "POST" and route.endswith("/save"):
                if job.status in ("queued", "starting", "running"): raise ValueError("Stop or finish the task first.")
                with self.lock:
                    if user["role"] != "owner":
                        page=self.storage.records(user["id"],job.service,limit=1)
                        if page["total"]>=1000 and self.storage.current_record(user["id"],"task-"+job.id,job.service) is None:
                            raise ValueError("This personal record scope has reached its 1000-record quota.")
                    return 200, self.storage.save(user["id"], "task-"+job.id, job.view(), job.service), None
        if route in ("/api/profiles", "/api/access", "/api/settings", "/api/audit"):
            if user["role"] != "owner": raise PermissionError("Host owner access is required.")
            if route == "/api/access":
                if method == "GET": return 200, {"requests":[x for x in self.accounts.profiles() if x["role"]=="pending"]}, None
                if method == "POST":
                    result = self.accounts.review(body.get("user_id"), body.get("action"))
                    self.accounts.audit(user["id"], "access_reviewed", {"profile":result["id"],"action":body.get("action")})
                    if body.get("action") in ("revoke", "reject"):
                        self.events.publish([result["id"]], {"type": "session.revoked", "reason": "access_revoked",
                                                             "message": "Access to this account was revoked."})
                    return 200, result, None
            if route == "/api/profiles":
                if method == "GET": return 200, {"profiles": self.accounts.profiles()}, None
                if method == "POST": return 201, self.accounts.create(body.get("username"), body.get("password"), body.get("name")), None
            if route == "/api/audit" and method == "GET": return 200, {"events": self.accounts.events()}, None
            if route == "/api/settings":
                if method == "GET": return 200, {k:v for k,v in self.config.items() if k != "rescs_key"}, None
                if method == "POST": return self.settings(body, user)
        return 404, {"error": "Unknown endpoint."}, None

    def settings(self, body, user):
        with self.lock:
            candidate = dict(self.config)
            roots, links = body.get("roots", candidate["roots"]), body.get("links", candidate["links"])
            if not isinstance(roots, dict) or set(roots) != set(CATALOG) or not all(isinstance(v,str) and v for v in roots.values()):
                raise ValueError("Provide a source path for every registered service.")
            if not isinstance(links, dict) or any(k not in CATALOG for k in links): raise ValueError("Unknown service link.")
            for url in links.values():
                p = urlparse(url)
                if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password:
                    raise ValueError("Service links must be HTTP(S) URLs.")
            origin = body.get("public_origin", candidate["public_origin"])
            self.validate_origin(origin)
            models = body.get("models", candidate["models"])
            if not isinstance(models,dict) or set(models) != {"asis","ascs","tiviss"} or not all(isinstance(v,str) and len(v)<200 for v in models.values()):
                raise ValueError("Provide model names for asis, ascs and tiviss (empty retains ASIS/ASCS defaults).")
            profile_models = body.get("profile_models", candidate.get("profile_models", {}))
            import re
            if not isinstance(profile_models,dict) or any(not re.fullmatch(r"[a-f0-9]{32}",k) or not isinstance(v,dict)
                    or any(s not in ("asis","ascs","tiviss") or not isinstance(m,str) or len(m)>200 for s,m in v.items()) for k,v in profile_models.items()):
                raise ValueError("Profile models must map profile IDs to service/model names.")
            candidate["profile_models"] = profile_models
            key = body.get("rescs_key") or candidate["rescs_key"]
            if not isinstance(key,str) or len(key) < 16: raise ValueError("RESCS keys require at least 16 characters.")
            storage = RescsStorage(body.get("rescs_url", candidate["rescs_url"]), key)
            candidate.update(roots=roots, links=links, models=models, public_origin=origin, rescs_url=storage.endpoint, rescs_key=key)
            self.config = candidate; self.save_config()
            self.storage = storage; self.services.roots = roots; self.services.api_key = key
            self.services.models = models
            self.services.profile_models = profile_models
        self.accounts.audit(user["id"], "settings_changed")
        return 200, {"saved": True}, None

    def check_request(self, method, headers):
        host = headers.get("Host", "")
        allowed = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        if self.config["public_origin"]: allowed.add(urlparse(self.config["public_origin"]).netloc)
        if host not in allowed: raise PermissionError("Unrecognized host. Configure CORE_PUBLIC_ORIGIN for web access.")
        if method != "GET":
            origin = headers.get("Origin")
            expected = self.config["public_origin"] if host == urlparse(self.config["public_origin"]).netloc else "http://"+host
            if origin and origin != expected: raise PermissionError("Cross-origin requests are disabled.")
            if headers.get("Content-Type", "").split(";",1)[0] != "application/json": raise ValueError("JSON content type is required.")

    def handler(self):
        gateway = self
        ui = (Path(__file__).parent / "portal.html").read_text()
        class Handler(BaseHTTPRequestHandler):
            server_version = "COREWeb/0.5"
            def log_message(self, *args): pass
            def setup(self):
                super().setup(); self.connection.settimeout(15)
            def reply(self, status, data, cookie=None, html=False):
                raw = data.encode() if html else json.dumps(data).encode()
                self.send_response(status)
                for key,value in {"Content-Type": "text/html; charset=utf-8" if html else "application/json",
                   "Content-Length": str(len(raw)), "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                   "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                   "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items():
                    self.send_header(key,value)
                if cookie: self.send_header("Set-Cookie", cookie)
                self.end_headers()
                try: self.wfile.write(raw)
                except (BrokenPipeError, ConnectionResetError): pass
            def run_request(self):
                try:
                    gateway.check_request(self.command, self.headers)
                    if self.command == "GET" and urlparse(self.path).path == "/":
                        self.reply(200, ui, html=True); return
                    body = {}
                    if self.command != "GET":
                        if urlparse(self.path).path == "/api/files" and gateway.accounts.session(gateway.token(self.headers)) is None:
                            raise PermissionError("Sign in before uploading files.")
                        length = int(self.headers.get("Content-Length", "0"))
                        maximum = 12*1024*1024 if urlparse(self.path).path == "/api/files" else MAX_BODY
                        if not 0 < length <= maximum: raise ValueError("Request body exceeds this endpoint size limit.")
                        body = json.loads(self.rfile.read(length))
                        if not isinstance(body, dict): raise ValueError("Expected a JSON object.")
                    remote = self.client_address[0]
                    if remote == "127.0.0.1" and self.headers.get("Host") == urlparse(gateway.config["public_origin"]).netloc:
                        import ipaddress
                        forwarded = self.headers.get("X-Forwarded-For", "").split(",")[-1].strip()
                        try: remote = str(ipaddress.ip_address(forwarded))
                        except ValueError: pass
                    status, data, cookie = gateway.dispatch(self.command, self.path, body, self.headers, remote)
                    self.reply(status, data, cookie)
                except RecordConflict as exc: self.reply(409, {"error": str(exc)})
                except PermissionError as exc: self.reply(403, {"error": str(exc)})
                except (ValueError, TypeError, KeyError) as exc: self.reply(400, {"error": str(exc)})
                except ConnectionError as exc: self.reply(503, {"error": str(exc)})
                except Exception: self.reply(500, {"error": "The host could not complete this request."})
            do_GET = run_request
            do_POST = run_request
        return Handler

    def close(self):
        self.services.close(); self.library.close(); self.accounts.close()


def serve(app=None, *, directory=None, port=8780, open_browser=False, start_storage=False):
    gateway = Gateway(app, directory=directory, port=port)
    try:
        server = LimitedHTTPServer(("127.0.0.1", port), gateway.handler())
    except Exception:
        gateway.close(); raise
    server.daemon_threads = True
    import signal
    previous_term = None
    if threading.current_thread() is threading.main_thread():
        previous_term = signal.getsignal(signal.SIGTERM)
        def terminate(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, terminate)
    previous_break = None
    if threading.current_thread() is threading.main_thread() and hasattr(signal,"SIGBREAK"):
        previous_break=signal.getsignal(signal.SIGBREAK)
        signal.signal(signal.SIGBREAK,terminate)
    event_server = WebSocketServer(gateway.events, gateway.tickets, port=gateway.ws_port)
    gateway.ws_running = event_server.start()
    if gateway.ws_running:
        print(f"C.O.R.E. event channel: ws://127.0.0.1:{gateway.ws_port}/api/ws")
    elif gateway.ws_available:
        print("C.O.R.E. event channel could not start; clients continue with polling.")
    print(f"C.O.R.E. portal: http://127.0.0.1:{port}")
    if gateway.accounts.empty(): print("First-run setup key:", gateway.setup_key)
    print("Keep this window open. Ctrl+C stops managed services.")
    try:
        if app: app.start()
        if start_storage:
            import socket
            from urllib.request import urlopen
            if gateway.config["rescs_url"].rstrip('/') != 'http://127.0.0.1:8081':
                raise ValueError("--with-storage requires the private local RESCS endpoint.")
            with socket.socket() as probe:
                try: probe.bind(('127.0.0.1',8081))
                except OSError as exc: raise ValueError("Port 8081 is occupied. Stop your existing RESCS instance explicitly first.") from exc
            owners=[p for p in gateway.accounts.profiles() if p['role']=='owner']
            if not owners:raise ValueError("Initialize an owner before starting bundled storage.")
            job=gateway.services.start('rescs',owners[0])
            deadline=time.monotonic()+30
            while True:
                try:
                    with urlopen('http://127.0.0.1:8081/health/ready',timeout=.5) as response:
                        if response.status==200:break
                except OSError:pass
                if time.monotonic()>deadline or gateway.services.jobs[job['id']].status=='failed':
                    raise ConnectionError("Bundled RESCS did not become ready. Check its environment and host job log.")
                time.sleep(.1)
            print("Bundled RESCS storage is ready.",flush=True)
        if open_browser:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{port}")
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt: pass
    finally:
        if previous_term is not None: signal.signal(signal.SIGTERM, previous_term)
        if previous_break is not None: signal.signal(signal.SIGBREAK,previous_break)
        event_server.stop()
        server.server_close(); gateway.close()
        if app: app.stop()
