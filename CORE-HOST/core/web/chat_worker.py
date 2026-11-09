"""Tool-free, account-isolated Ollama messaging worker for public portal members."""
import argparse
import json
import os
from pathlib import Path
import tempfile
from core.inference import ChatStream


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--profile-dir',required=True)
    parser.add_argument('--model',required=True)
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--message')
    source.add_argument('--message-stdin',action='store_true')
    parser.add_argument('--no-memory',action='store_true')
    parser.add_argument('--coding',action='store_true',help='Code generation only; no shell or file tools.')
    args=parser.parse_args()
    if args.message_stdin:
        import sys
        args.message=sys.stdin.buffer.read(128001).decode('utf-8')
        if len(args.message)>32000:raise ValueError('Message exceeded the limit.')
    home=Path(args.profile_dir);home.mkdir(parents=True,exist_ok=True)
    path=home/'chat-context.json'
    messages=[]
    if not args.no_memory and path.is_file():
        messages=json.loads(path.read_text())[-12:]
    messages.append({'role':'user','content':args.message})
    # No tools, filesystem access, shell, shared conversation ID or remote provider fallback.
    if args.coding:messages=[{'role':'system','content':'Generate code and explain changes. You have no tools or repository access. Never claim to have edited or executed files.'}]+[m for m in messages if m.get('role')!='system']
    output=[]
    with ChatStream(args.model, messages) as stream:
        for event in stream:
            text=event.get('message',{}).get('content','')
            print(text,end='',flush=True);output.append(text)
    if not args.no_memory:
        messages.append({'role':'assistant','content':''.join(output)})
        fd,name=tempfile.mkstemp(dir=home,prefix='context-',suffix='.json')
        with os.fdopen(fd,'w') as stream:json.dump(messages[-12:],stream)
        Path(name).replace(path)
    return 0


if __name__=='__main__':raise SystemExit(main())
