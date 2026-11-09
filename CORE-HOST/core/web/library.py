"""Gateway-owned folder, read-sharing, trash and quota metadata on the SSD.

RESCS remains the source of truth for bytes, hashes and file ownership. A grant
never changes that ownership; callers cannot choose an effective owner.
"""
import re
import sqlite3
import threading
import time
import uuid


class Library:
    def __init__(self, directory):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(directory / 'library.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS folders(id TEXT PRIMARY KEY, owner TEXT, name TEXT);
        CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY, owner TEXT, folder TEXT, trashed REAL);
        CREATE TABLE IF NOT EXISTS grants(folder TEXT, recipient TEXT, PRIMARY KEY(folder,recipient));
        CREATE TABLE IF NOT EXISTS quotas(owner TEXT PRIMARY KEY, bytes INTEGER);
        ''')
        self.db.commit()
        (directory / 'library.sqlite3').chmod(0o600)

    def quota(self, user):
        with self.lock:
            row = self.db.execute('SELECT bytes FROM quotas WHERE owner=?', (user,)).fetchone()
            return row[0] if row else 250 * 1024 * 1024

    def set_quota(self, user, size):
        if type(size) is not int or not 8 * 1024 * 1024 <= size <= 10 * 1024**3:
            raise ValueError('Quota must be between 8 MiB and 10 GiB; existing bytes are never deleted.')
        with self.lock, self.db:
            self.db.execute('INSERT OR REPLACE INTO quotas VALUES(?,?)', (user, size))

    def folder(self, user, folder):
        if not folder: return None
        with self.lock:
            row = self.db.execute('SELECT * FROM folders WHERE id=? AND owner=?', (folder, user)).fetchone()
            if row is None: raise PermissionError('Folder is unavailable to this account.')
            return dict(row)

    def folders(self, user):
        with self.lock:
            own = [dict(x) for x in self.db.execute('SELECT * FROM folders WHERE owner=? ORDER BY name', (user,))]
            shared = [dict(x) for x in self.db.execute('SELECT f.id,f.name FROM folders f JOIN grants g ON f.id=g.folder WHERE g.recipient=? ORDER BY f.name', (user,))]
            for item in own:
                item['recipients'] = [r[0] for r in self.db.execute('SELECT recipient FROM grants WHERE folder=?', (item['id'],))]
            return {'folders': own, 'shared_folders': shared}

    def create_folder(self, user, name):
        if not isinstance(name, str) or not name.strip() or len(name)>100 or any(ord(c)<32 or c in '/\\' for c in name):
            raise ValueError('Use a folder name of 1–100 characters without slashes/control characters.')
        item = {'id': uuid.uuid4().hex, 'owner': user, 'name': name.strip()}
        with self.lock, self.db:
            self.db.execute('INSERT INTO folders VALUES(:id,:owner,:name)', item)
        return item

    def share(self, user, folder, recipient, revoke=False):
        self.folder(user, folder)
        if not folder: raise ValueError('Choose a folder to share.')
        with self.lock, self.db:
            if revoke: self.db.execute('DELETE FROM grants WHERE folder=? AND recipient=?', (folder, recipient))
            else: self.db.execute('INSERT OR IGNORE INTO grants VALUES(?,?)', (folder, recipient))

    def entry(self, file_id):
        if not isinstance(file_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', file_id):
            raise ValueError('Invalid file ID.')
        with self.lock:
            row = self.db.execute('SELECT * FROM files WHERE id=?', (file_id,)).fetchone()
            return dict(row) if row else None

    def attach(self, user, file_id, folder=''):
        self.folder(user, folder)
        old = self.entry(file_id)
        if old and old['owner'] != user: raise PermissionError('File belongs to another account.')
        with self.lock, self.db:
            self.db.execute('INSERT INTO files VALUES(?,?,?,0) ON CONFLICT(id) DO UPDATE SET folder=excluded.folder', (file_id, user, folder))

    def resolve(self, storage, user, file_id, *, write=False, allow_trash=False):
        item = self.entry(file_id)
        owner = item['owner'] if item else user
        if owner != user:
            with self.lock:
                allowed = item and self.db.execute('SELECT 1 FROM grants WHERE folder=? AND recipient=?', (item['folder'], user)).fetchone()
            if write or not allowed: raise PermissionError('File is unavailable to this account.')
        if item and item['trashed'] and not allow_trash: raise PermissionError('File is in Trash.')
        storage.file_meta(owner, file_id)  # Verify ownership against RESCS on every content/change request.
        return owner

    def listing(self, storage, user, *, offset=0, folder=None, trash=False, search='', shared=False):
        if type(offset) is not int or offset<0 or not isinstance(search,str) or len(search)>180:
            raise ValueError('Invalid file listing request.')
        if folder and not shared: self.folder(user, folder)
        if shared:
            with self.lock:
                ids = [r[0] for r in self.db.execute('SELECT f.id FROM files f JOIN grants g ON f.folder=g.folder WHERE g.recipient=? AND f.trashed=0', (user,))]
            rows=[]
            for file_id in ids:
                item=self.entry(file_id)
                if folder is not None and item['folder']!=folder: continue
                try:
                    owner=self.resolve(storage,user,file_id)
                    rows.append(storage.file_meta(owner,file_id))
                except PermissionError: continue
        else:
            rows=[]; start=0
            while True:
                page=storage.files(user,limit=500,offset=start)
                rows.extend(page['items']);start+=len(page['items'])
                if start>=page['total']:break
                if not page['items'] or start>10000:raise ConnectionError('File listing could not complete.')
        visible=[]
        for row in rows:
            item=self.entry(row['id']) or {'folder':'','trashed':0}
            if bool(item['trashed']) != trash:continue
            if folder is not None and item['folder']!=folder:continue
            name=row.get('filename',row.get('name',''))
            if search.casefold() not in name.casefold():continue
            visible.append({**row,'folder':item['folder'],'trashed':item['trashed'],'read_only':shared})
        return {'items':visible[offset:offset+100],'total':len(visible),'offset':offset,'limit':100,'quota_bytes':self.quota(user)}

    def change(self, storage, user, file_id, action, folder=''):
        owner=self.resolve(storage,user,file_id,write=True,allow_trash=True)
        if action=='move':
            if self.entry(file_id) and self.entry(file_id)['trashed']:raise ValueError('Restore this file before moving it.')
            self.attach(owner,file_id,folder)
        elif action in ('trash','restore'):
            if not self.entry(file_id):self.attach(owner,file_id)
            with self.lock,self.db:
                self.db.execute('UPDATE files SET trashed=? WHERE id=?',(time.time() if action=='trash' else 0,file_id))
        elif action=='purge':
            if not self.entry(file_id) or not self.entry(file_id)['trashed']:raise ValueError('Move this file to Trash before permanently deleting it.')
            storage.purge_file(owner,file_id)
            with self.lock,self.db:self.db.execute('DELETE FROM files WHERE id=?',(file_id,))
        else:raise ValueError('Unknown file action.')

    def close(self):
        with self.lock:self.db.close()
