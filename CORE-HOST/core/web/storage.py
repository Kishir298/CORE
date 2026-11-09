"""The real RESCS v1 API; profile owner/namespace is derived server-side."""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
from urllib.parse import urlencode, urlparse
import urllib.request

MAX_BYTES = 8 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise OSError("Backend redirects are not permitted.")


class RecordConflict(ValueError):
    pass


def record_revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class RescsStorage:
    def __init__(self, endpoint, api_key):
        parsed = urlparse(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("RESCS endpoint must be an HTTP(S) origin.")
        if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("Remote RESCS connections require HTTPS.")
        self.endpoint, self.key = endpoint.rstrip("/"), api_key
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))

    def scope_headers(self, owner, method, path):
        import hmac
        import time
        expiry=int(time.time())+30
        message=f'{owner}\n{expiry}\n{method.upper()}\n{path}'
        signature=hmac.new(self.key.encode(),message.encode(),hashlib.sha256).hexdigest()
        return {'X-RESCS-Owner':owner,'X-RESCS-Expires':str(expiry),'X-RESCS-Signature':signature}

    def request(self, method, path, *, body=None, params=None, owner=None):
        if not self.key: raise ConnectionError("Configure the host RESCS API key in Settings first.")
        owner=owner or (body or {}).get('owner') or (params or {}).get('owner')
        if not owner and path not in ('/health/ready','/health/live'):raise PermissionError('An authenticated profile scope is required.')
        scope=self.scope_headers(owner,method,path) if owner else {}
        url = self.endpoint + path
        if params: url += "?" + urlencode(params)
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method,
                     headers={**scope,"X-API-Key": self.key, "Accept": "application/json", "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=8) as response:
                raw = response.read(MAX_BYTES+1)
                if len(raw) > MAX_BYTES: raise ConnectionError("RESCS response exceeds the portal limit.")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            if exc.code in (401,403):raise PermissionError('RESCS denied access to this profile scope.') from exc
            raise ConnectionError(f"RESCS returned HTTP {exc.code}.") from exc
        except (OSError, ValueError) as exc:
            raise ConnectionError("RESCS is unavailable or returned an invalid response.") from exc

    @staticmethod
    def scope(user_id, service="workspace"):
        if not re.fullmatch(r"[a-f0-9]{32}", user_id): raise ValueError("Invalid profile ID.")
        if not re.fullmatch(r"[a-z0-9_-]{1,32}", service): raise ValueError("Invalid service scope.")
        return "core.profile." + user_id, "personal.profile." + user_id + "." + service

    def records(self, user_id, service="workspace", *, limit=100, offset=0):
        if type(limit) is not int or type(offset) is not int or not 1 <= limit <= 500 or offset < 0:
            raise ValueError("Invalid records pagination.")
        owner, namespace = self.scope(user_id, service)
        page = self.request("GET", "/api/v1/records", params={"owner": owner, "namespace": namespace, "limit": limit, "offset": offset})
        if not isinstance(page, dict) or not isinstance(page.get("items"), list):
            raise ConnectionError("Invalid RESCS collection contract.")
        if (any(type(page.get(k)) is not int for k in ("total", "limit", "offset"))
                or page["total"] < 0 or page["limit"] != limit or page["offset"] != offset
                or len(page["items"]) > limit):
            raise ConnectionError("Invalid RESCS pagination contract.")
        # Fail closed if a backend ignores either owner or namespace filtering.
        if any(not isinstance(x, dict) or x.get("owner") != owner or x.get("namespace") != namespace for x in page["items"]):
            raise PermissionError("RESCS returned data outside this profile.")
        return page

    def current_record(self, user_id, key, service="workspace"):
        # Scan all pages under the trusted server-side owner/namespace filters.
        offset = 0
        while offset < 100000:
            page = self.records(user_id, service, limit=100, offset=offset)
            for row in page["items"]:
                if row.get("key") == key:
                    return row
            offset += len(page["items"])
            if offset >= page["total"]:
                return None
            if not page["items"]:
                raise ConnectionError("RESCS returned an incomplete page.")
        raise ConnectionError("Record lookup exceeded the sync scan limit.")

    def conditional_save(self, user_id, key, value, service, expected):
        if not isinstance(expected, str) or (expected and not re.fullmatch(r"[a-f0-9]{64}", expected)):
            raise ValueError("Invalid expected record revision.")
        current = self.current_record(user_id, key, service)
        actual = record_revision(current["value"]) if current else ""
        if actual != expected:
            raise RecordConflict("Record changed on the server. Keep the local draft and review the conflict.")
        return self.save(user_id, key, value, service)

    def save(self, user_id, key, value, service="workspace"):
        if not isinstance(key, str) or not 1 <= len(key) <= 200 or not isinstance(value, dict):
            raise ValueError("A record key and JSON object are required.")
        owner, namespace = self.scope(user_id, service)
        saved = self.request("PUT", "/api/v1/records", body={"owner": owner, "namespace": namespace, "key": key, "value": value})
        if not isinstance(saved, dict) or saved.get("owner") != owner or saved.get("namespace") != namespace or saved.get("key") != key:
            raise PermissionError("RESCS returned a saved record outside this profile/key.")
        return saved

    def files(self, user_id, *, limit=100, offset=0, tag=None):
        owner, _ = self.scope(user_id)
        params={"owner":owner,"limit":limit,"offset":offset}
        if tag: params["tags"]=tag
        page=self.request("GET","/api/v1/files",params=params)
        if not isinstance(page,dict) or not isinstance(page.get("items"),list): raise ConnectionError("Invalid file collection.")
        if any(not isinstance(row,dict) or row.get("owner")!=owner for row in page["items"]):
            raise PermissionError("RESCS returned another account's files.")
        return page

    def file_meta(self, user_id, file_id):
        from urllib.parse import quote
        owner, _ = self.scope(user_id)
        meta=self.request("GET","/api/v1/files/"+quote(file_id,safe=""),owner=owner)
        if not isinstance(meta,dict) or meta.get("owner")!=owner:
            raise PermissionError("This file belongs to another account.")
        return meta

    def upload(self, user_id, filename, data, upload_id, quota_bytes=250*1024*1024):
        import secrets
        from pathlib import Path
        if not isinstance(data,bytes) or len(data)>8*1024*1024:raise ValueError("Files must be at most 8 MiB.")
        if not re.fullmatch(r"[a-f0-9]{32}",upload_id):raise ValueError("Invalid upload ID.")
        filename=Path(str(filename).replace("\\","/")).name
        filename="".join(ch for ch in filename if ch not in '\r\n"' and ord(ch)>=32)[:180] or "file"
        owner,_=self.scope(user_id);tag="core-upload-"+upload_id
        old=self.files(user_id,tag=tag)
        if old["items"]:
            meta=old["items"][0]
            if meta.get("sha256")!=hashlib.sha256(data).hexdigest():raise RecordConflict("Upload ID already has different content.")
            return meta
        offset=total=0
        while True:
            page=self.files(user_id,limit=500,offset=offset)
            total+=sum(int(row.get("size",0)) for row in page["items"])
            offset+=len(page["items"])
            if offset>=int(page["total"]):break
            if not page["items"] or offset>10000:raise ConnectionError("File quota check could not complete.")
        if total+len(data)>quota_bytes:raise ValueError("This account has reached its file storage quota (Trash is included).")
        boundary="core-"+secrets.token_hex(24)
        fields=(f'--{boundary}\r\nContent-Disposition: form-data; name="owner"\r\n\r\n{owner}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="tags"\r\n\r\n{tag}\r\n'
                f'--{boundary}\r\nContent-Disposition: form-data; name="upload"; filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
        request=urllib.request.Request(self.endpoint+"/api/v1/files",data=fields+data+f'\r\n--{boundary}--\r\n'.encode(),method="POST",
            headers={**self.scope_headers(owner,"POST","/api/v1/files"),"X-API-Key":self.key,"Content-Type":"multipart/form-data; boundary="+boundary})
        try:
            with self.opener.open(request,timeout=30) as response:
                raw=response.read(MAX_BYTES+1)
                if len(raw)>MAX_BYTES:raise ConnectionError("Invalid file metadata size.")
                meta=json.loads(raw)
        except (OSError,ValueError) as exc:raise ConnectionError("RESCS file upload failed.") from exc
        if meta.get("owner")!=owner or meta.get("sha256")!=hashlib.sha256(data).hexdigest():
            raise PermissionError("Uploaded file did not match this account/content.")
        return meta

    def download(self, user_id, file_id):
        import base64
        from urllib.parse import quote
        meta=self.file_meta(user_id,file_id)
        if int(meta.get("size",0))>8*1024*1024:raise ValueError("This app supports file transfers up to 8 MiB.")
        request=urllib.request.Request(self.endpoint+"/api/v1/files/"+quote(file_id,safe="")+"/content",headers={**self.scope_headers(meta["owner"],"GET","/api/v1/files/"+quote(file_id,safe="")+"/content"),"X-API-Key":self.key})
        try:
            with self.opener.open(request,timeout=30) as response:data=response.read(8*1024*1024+1)
        except OSError as exc:raise ConnectionError("RESCS file download failed.") from exc
        if len(data)>8*1024*1024 or hashlib.sha256(data).hexdigest()!=meta.get("sha256"):
            raise ConnectionError("Downloaded file failed its size/integrity check.")
        return {"metadata":meta,"base64":base64.b64encode(data).decode()}

    def delete_file(self,user_id,file_id):
        from urllib.parse import quote
        self.file_meta(user_id,file_id)
        self.request("DELETE","/api/v1/files/"+quote(file_id,safe=""),owner=self.scope(user_id)[0])

    def purge_file(self,user_id,file_id):
        from urllib.parse import quote
        self.file_meta(user_id,file_id)
        self.request('DELETE','/api/v1/files/'+quote(file_id,safe='')+'/purge',owner=self.scope(user_id)[0])
