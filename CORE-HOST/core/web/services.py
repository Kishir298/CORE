"""Allowlisted local service commands with profile workspaces and live output."""
from __future__ import annotations

from collections import deque
import codecs
import json
from dataclasses import dataclass, field
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid

CATALOG = {
    "asis": ("A.S.I.S.", "Personal assistant", "ASIS"),
    "ascs": ("A.S.C.S.", "Coding workspace · owner only", "ASCS"),
    "rescs": ("R.E.S.C.S.", "Profile records", "RESCS"),
    "tiviss": ("T.I.V.I.S.S.", "Independent agent · owner only", "TIVISS"),
    "rovert": ("R.O.V.E.R.T.", "Rover services · configure telemetry portal", "ROVERT"),
}


@dataclass
class Job:
    id: str
    user: str
    service: str
    status: str = "starting"
    prompt: str = ""
    persist: bool = True
    events: deque = field(default_factory=lambda: deque(maxlen=1000))
    sequence: int = 0
    process: object = None
    lock: object = field(default_factory=threading.RLock)
    cancel: object = field(default_factory=threading.Event)
    started: float = field(default_factory=time.time)

    def emit(self, kind, text):
        with self.lock:
            self.sequence += 1
            self.events.append({"id": self.sequence, "kind": kind, "text": text[:16000]})

    def view(self, after=0):
        with self.lock:
            return {"id": self.id, "service": self.service, "status": self.status,
                    "events": [event for event in self.events if event["id"] > after]}


class Services:
    def __init__(self, data, roots, api_key, models=None):
        self.data, self.roots, self.api_key = Path(data), roots, api_key
        self.models = models or {}
        self.profile_models = {}
        self.jobs = {}
        self.lock = threading.RLock()
        self.closed = False
        self.pi_slot=threading.Semaphore(1)
        self.pi_policy=None
        if os.environ.get('CORE_SAFE_CHAT')=='1':
            from core.pi_resources import PiPolicy
            self.pi_policy=PiPolicy(self.data)

    def root(self, service):
        if service not in CATALOG: raise ValueError("Unknown RISARMS service.")
        return Path(self.roots[service]).expanduser().resolve()

    def interpreter(self, service):
        root = self.root(service)
        candidate = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        return str(candidate) if candidate.is_file() else sys.executable

    def catalog(self):
        result=[{"id":key,"name":value[0],"description":value[1],
                 "installed_source":self.root(key).is_dir(),
                 "adapter":"message" if key in ("asis","ascs","tiviss") else "server" if key=="rescs" else "external",
                 "owner_only":key in ("ascs","rescs","tiviss","rovert")}
                for key,value in CATALOG.items()]
        if self.pi_policy:
            for row in result:
                if row['id'] in ('asis','ascs'):
                    row.update(installed_source=True,execution_mode='Tool-free assistance' if row['id']=='asis' else 'Code generation only; no repository tools')
                elif row['id']=='tiviss':row.update(enabled=False,execution_mode='Execution disabled on this Pi profile')
                elif row['id']=='rescs':row.update(installed_source=True,execution_mode='Private SSD service managed by systemd')
        return result

    def command(self, service, user, prompt, mode):
        if user["role"] != "owner" and service != "asis": raise PermissionError("This service requires the host owner.")
        if service not in ("asis", "ascs", "rescs", "tiviss"):
            raise ValueError("This service has no verified runnable web adapter. Configure its external URL instead.")
        if self.pi_policy and service=='ascs' and mode!='plan':raise ValueError('Pi ASCS is code generation only. Choose Plan mode; Build/Auto execution is unavailable.')
        if os.environ.get('CORE_SAFE_CHAT')=='1' and service == 'tiviss':
            raise PermissionError('Privileged agents are disabled in the Pi privacy profile. Run them separately under an isolated OS account.')
        models = {**self.models, **self.profile_models.get(user["id"], {})}
        home = self.data / "profiles" / user["id"]
        if user["role"] != "owner" or (service in ('asis','ascs') and os.environ.get('CORE_SAFE_CHAT') == '1'):
            if not models.get(service): raise ValueError('The owner must configure an installed model for this service first.')
            if self.pi_policy:home=home/'pi-chat'/service
            home.mkdir(parents=True, exist_ok=True, mode=0o700)
            env = {k:v for k,v in os.environ.items() if k in ("PATH","SYSTEMROOT","WINDIR","TEMP","TMP","LANG")}
            env.update({k:os.environ[k] for k in ('CORE_AI_CONTEXT_LIMIT','CORE_AI_THREADS') if k in os.environ})
            env.update(PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", PYTHONPATH=str(Path(__file__).resolve().parents[2]))
            return [sys.executable,"-u","-m","core.web.chat_worker","--profile-dir",str(home),"--model",models[service]]+(["--message-stdin"] if self.pi_policy else ["--message="+prompt])+(["--coding"] if service=="ascs" else []), home, env
        if service=='rescs' and os.environ.get('CORE_EXTERNAL_STORAGE')=='1':
            raise ValueError('RESCS is managed separately by systemd. Use systemctl status risarms-rescs.')
        root = self.root(service)
        marker = {"asis": "asis", "ascs": "agent", "rescs": "src/rescs", "tiviss":"tiviss"}[service]
        if not (root / marker).is_dir(): raise ValueError(f"{CATALOG[service][2]} source was not found. Set its path in Settings.")
        home = self.data / "profiles" / user["id"]
        workspace = home / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        # Do not forward host portal/RESCS credentials into agent processes.
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CORE_", "RESCS_"))}
        env.update(PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        python = self.interpreter(service)
        if service == "asis":
            for part in ("DATA", "CONFIG", "CACHE", "LOG", "MEMORY", "RUNTIME"):
                env[f"ASIS_{part}_DIRECTORY"] = str(home / "asis" / part.lower())
            env["ASIS_CORE_ENABLED"] = "false"
            argv = [python, "-u", "-m", "asis", "--mode", "general", "--workspace", str(workspace),
                    "--memory-db", str(home / "asis-memory.sqlite3"), "--message=" + prompt]
        elif service == "ascs":
            if mode not in ("plan", "build", "auto"): raise ValueError("Invalid coding mode.")
            env["AGENT_EXPERIENCE_PATH"] = str(home / "ascs-experiences.jsonl")
            env["AGENT_STOP_OLLAMA_ON_EXIT"] = "false"
            env["AGENT_PROFILE_DIRECTORY"] = str(home / "ascs")
            env["AGENT_TUI_STATE_PATH"] = str(home / "ascs" / "tui_state.json")
            env["AGENT_NONINTERACTIVE"] = "1"
            env["AGENT_ALLOW_MODEL_FALLBACK"] = "false"
            env["AGENT_PROVIDER"] = "ollama"
            argv = [python, "-u", "-m", "agent.main", "--workspace", str(workspace), "--mode", mode, "--", prompt]
        elif service == "tiviss":
            model = models.get("tiviss") or env.get("TIVISS_MODEL_ID")
            if not model: raise ValueError("Choose an installed Ollama model for TIVISS in Host settings.")
            env.update(TIVISS_MODEL_PROVIDER="ollama", TIVISS_MODEL_ID=model,
                       TIVISS_MEMORY_BACKEND="sqlite", TIVISS_MEMORY_CONVERSATION_DB=str(home/"tiviss-conversations.sqlite3"),
                       TIVISS_MEMORY_SEMANTIC_DB=str(home/"tiviss-semantic.sqlite3"), TIVISS_OWNER_ID=user["id"],
                       TIVISS_CORE_ENABLED="false", TIVISS_RESCS_ENABLED="false")
            argv = [python, "-u", "-m", "tiviss", "--message=" + prompt]
        else:
            env.update(RESCS_API_KEY=self.api_key, RESCS_API_KEY_OWNER="",
                       RESCS_DATABASE_URL="sqlite:///" + str(self.data / "rescs.sqlite3").replace("\\", "/"),
                       RESCS_STORAGE_DIR=str(self.data / "rescs-files"), RESCS_AUTO_CREATE_SCHEMA="true",
                       PYTHONPATH=str(root / "src"))
            argv = [python, "-u", "-m", "uvicorn", "rescs.main:create_app", "--factory", "--host", "127.0.0.1", "--port", "8081"]
        if service in ("asis", "ascs") and models.get(service):
            argv[4:4] = ["--model=" + models[service]]
        return argv, root, env

    def start(self, service, user, prompt="", mode="plan", persist=True):
        if not isinstance(persist,bool): raise ValueError("persist must be true or false.")
        if not isinstance(prompt, str) or len(prompt) > 32000 or (service != "rescs" and not prompt.strip()):
            raise ValueError("Enter a message of 1–32000 characters.")
        argv, cwd, env = self.command(service, user, prompt, mode)
        if not persist and (user["role"] != "owner" or (service in ('asis','ascs') and os.environ.get('CORE_SAFE_CHAT') == '1')): argv.append("--no-memory")
        with self.lock:
            if self.closed: raise ValueError("Host is shutting down.")
            active = [j for j in self.jobs.values() if j.status in ("queued", "starting", "running")]
            if self.pi_policy:
                if len(active)>=8 or any(j.user==user['id'] for j in active):
                    raise ValueError('This profile already has a queued/running task, or the eight-job queue is full.')
            else:
                maximum = max(1, int(os.environ.get('CORE_MAX_AI_JOBS','5')))
                if service != 'rescs' and sum(j.service!='rescs' for j in active)>=maximum:
                    raise ValueError('The AI service is busy. Try again when the current task finishes.')
                if len(active) >= 5 or any(j.user == user['id'] and j.service != 'rescs' and service != 'rescs' for j in active):
                    raise ValueError('A task is already running for this profile, or the host is at capacity.')
            if service == "rescs" and any(j.service == service for j in active): raise ValueError("RESCS is already managed by this host.")
            for key, old in list(self.jobs.items()):
                if len(self.jobs) < 100: break
                if old.status not in ("queued", "starting", "running"): del self.jobs[key]
            job = Job(uuid.uuid4().hex, user["id"], service, prompt=prompt, persist=persist)
            self.jobs[job.id] = job
            threading.Thread(target=self._run, args=(job, argv, cwd, env), daemon=True).start()
            return job.view()

    def _run(self, job, argv, cwd, env):
        timer = None
        held=False
        shared_descriptor=None
        pressure_stop=threading.Event()
        pressure_thread=None
        try:
            if self.pi_policy and job.service in ('asis','ascs'):
                with job.lock:job.status='queued'
                job.emit('status','Queued for the shared Pi inference slot.')
                deadline=time.monotonic()+120
                while not job.cancel.is_set():
                    if time.monotonic()>deadline:raise ValueError('AI queue wait exceeded two minutes; no task was executed.')
                    if self.pi_slot.acquire(timeout=.5):held=True;break
                if job.cancel.is_set():return
                if os.environ.get('RISARMS_INFERENCE_LOCK'):
                    from core.pi_resources import acquire_shared_lock
                    shared_descriptor=acquire_shared_lock(os.environ['RISARMS_INFERENCE_LOCK'],job.cancel,deadline)
                model=argv[argv.index('--model')+1]
                # Validate model identity before issuing any unload control request.
                self.pi_policy.installed(model,job.service)
                preliminary=self.pi_policy.evaluate(model,job.service)
                if preliminary['state']=='blocked':raise ValueError(preliminary['reason'])
                self.pi_policy.switch(model)
                previous=''
                while not job.cancel.is_set():
                    report=self.pi_policy.evaluate(model,job.service)
                    if report['state']=='allowed':break
                    if report['state']=='blocked':raise ValueError(report['reason'])
                    if report['reason']!=previous:job.emit('status',report['reason']);previous=report['reason']
                    if time.monotonic()>deadline:raise ValueError('Resources remained unavailable for two minutes; no model task was started.')
                    job.cancel.wait(1)
                if job.cancel.is_set():return
            with job.lock:
                if job.cancel.is_set(): job.status = "cancelled"; return
                job.process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if "--message-stdin" in argv else subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    start_new_session=os.name != "nt", creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
                if '--message-stdin' in argv:
                    job.process.stdin.write(job.prompt.encode('utf-8'));job.process.stdin.close()
                job.status = "running"
            job.emit("status", "Service process started.")
            if job.service != "rescs":
                timer = threading.Timer(900, lambda: self.stop(job.id, {"id": job.user, "role": "owner"}))
                timer.daemon = True; timer.start()
            if held:
                def watch_pressure():
                    while not pressure_stop.wait(2):
                        try:
                            metrics=self.pi_policy.metrics()
                            critical=(metrics['available_bytes']<512*1024**2 or (metrics.get('temperature_c') or 0)>=85 or (metrics.get('memory_pressure_avg10') or 0)>20)
                            if critical:
                                job.emit('error','Critical memory or thermal pressure; task cancelled without replay.')
                                self.stop(job.id,{'id':job.user});return
                        except (OSError,ValueError,KeyError):pass
                pressure_thread=threading.Thread(target=watch_pressure,daemon=True);pressure_thread.start()
            # Fixed-size reads stream output even when there are no newlines.
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            while True:
                chunk = job.process.stdout.read1(512)
                if not chunk: break
                job.emit("output", decoder.decode(chunk))
            tail = decoder.decode(b"", final=True)
            if tail: job.emit("output", tail)
            code = job.process.wait()
            with job.lock:
                job.status = "cancelled" if job.cancel.is_set() else "completed" if code == 0 else "failed"
            job.emit("status", f"{job.status} (exit {code}).")
        except Exception as exc:
            with job.lock: job.status = 'cancelled' if job.cancel.is_set() else 'failed'
            job.emit('error',str(exc) if self.pi_policy and isinstance(exc,ValueError) else 'Service could not start. Check its Python environment and installed dependencies.')
        finally:
            pressure_stop.set()
            if pressure_thread:pressure_thread.join(timeout=4)
            if timer: timer.cancel()
            if held:
                if job.status in ('failed','cancelled') and job.process is not None:
                    try:
                        from core.pi_resources import ollama
                        ollama('/api/generate',{'model':argv[argv.index('--model')+1],'keep_alive':0})
                    except (OSError,ValueError,KeyError):pass
                if shared_descriptor is not None:os.close(shared_descriptor)
                self.pi_slot.release()
            if job.persist:
                try:
                    home = self.data / "profiles" / job.user
                    chats = home / "chats"; chats.mkdir(parents=True, exist_ok=True, mode=0o700)
                    path = chats / (job.id + ".json")
                    with path.open("w") as stream: json.dump({"prompt":job.prompt,"started":job.started,**job.view()},stream)
                    if os.name == "posix": home.chmod(0o700);path.chmod(0o600)
                    for old in sorted(chats.glob("*.json"),key=lambda p:p.stat().st_mtime,reverse=True)[200:]: old.unlink()
                    logs = home / "logs"; logs.mkdir(exist_ok=True,mode=0o700)
                    log = logs / "tasks.log"
                    if log.exists() and log.stat().st_size > 1024*1024: log.replace(logs/"tasks.previous.log")
                    with log.open("a") as stream: stream.write(f"{job.started} {job.id} {job.service} {job.status}\n")
                    if os.name == "posix": log.chmod(0o600)
                except OSError:
                    job.emit("error", "Chat history could not be saved on the server.")

    def get(self, job_id, user):
        with self.lock: job = self.jobs.get(job_id)
        if job is None or job.user != user["id"]: raise PermissionError("Task is not available to this profile.")
        return job

    def stop(self, job_id, user):
        job = self.get(job_id, user)
        with job.lock:
            job.cancel.set()
            process = job.process
            if process is not None and process.poll() is None:
                if os.name == "nt":
                    try:
                        process.send_signal(signal.CTRL_BREAK_EVENT)
                        process.wait(timeout=3)
                    except (OSError, subprocess.TimeoutExpired):
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
                else:
                    try: os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError: pass
                    try: process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        try: os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError: pass
            job.status = "cancelled"
        return job.view()

    def close(self):
        with self.lock: self.closed = True; jobs = list(self.jobs.values())
        if self.pi_policy:self.pi_policy.close()
        for job in jobs:
            if job.status in ("queued", "starting", "running"): self.stop(job.id, {"id": job.user, "role": "owner"})
