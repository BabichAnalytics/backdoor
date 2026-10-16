"""Backdoor desktop UI and command-line entry point. Python 3.12+."""
import argparse
import json
from pathlib import Path
import queue
import threading
from engine import backup, verify_report

def launch():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    root = tk.Tk()
    root.title('BACKDOOR | Backup & Verification')
    root.geometry('1000x740')
    root.minsize(800, 620)
    root.configure(bg='#101923')
    style = ttk.Style()
    style.theme_use('clam')
    style.configure('.', font=('Segoe UI', 10), background='#182635', foreground='#e6eef5')
    style.configure('TFrame', background='#101923')
    style.configure('TLabel', background='#101923', foreground='#e6eef5')
    style.configure('TButton', padding=9, background='#234d5c')
    style.configure('TEntry', fieldbackground='#f3f7fa', foreground='#15212b', padding=7)
    style.configure('Horizontal.TProgressbar', background='#4dc9b2', troughcolor='#243747')
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='BACKDOOR', font=('Segoe UI', 25, 'bold'), foreground='#60d9c1').pack(anchor='w')
    ttk.Label(frame, text='Local backup. Independent verification. Clear results.').pack(anchor='w', pady=(0, 18))
    paths = {}
    for key, label in [('source', 'Source folder'), ('destination', 'Destination folder (external SSD or separate location)')]:
        ttk.Label(frame, text=label).pack(anchor='w')
        row = ttk.Frame(frame); row.pack(fill='x', pady=(4, 12))
        paths[key] = tk.StringVar()
        ttk.Entry(row, textvariable=paths[key]).pack(side='left', fill='x', expand=True)
        def browse(k=key):
            value = filedialog.askdirectory(title='Choose '+k+' folder')
            if value: paths[k].set(value)
        ttk.Button(row, text='Browse', command=browse).pack(side='left', padx=(10, 0))
    ttk.Label(frame, text='Each run creates a new folder. Source files are never deleted or overwritten.').pack(anchor='w', pady=4)
    controls = ttk.Frame(frame); controls.pack(fill='x', pady=12)
    events = queue.Queue(); stop = threading.Event()
    state = {'busy': False, 'report': None}
    status = tk.StringVar(value='Ready — choose source and destination folders.')
    progress = ttk.Progressbar(frame, mode='determinate', maximum=100)
    progress.pack(fill='x', pady=8)
    ttk.Label(frame, textvariable=status, wraplength=900).pack(anchor='w')
    log = tk.Text(frame, bg='#0c141e', fg='#bfd0df', insertbackground='white', relief='flat',
                  font=('Consolas', 10), height=14, state='disabled', wrap='word')
    log.pack(fill='both', expand=True, pady=14)
    def write(text):
        log.configure(state='normal'); log.insert('end', text+'\n'); log.see('end'); log.configure(state='disabled')
    def busy(value):
        state['busy'] = value
        start.configure(state='disabled' if value else 'normal')
        verify.configure(state='disabled' if value else 'normal')
        cancel.configure(state='normal' if value else 'disabled')
    def worker(source, destination):
        try: backup(source, destination, stop, events.put)
        except Exception as exc: events.put({'event': 'fatal', 'message': str(exc)})
    def begin():
        if state['busy']: return
        if not paths['source'].get().strip() or not paths['destination'].get().strip():
            messagebox.showerror('Folders required', 'Choose both folders.'); return
        stop.clear(); progress['value'] = 0; busy(True)
        source, destination = paths['source'].get(), paths['destination'].get()
        write('Starting a new copy-only backup…')
        threading.Thread(target=worker, args=(source, destination), daemon=True).start()
    def check():
        filename = filedialog.askopenfilename(title='Choose a Backdoor report.json', filetypes=[('JSON reports','*.json')])
        if not filename: return
        busy(True); status.set('Rechecking backup hashes…')
        def task():
            try: events.put({'event': 'recheck', 'data': verify_report(filename)})
            except Exception as exc: events.put({'event': 'fatal', 'message': str(exc)})
        threading.Thread(target=task, daemon=True).start()
    def export():
        if not state['report']:
            messagebox.showinfo('No report', 'Finish a backup or recheck first.'); return
        filename = filedialog.asksaveasfilename(defaultextension='.json', initialfile='backdoor-report.json', filetypes=[('JSON','*.json')])
        if filename:
            try: Path(filename).write_text(json.dumps(state['report'],indent=2),encoding='utf-8')
            except OSError as exc: messagebox.showerror('Export failed',str(exc))
    start = ttk.Button(controls, text='Start verified backup', command=begin); start.pack(side='left')
    cancel = ttk.Button(controls, text='Cancel after current block', command=stop.set, state='disabled'); cancel.pack(side='left',padx=8)
    verify = ttk.Button(controls, text='Recheck a backup', command=check); verify.pack(side='left')
    ttk.Button(controls, text='Export last report', command=export).pack(side='right')
    def poll():
        try:
            while True:
                item = events.get_nowait(); event = item['event']
                if event == 'progress':
                    progress['value'] = min(99,100*item['bytes_copied']/max(1,item['total_bytes']))
                    status.set('Copying '+item['path'])
                elif event == 'scan': write(f"Scanned {item['total_files']} files, {item['total_bytes']:,} bytes.")
                elif event == 'file': write(item['status'].upper()+' | '+item['path'])
                elif event == 'done':
                    state['report'] = item; busy(False)
                    if item['status'] == 'completed': progress['value'] = 100
                    status.set(f"{item['status'].upper()} — {item['verified_files']}/{item['total_files']} files verified")
                    write('Report saved: '+str(Path(item['run_folder'])/'report.json'))
                    for error in item['scan_errors']: write('SCAN ERROR | '+error)
                    for skipped in item['skipped']: write('SKIPPED | '+skipped)
                elif event == 'recheck':
                    state['report'] = item['data']; busy(False)
                    status.set('Recheck: '+('all checked files match' if item['data']['all_match'] else 'issues found or no verified files'))
                    write(json.dumps(item['data'],indent=2))
                elif event == 'fatal': busy(False); status.set('Stopped: '+item['message']); write('ERROR | '+item['message'])
        except queue.Empty: pass
        root.after(100,poll)
    def close():
        if state['busy']:
            messagebox.showinfo('Operation active','Cancel and wait for the report before closing.'); return
        root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    poll(); root.mainloop()

def main():
    parser=argparse.ArgumentParser(description='Backdoor local backup and SHA-256 verification')
    sub=parser.add_subparsers(dest='command')
    command=sub.add_parser('backup'); command.add_argument('source'); command.add_argument('destination')
    command=sub.add_parser('verify'); command.add_argument('report')
    args=parser.parse_args()
    if args.command == 'backup':
        result=backup(args.source,args.destination); print(json.dumps(result,indent=2))
        return 0 if result['status']=='completed' else 1
    if args.command == 'verify':
        result=verify_report(args.report); print(json.dumps(result,indent=2)); return 0 if result['all_match'] else 1
    launch(); return 0

if __name__=='__main__':
    raise SystemExit(main())
